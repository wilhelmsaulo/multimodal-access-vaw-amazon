from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point

SUBEDGES = Path("artifacts/hydro_temporal_subdivision/hydro_reference_time_subedges.gpkg")
ANCHORS = Path("artifacts/validated_spatial_transfer_anchors/validated_spatial_transfer_anchors.gpkg")
RULE = Path("artifacts/non_temporal_cartographic_snap_rule/non_temporal_cartographic_snap_rule_audit.json")
OUT = Path("artifacts/hydro_topology_with_validated_snaps")
METRIC_CRS = "EPSG:5880"
GEOD = Geod(ellps="GRS80")
ENDPOINT_EPS_M = 1e-6
TIME_TOL_MIN = 1e-9


def norm_hydro_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    s = str(value).strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


def geodesic_segment_length_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    _, _, d = GEOD.inv(float(a[0]), float(a[1]), float(b[0]), float(b[1]))
    return max(float(d), 0.0)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    edges = gpd.read_file(SUBEDGES, layer="hydro_reference_time_subedges").reset_index(drop=True)
    anchors = gpd.read_file(ANCHORS, layer="anchors").reset_index(drop=True)
    rule = json.loads(RULE.read_text(encoding="utf-8"))

    if rule.get("temporal_connector_impedance_resolved") is not True:
        raise RuntimeError("Non-temporal cartographic snap rule is not finalized")
    if rule.get("connector_is_temporal_edge") is not False:
        raise RuntimeError("Cartographic snap must not be represented as a temporal edge")
    if rule.get("zero_time_transfer_adopted") is not False:
        raise RuntimeError("A zero-minute transfer edge must not be adopted")
    if len(anchors) != 3:
        raise RuntimeError(f"Expected 3 validated anchors, got {len(anchors)}")
    if edges.crs is None or anchors.crs is None:
        raise RuntimeError("Hydro edges and anchors must have CRS")

    source_crs = edges.crs
    anchors = anchors.to_crs(source_crs)
    edges["hydro_id_norm"] = edges["hydro_id"].map(norm_hydro_id)
    anchors["hydro_id_norm"] = anchors["hydro_id"].map(norm_hydro_id)

    metric_edges = edges.to_crs(METRIC_CRS)
    metric_anchors = anchors.to_crs(METRIC_CRS)
    to_source = Transformer.from_crs(METRIC_CRS, source_crs, always_xy=True)

    # Each validated anchor is inserted only into its already-validated hydro_id.
    # No global nearest-route snapping is allowed.
    selected: list[dict] = []
    split_instructions: dict[int, list[dict]] = {}

    for ai, anchor in anchors.iterrows():
        hid = anchor["hydro_id_norm"]
        candidate_idx = edges.index[edges["hydro_id_norm"] == hid].tolist()
        if not candidate_idx:
            raise RuntimeError(f"No hydro subedges found for validated anchor {anchor['port_name']} hydro_id={hid}")

        p_metric = metric_anchors.geometry.iloc[ai]
        distances = [(ei, float(metric_edges.geometry.iloc[ei].distance(p_metric))) for ei in candidate_idx]
        edge_idx, snap_distance_m = min(distances, key=lambda x: x[1])
        line_metric = metric_edges.geometry.iloc[edge_idx]
        projected_m = float(line_metric.project(p_metric))
        line_len_m = float(line_metric.length)
        if line_len_m <= 0:
            raise RuntimeError(f"Selected subedge has non-positive metric length: {edge_idx}")
        projected_m = min(max(projected_m, 0.0), line_len_m)
        snap_metric = line_metric.interpolate(projected_m)
        sx, sy = to_source.transform(float(snap_metric.x), float(snap_metric.y))
        snap_source = Point(sx, sy)

        # We retain the already-audited anchor-to-route offset as descriptive evidence.
        # This distance is not a travel distance and never becomes time.
        instruction = {
            "anchor_index": int(ai),
            "anchor_id": str(anchor["anchor_id"]),
            "port_name": str(anchor["port_name"]),
            "hydro_id_norm": hid,
            "edge_index": int(edge_idx),
            "route_key": str(edges.loc[edge_idx, "route_key"]),
            "snap_distance_m_recomputed": snap_distance_m,
            "snap_point": snap_source,
            "projected_m": projected_m,
            "edge_metric_length_m": line_len_m,
        }
        split_instructions.setdefault(int(edge_idx), []).append(instruction)
        selected.append(instruction)

    # Current validated anchors map to distinct routes; if two ever target the same
    # source subedge, explicitly reject until a multi-split ordering audit is added.
    duplicate_target_edges = [ei for ei, vals in split_instructions.items() if len(vals) > 1]
    if duplicate_target_edges:
        raise RuntimeError(f"Multiple validated anchors target the same source subedge: {duplicate_target_edges}")

    output_edge_rows: list[dict] = []
    attachment_rows: list[dict] = []
    source_edge_time_checks: list[dict] = []

    for ei, row in edges.iterrows():
        geom = row.geometry
        if not isinstance(geom, LineString) or len(geom.coords) != 2:
            raise RuntimeError(f"Expected two-vertex LineString subedge at row {ei}")
        a = tuple(geom.coords[0])
        b = tuple(geom.coords[-1])
        original_time = float(row["travel_time_min"])
        original_length = float(row["edge_length_m"])
        base = {k: row[k] for k in edges.columns if k not in {"geometry", "hydro_id_norm"}}
        base["source_subedge_index"] = int(ei)

        insts = split_instructions.get(int(ei), [])
        if not insts:
            rec = dict(base)
            rec["topology_piece_index"] = 0
            rec["edge_length_m"] = original_length
            rec["travel_time_min"] = original_time
            rec["geometry"] = geom
            output_edge_rows.append(rec)
            source_edge_time_checks.append({
                "source_subedge_index": int(ei),
                "official_subedge_time_min": original_time,
                "topology_time_sum_min": original_time,
                "absolute_time_error_min": 0.0,
            })
            continue

        inst = insts[0]
        s = inst["snap_point"]
        # Use the metric projection only to determine whether the snap is effectively
        # at an endpoint. Interior pieces are then measured geodesically in GRS80.
        frac = inst["projected_m"] / inst["edge_metric_length_m"]
        if inst["projected_m"] <= ENDPOINT_EPS_M:
            pieces = [(a, b, original_length, original_time, geom, 0)]
            snap_node_coord = a
            split_applied = False
        elif (inst["edge_metric_length_m"] - inst["projected_m"]) <= ENDPOINT_EPS_M:
            pieces = [(a, b, original_length, original_time, geom, 0)]
            snap_node_coord = b
            split_applied = False
        else:
            snap_coord = (float(s.x), float(s.y))
            l1 = geodesic_segment_length_m(a, snap_coord)
            l2 = geodesic_segment_length_m(snap_coord, b)
            total = l1 + l2
            if total <= 0:
                raise RuntimeError(f"Anchor split produced non-positive total length at source edge {ei}")
            t1 = original_time * l1 / total
            t2 = original_time - t1
            if t1 <= 0 or t2 <= 0:
                raise RuntimeError(f"Anchor split produced non-positive time at source edge {ei}")
            pieces = [
                (a, snap_coord, l1, t1, LineString([a, snap_coord]), 0),
                (snap_coord, b, l2, t2, LineString([snap_coord, b]), 1),
            ]
            snap_node_coord = snap_coord
            split_applied = True

        topo_time_sum = 0.0
        for p0, p1, plen, ptime, pgeom, piece_index in pieces:
            rec = dict(base)
            rec["topology_piece_index"] = int(piece_index)
            rec["edge_length_m"] = float(plen)
            rec["travel_time_min"] = float(ptime)
            rec["geometry"] = pgeom
            output_edge_rows.append(rec)
            topo_time_sum += float(ptime)

        source_edge_time_checks.append({
            "source_subedge_index": int(ei),
            "official_subedge_time_min": original_time,
            "topology_time_sum_min": topo_time_sum,
            "absolute_time_error_min": abs(topo_time_sum - original_time),
        })
        attachment_rows.append({
            "anchor_id": inst["anchor_id"],
            "port_name": inst["port_name"],
            "hydro_id": inst["hydro_id_norm"],
            "route_key": inst["route_key"],
            "source_subedge_index": int(ei),
            "snap_distance_m_recomputed": float(inst["snap_distance_m_recomputed"]),
            "source_edge_projection_fraction": float(frac),
            "source_edge_split_applied": bool(split_applied),
            "snap_lon": float(snap_node_coord[0]),
            "snap_lat": float(snap_node_coord[1]),
            "attachment_role": "non_temporal_cartographic_topology_alignment",
            "connector_is_temporal_edge": False,
            "connector_travel_time_minutes": None,
            "zero_time_transfer_adopted": False,
            "snap_distance_interpreted_as_travel_distance": False,
            "distance_to_time_conversion_used": False,
        })

    topo_edges = gpd.GeoDataFrame(output_edge_rows, geometry="geometry", crs=source_crs)
    checks = pd.DataFrame(source_edge_time_checks)
    if (checks["absolute_time_error_min"] > TIME_TOL_MIN).any():
        bad = checks.loc[checks["absolute_time_error_min"] > TIME_TOL_MIN]
        raise RuntimeError(f"Time not conserved after validated snap insertion:\n{bad.to_string(index=False)}")

    # Build route-specific nodes. Coordinates are deduplicated only within the same
    # official route_key, never across different route identities.
    node_map: dict[tuple[str, float, float], str] = {}
    node_rows: list[dict] = []

    def node_for(route_key: str, coord: tuple[float, float]) -> str:
        key = (route_key, round(float(coord[0]), 12), round(float(coord[1]), 12))
        if key not in node_map:
            node_id = f"{route_key}_node_{len(node_map):06d}"
            node_map[key] = node_id
            node_rows.append({
                "node_id": node_id,
                "route_key": route_key,
                "longitude": float(coord[0]),
                "latitude": float(coord[1]),
                "geometry": Point(float(coord[0]), float(coord[1])),
            })
        return node_map[key]

    from_nodes: list[str] = []
    to_nodes: list[str] = []
    for _, r in topo_edges.iterrows():
        coords = list(r.geometry.coords)
        route_key = str(r["route_key"])
        from_nodes.append(node_for(route_key, tuple(coords[0])))
        to_nodes.append(node_for(route_key, tuple(coords[-1])))
    topo_edges["from_node"] = from_nodes
    topo_edges["to_node"] = to_nodes
    topo_edges["edge_id"] = [f"hydro_edge_{i:06d}" for i in range(len(topo_edges))]
    topo_edges["route_switching_enabled"] = False
    topo_edges["traversal_direction_policy"] = "pending_explicit_hydro_directionality_decision"

    nodes = gpd.GeoDataFrame(node_rows, geometry="geometry", crs=source_crs)
    attachments = pd.DataFrame(attachment_rows)
    if len(attachments) != 3:
        raise RuntimeError(f"Expected 3 materialized validated snap attachments, got {len(attachments)}")

    # Link each attachment to the exact route-specific node created at the snap point.
    attachment_node_ids = []
    for _, arow in attachments.iterrows():
        key = (
            str(arow["route_key"]),
            round(float(arow["snap_lon"]), 12),
            round(float(arow["snap_lat"]), 12),
        )
        node_id = node_map.get(key)
        if node_id is None:
            raise RuntimeError(f"Snap node missing from hydro topology for {arow['port_name']}")
        attachment_node_ids.append(node_id)
    attachments["hydro_node_id"] = attachment_node_ids

    topo_edges.to_file(OUT / "hydro_topology_edges.gpkg", layer="hydro_topology_edges", driver="GPKG")
    nodes.to_file(OUT / "hydro_topology_nodes.gpkg", layer="hydro_topology_nodes", driver="GPKG")
    attachments.to_csv(OUT / "validated_anchor_hydro_node_attachments.csv", index=False)
    checks.to_csv(OUT / "snap_insertion_time_conservation.csv", index=False)

    # Recheck official route totals after the second-level split at anchor locations.
    route_sums = topo_edges.groupby("route_key", as_index=False)["travel_time_min"].sum()
    original_route_sums = edges.groupby("route_key", as_index=False)["travel_time_min"].sum()
    route_check = original_route_sums.merge(route_sums, on="route_key", suffixes=("_before", "_after"))
    route_check["absolute_time_error_min"] = (
        route_check["travel_time_min_after"] - route_check["travel_time_min_before"]
    ).abs()
    if (route_check["absolute_time_error_min"] > TIME_TOL_MIN).any():
        raise RuntimeError("Official route time conservation failed after anchor insertion")
    route_check.to_csv(OUT / "route_time_conservation_after_snap_insertion.csv", index=False)

    audit = {
        "official_route_count": int(edges["route_key"].nunique()),
        "source_subedges_total": int(len(edges)),
        "topology_edges_total": int(len(topo_edges)),
        "topology_nodes_total": int(len(nodes)),
        "validated_snap_attachments_total": int(len(attachments)),
        "source_edges_split_for_anchor_insertion": int(attachments["source_edge_split_applied"].sum()),
        "routes_with_time_conservation_after_snap_insertion": int((route_check["absolute_time_error_min"] <= TIME_TOL_MIN).sum()),
        "route_time_conservation_fraction": float((route_check["absolute_time_error_min"] <= TIME_TOL_MIN).mean()),
        "max_route_time_conservation_error_min": float(route_check["absolute_time_error_min"].max()),
        "route_specific_node_identity_preserved": True,
        "cross_route_node_merging_used": False,
        "route_switching_enabled": False,
        "hydro_directionality_resolved": False,
        "traversal_direction_policy": "pending_explicit_hydro_directionality_decision",
        "cartographic_snap_is_temporal_edge": False,
        "zero_time_transfer_adopted": False,
        "distance_to_time_conversion_used": False,
        "waiting_time_included": False,
        "ready_for_hydro_directionality_decision": True,
        "ready_for_final_multimodal_routing": False,
        "scientific_policy": (
            "Hydro topology is materialized from route-specific ANTAQ temporal subedges. Validated Muaná, Soure, and Moju cartographic snaps are inserted only into their already validated hydro_id routes; an interior insertion splits the affected temporal subedge while conserving its time and the official route-level total. "
            "The snap itself is not a temporal edge. Route identities are not merged and cross-route switching is not enabled. Hydro traversal direction remains explicitly unresolved rather than silently assuming symmetric navigation."
        ),
    }
    (OUT / "hydro_topology_with_validated_snaps_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(attachments.to_string(index=False))


if __name__ == "__main__":
    main()
