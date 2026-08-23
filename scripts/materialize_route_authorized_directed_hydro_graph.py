from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

TOPO_EDGES = Path("artifacts/hydro_topology_with_validated_snaps/hydro_topology_edges.gpkg")
TOPO_NODES = Path("artifacts/hydro_topology_with_validated_snaps/hydro_topology_nodes.gpkg")
ATTACHMENTS = Path("artifacts/hydro_topology_with_validated_snaps/validated_anchor_hydro_node_attachments.csv")
ORIENTATION = Path("artifacts/hydro_endpoint_municipality_orientation/hydro_route_endpoint_orientation.csv")
ORIENTATION_AUDIT = Path("artifacts/hydro_endpoint_municipality_orientation/hydro_endpoint_municipality_orientation_audit.json")
OUT = Path("artifacts/route_authorized_directed_hydro_graph")
TIME_TOL_MIN = 1e-9


def reverse_linestring(geom):
    if not isinstance(geom, LineString):
        raise RuntimeError(f"Expected LineString topology edge, got {type(geom).__name__}")
    return LineString(list(geom.coords)[::-1])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    edges = gpd.read_file(TOPO_EDGES, layer="hydro_topology_edges")
    nodes = gpd.read_file(TOPO_NODES, layer="hydro_topology_nodes")
    attachments = pd.read_csv(ATTACHMENTS)
    orientation = pd.read_csv(ORIENTATION)
    orientation_audit = json.loads(ORIENTATION_AUDIT.read_text(encoding="utf-8"))

    if orientation_audit.get("ready_for_route_specific_directional_materialization") is not True:
        raise RuntimeError("Route-specific direction authorization is not ready")
    if orientation_audit.get("statewide_geometry_order_validated") is not False:
        raise RuntimeError("Statewide geometry direction must not be assumed")
    if orientation_audit.get("automatic_reverse_edge_creation_used") is not False:
        raise RuntimeError("Synthetic reverse edges must not be used")

    required_edge_cols = {"route_key", "route_index", "travel_time_min", "from_node", "to_node", "geometry"}
    missing = required_edge_cols - set(edges.columns)
    if missing:
        raise RuntimeError(f"Missing topology edge columns: {sorted(missing)}")

    auth = orientation.loc[
        orientation["orientation_class"].isin(["forward_consistent", "reverse_consistent"]),
        ["route_index", "hydro_id", "orientation_class", "directed_geometry_use", "travel_time_min"],
    ].copy()
    auth["route_index"] = auth["route_index"].astype(int)
    if len(auth) != int(orientation_audit["route_specific_direction_authorized_count"]):
        raise RuntimeError("Authorized route count disagrees with orientation audit")

    auth_map = auth.set_index("route_index")["orientation_class"].to_dict()
    directed = edges.loc[edges["route_index"].astype(int).isin(auth_map)].copy()
    if directed.empty:
        raise RuntimeError("No authorized topology edges found")

    directed["orientation_class"] = directed["route_index"].astype(int).map(auth_map)
    reverse_mask = directed["orientation_class"].eq("reverse_consistent")

    # Reverse only the authorized records whose endpoint evidence shows that stored
    # geometry order is destination→origin. This is not creation of a return edge.
    old_from = directed.loc[reverse_mask, "from_node"].copy()
    directed.loc[reverse_mask, "from_node"] = directed.loc[reverse_mask, "to_node"].values
    directed.loc[reverse_mask, "to_node"] = old_from.values
    directed.loc[reverse_mask, "geometry"] = directed.loc[reverse_mask, "geometry"].map(reverse_linestring)

    directed["direction_authorization_source"] = "ibge_2023_exact_endpoint_municipality_coverage"
    directed["synthetic_reverse_edge"] = False
    directed["waiting_time_included"] = False
    directed["statewide_direction_assumption"] = False

    # Route-level time conservation must remain exact after orientation.
    topo_sums = edges.groupby("route_index", as_index=False)["travel_time_min"].sum().rename(
        columns={"travel_time_min": "topology_time_min"}
    )
    directed_sums = directed.groupby("route_index", as_index=False)["travel_time_min"].sum().rename(
        columns={"travel_time_min": "directed_time_min"}
    )
    time_check = auth[["route_index", "orientation_class"]].merge(topo_sums, on="route_index", how="left").merge(
        directed_sums, on="route_index", how="left"
    )
    time_check["absolute_time_error_min"] = (time_check["directed_time_min"] - time_check["topology_time_min"]).abs()
    time_check["time_conserved"] = time_check["absolute_time_error_min"] <= TIME_TOL_MIN
    if not time_check["time_conserved"].all():
        bad = time_check.loc[~time_check["time_conserved"]]
        raise RuntimeError(f"Directed graph changed authorized route time:\n{bad.to_string(index=False)}")

    authorized_route_indices = set(auth["route_index"].astype(int))
    node_ids = set(directed["from_node"]) | set(directed["to_node"])
    directed_nodes = nodes.loc[nodes["node_id"].isin(node_ids)].copy()

    attachments = attachments.copy()
    # route_key is sufficient to map each anchor to its source route index.
    route_index_by_key = edges[["route_key", "route_index"]].drop_duplicates().set_index("route_key")["route_index"].to_dict()
    attachments["route_index"] = attachments["route_key"].map(route_index_by_key)
    attachments["direction_authorized_for_routing"] = attachments["route_index"].map(
        lambda x: int(x) in authorized_route_indices if pd.notna(x) else False
    )
    attachments["orientation_class"] = attachments["route_index"].map(
        lambda x: auth_map.get(int(x)) if pd.notna(x) else None
    )

    authorized_route_count = len(authorized_route_indices)
    total_route_count = int(orientation_audit["official_routes_total"])
    authorized_topology_edges = len(directed)
    total_topology_edges = len(edges)
    authorized_time_sum = float(directed["travel_time_min"].sum())
    total_time_sum = float(edges["travel_time_min"].sum())
    authorized_length_sum = float(directed["edge_length_m"].sum())
    total_length_sum = float(edges["edge_length_m"].sum())
    anchor_authorized_count = int(attachments["direction_authorized_for_routing"].sum())

    directed.to_file(OUT / "directed_hydro_edges.gpkg", layer="directed_hydro_edges", driver="GPKG")
    directed_nodes.to_file(OUT / "directed_hydro_nodes.gpkg", layer="directed_hydro_nodes", driver="GPKG")
    time_check.to_csv(OUT / "directed_hydro_route_time_conservation.csv", index=False)
    attachments.to_csv(OUT / "validated_anchor_directional_coverage.csv", index=False)
    orientation.to_csv(OUT / "hydro_route_direction_authorization_inventory.csv", index=False)

    audit = {
        "official_routes_total": total_route_count,
        "direction_authorized_routes": authorized_route_count,
        "direction_authorized_route_fraction": authorized_route_count / total_route_count,
        "forward_consistent_routes": int((auth["orientation_class"] == "forward_consistent").sum()),
        "reverse_consistent_routes": int((auth["orientation_class"] == "reverse_consistent").sum()),
        "unresolved_routes_excluded": total_route_count - authorized_route_count,
        "topology_edges_total": total_topology_edges,
        "directed_authorized_edges": authorized_topology_edges,
        "directed_authorized_edge_fraction": authorized_topology_edges / total_topology_edges,
        "directed_authorized_length_fraction": authorized_length_sum / total_length_sum if total_length_sum else None,
        "directed_authorized_reference_time_fraction": authorized_time_sum / total_time_sum if total_time_sum else None,
        "directed_nodes_total": int(len(directed_nodes)),
        "route_time_conservation_fraction": float(time_check["time_conserved"].mean()),
        "max_route_time_conservation_error_min": float(time_check["absolute_time_error_min"].max()),
        "validated_snap_anchor_count": int(len(attachments)),
        "validated_snap_anchors_on_direction_authorized_routes": anchor_authorized_count,
        "validated_snap_anchor_directional_coverage_fraction": anchor_authorized_count / len(attachments) if len(attachments) else None,
        "statewide_direction_assumption_used": False,
        "synthetic_reverse_edges_created": False,
        "same_municipality_routes_promoted": False,
        "unresolved_routes_promoted": False,
        "waiting_time_included": False,
        "ready_for_restricted_directed_hydro_routing": True,
        "ready_for_statewide_directed_hydro_routing": False,
        "scientific_policy": (
            "The restricted directed hydro graph contains only ANTAQ route records whose geometry direction is individually authorized by exact endpoint coverage against official IBGE 2023 Pará municipality polygons. Forward-consistent records retain stored order; reverse-consistent records are explicitly reoriented without creating a synthetic return edge. Unresolved records remain unavailable for directed routing. Official route reference times are conserved exactly and waiting is excluded."
        ),
        "next_required_step": (
            "Evaluate whether route, length, reference-time, and validated-anchor coverage of this restricted directed graph are sufficient for the primary statewide analysis. If not, obtain additional official direction evidence for unresolved routes rather than extrapolating direction."
        ),
    }
    (OUT / "route_authorized_directed_hydro_graph_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(attachments[["port_name", "route_key", "route_index", "orientation_class", "direction_authorized_for_routing"]].to_string(index=False))


if __name__ == "__main__":
    main()
