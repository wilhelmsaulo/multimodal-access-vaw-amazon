from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import LineString, Point

TARGET_CRS = "EPSG:4674"
DISTANCE_CRS = "EPSG:5880"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--edges", type=Path, default=Path("artifacts/primary_motor_road_times_complete/primary_motor_edges_with_complete_times.csv.gz"))
    p.add_argument("--nodes", type=Path, default=Path("artifacts/transport_topology/road_nodes.csv.gz"))
    p.add_argument("--anchors", type=Path, default=Path("artifacts/validated_spatial_transfer_anchors/validated_spatial_transfer_anchors.gpkg"))
    p.add_argument("--terminal-policy", type=Path, default=Path("artifacts/intermodal_terminal_identity_policy/intermodal_terminal_identity_policy.csv"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/intermodal_terminal_road_edge_splits"))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    nodes = pd.read_csv(args.nodes)
    edges = pd.read_csv(args.edges, low_memory=False)
    anchors = gpd.read_file(args.anchors)
    policy = pd.read_csv(args.terminal_policy)

    if len(anchors) != 3 or len(policy) != 3:
        raise RuntimeError("Expected exactly three validated intermodal terminals")
    if not policy["terminal_identity_adopted"].astype(bool).all():
        raise RuntimeError("All three terminal semantic identities must be adopted upstream")

    node_lookup = nodes.set_index("node_id")[["longitude", "latitude"]]
    transformer = Transformer.from_crs(TARGET_CRS, DISTANCE_CRS, always_xy=True)

    out_rows: list[dict[str, object]] = []
    for _, anchor in anchors.sort_values("evidence_rank").iterrows():
        name = str(anchor["port_name"])
        match = policy[policy["port_name"].astype(str).eq(name)]
        if len(match) != 1:
            raise RuntimeError(f"Could not uniquely match terminal policy for {name}")
        pr = match.iloc[0]
        if not bool(pr["terminal_identity_adopted"]):
            raise RuntimeError(f"Terminal identity not adopted for {name}")

        lon = float(anchor.geometry.x)
        lat = float(anchor.geometry.y)
        audited_distance = float(anchor["road_distance_m"])
        # Candidate reduction only; not a routing or eligibility threshold. The final
        # selected segment must reproduce the independently audited geometric distance.
        near_nodes = nodes[
            nodes["longitude"].between(lon - 0.02, lon + 0.02)
            & nodes["latitude"].between(lat - 0.02, lat + 0.02)
        ]
        ids = set(near_nodes["node_id"].astype("int64"))
        cand = edges[edges["u"].isin(ids) & edges["v"].isin(ids)].copy()
        if cand.empty:
            raise RuntimeError(f"No primary road candidates near {name}")

        px, py = transformer.transform(lon, lat)
        point = Point(px, py)
        best: tuple[float, float, pd.Series] | None = None
        for _, edge in cand.iterrows():
            u = int(edge["u"])
            v = int(edge["v"])
            if u not in node_lookup.index or v not in node_lookup.index:
                continue
            nu = node_lookup.loc[u]
            nv = node_lookup.loc[v]
            x1, y1 = transformer.transform(float(nu["longitude"]), float(nu["latitude"]))
            x2, y2 = transformer.transform(float(nv["longitude"]), float(nv["latitude"]))
            line = LineString([(x1, y1), (x2, y2)])
            if line.length <= 0:
                continue
            distance = float(point.distance(line))
            frac = float(line.project(point) / line.length)
            if best is None or distance < best[0]:
                best = (distance, frac, edge)

        if best is None:
            raise RuntimeError(f"Could not locate a primary road segment for {name}")
        distance, frac, edge = best
        # This is a reproducibility equality check against the prior independent audit,
        # not a statewide cutoff. For all three validated terminals the match is exact
        # to floating-point precision and is sub-metre by the upstream evidence.
        if abs(distance - audited_distance) > 1e-6:
            raise RuntimeError(
                f"Nearest primary road segment for {name} does not reproduce audited distance: "
                f"computed={distance}, audited={audited_distance}"
            )
        if not (0.0 < frac < 1.0):
            raise RuntimeError(f"Terminal projection is not internal to the source edge for {name}")

        source_time = float(edge["travel_time_min"])
        source_length = float(edge["length_m"])
        if not (source_time > 0 and source_length > 0):
            raise RuntimeError(f"Invalid source edge impedance for {name}")
        first_time = source_time * frac
        second_time = source_time * (1.0 - frac)
        first_length = source_length * frac
        second_length = source_length * (1.0 - frac)
        terminal_node_id = f"terminal:{str(pr['anchor_id'])}"

        out_rows.append({
            "anchor_id": str(pr["anchor_id"]),
            "port_name": name,
            "terminal_node_id": terminal_node_id,
            "hydro_node_id": str(pr["hydro_node_id"]),
            "source_way_id": int(edge["way_id"]),
            "source_u": int(edge["u"]),
            "source_v": int(edge["v"]),
            "source_highway": str(edge["highway"]),
            "source_oneway": edge.get("oneway"),
            "source_junction": edge.get("junction"),
            "road_distance_m_reproduced": distance,
            "road_distance_m_audited": audited_distance,
            "projection_fraction_u_to_v": frac,
            "source_length_m": source_length,
            "source_travel_time_min": source_time,
            "u_to_terminal_length_m": first_length,
            "terminal_to_v_length_m": second_length,
            "u_to_terminal_time_min": first_time,
            "terminal_to_v_time_min": second_time,
            "split_length_conservation_error_m": (first_length + second_length) - source_length,
            "split_time_conservation_error_min": (first_time + second_time) - source_time,
            "road_terminal_attachment_role": "structural_insertion_into_validated_primary_road_edge",
            "creates_connector_edge": False,
            "zero_time_edge_created": False,
            "cartographic_offset_interpreted_as_physical_travel": False,
            "new_speed_assumption_used": False,
        })

    out = pd.DataFrame(out_rows)
    out.to_csv(args.output_dir / "intermodal_terminal_road_edge_splits.csv", index=False)
    audit = {
        "terminal_count": int(len(out)),
        "terminal_names": out["port_name"].tolist(),
        "audited_road_distance_reproduced_all": bool((out["road_distance_m_reproduced"] - out["road_distance_m_audited"]).abs().le(1e-6).all()),
        "source_edges_unique": int(out[["source_u", "source_v", "source_way_id"]].drop_duplicates().shape[0]),
        "split_time_conservation_max_abs_error_min": float(out["split_time_conservation_error_min"].abs().max()),
        "split_length_conservation_max_abs_error_m": float(out["split_length_conservation_error_m"].abs().max()),
        "creates_connector_edge": False,
        "zero_time_edge_created": False,
        "cartographic_offset_interpreted_as_physical_travel": False,
        "new_speed_assumption_used": False,
        "ready_for_multimodal_graph_union": True,
        "scientific_policy": (
            "Each validated ANTAQ terminal is inserted structurally into the exact primary OSM road segment that reproduces its independently audited sub-metre road distance. "
            "The source road segment is split at the terminal projection and its already validated free-flow impedance is partitioned proportionally, conserving the original segment time exactly. "
            "No terminal-to-road connector edge is created, no cartographic offset is converted to physical travel time, and no new speed assumption is introduced. "
            "The same terminal identity is linked semantically to the previously validated official ANTAQ hydro endpoint."
        ),
    }
    (args.output_dir / "intermodal_terminal_road_edge_splits_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
