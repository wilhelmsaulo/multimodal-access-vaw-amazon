from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

DISTANCE_CRS = "EPSG:5880"
GEOGRAPHIC_CRS = "EPSG:4674"


def summary(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not x.size:
        return {"n": 0, "median_m": None, "p90_m": None, "p95_m": None, "p99_m": None, "max_m": None}
    return {
        "n": int(x.size),
        "median_m": float(np.median(x)),
        "p90_m": float(np.quantile(x, .90)),
        "p95_m": float(np.quantile(x, .95)),
        "p99_m": float(np.quantile(x, .99)),
        "max_m": float(np.max(x)),
    }


def main() -> None:
    destinations = pd.read_csv("artifacts/routing_inputs/destinations_for_routing.csv", low_memory=False)
    nodes = pd.read_csv("artifacts/transport_topology/road_nodes.csv.gz")
    motor = pd.read_csv(
        "artifacts/primary_motor_road_times_complete/primary_motor_edges_with_complete_times.csv.gz",
        usecols=["u", "v"],
    )
    motor_ids = pd.Index(pd.unique(pd.concat([motor["u"], motor["v"]], ignore_index=True)))
    motor_nodes = nodes[nodes["node_id"].isin(motor_ids)].copy()

    tr = Transformer.from_crs(GEOGRAPHIC_CRS, DISTANCE_CRS, always_xy=True)
    sx, sy = tr.transform(destinations["longitude"].to_numpy(), destinations["latitude"].to_numpy())
    ax, ay = tr.transform(nodes["longitude"].to_numpy(), nodes["latitude"].to_numpy())
    mx, my = tr.transform(motor_nodes["longitude"].to_numpy(), motor_nodes["latitude"].to_numpy())
    all_dist, all_idx = cKDTree(np.c_[ax, ay]).query(np.c_[sx, sy], workers=-1)
    motor_dist, motor_idx = cKDTree(np.c_[mx, my]).query(np.c_[sx, sy], workers=-1)
    nearest_all_ids = nodes["node_id"].to_numpy()[all_idx]
    nearest_is_motor = pd.Index(nearest_all_ids).isin(motor_ids)

    non_ids = nodes.loc[~nodes["node_id"].isin(motor_ids), "node_id"].to_numpy(dtype=np.int64)
    non_index = {int(n): i for i, n in enumerate(non_ids)}
    n_non = len(non_ids)
    boundary = np.full(n_non, np.inf)
    ri: list[int] = []
    rj: list[int] = []
    rw: list[float] = []
    incident: dict[int, set[str]] = defaultdict(set)
    target_nonmotor = set(int(n) for n in nearest_all_ids[~nearest_is_motor])

    for chunk in pd.read_csv(
        "artifacts/transport_topology/road_edges.csv.gz",
        usecols=["u", "v", "highway", "length_m"], chunksize=500_000,
    ):
        u_non = chunk["u"].isin(non_index)
        v_non = chunk["v"].isin(non_index)
        both = u_non & v_non
        if both.any():
            sub = chunk.loc[both]
            ui = sub["u"].map(non_index).to_numpy(dtype=int)
            vi = sub["v"].map(non_index).to_numpy(dtype=int)
            w = pd.to_numeric(sub["length_m"], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(w) & (w >= 0)
            ui, vi, w = ui[ok], vi[ok], w[ok]
            ri.extend(ui.tolist()); rj.extend(vi.tolist()); rw.extend(w.tolist())
            ri.extend(vi.tolist()); rj.extend(ui.tolist()); rw.extend(w.tolist())
        for mask, col in ((u_non & ~v_non, "u"), (~u_non & v_non, "v")):
            if mask.any():
                sub = chunk.loc[mask]
                idx = sub[col].map(non_index).to_numpy(dtype=int)
                w = pd.to_numeric(sub["length_m"], errors="coerce").to_numpy(dtype=float)
                ok = np.isfinite(w) & (w >= 0)
                np.minimum.at(boundary, idx[ok], w[ok])
        local = chunk[chunk["u"].isin(target_nonmotor) | chunk["v"].isin(target_nonmotor)]
        for r in local.itertuples(index=False):
            if int(r.u) in target_nonmotor:
                incident[int(r.u)].add(str(r.highway))
            if int(r.v) in target_nonmotor:
                incident[int(r.v)].add(str(r.highway))

    source = n_non
    bidx = np.flatnonzero(np.isfinite(boundary))
    rows = np.asarray(ri + bidx.tolist() + [source] * len(bidx), dtype=np.int32)
    cols = np.asarray(rj + [source] * len(bidx) + bidx.tolist(), dtype=np.int32)
    vals = np.asarray(rw + boundary[bidx].tolist() + boundary[bidx].tolist(), dtype=float)
    graph = coo_matrix((vals, (rows, cols)), shape=(n_non + 1, n_non + 1)).tocsr()
    to_motor = dijkstra(graph, directed=False, indices=source, return_predecessors=False)[:-1]

    local_path = np.full(len(destinations), np.nan)
    local_connected = np.ones(len(destinations), dtype=bool)
    for pos in np.flatnonzero(~nearest_is_motor):
        d = to_motor[non_index[int(nearest_all_ids[pos])]]
        local_path[pos] = d
        local_connected[pos] = bool(np.isfinite(d))

    classes = [
        "" if flag else "|".join(sorted(incident.get(int(nid), set())))
        for nid, flag in zip(nearest_all_ids, nearest_is_motor)
    ]
    keep = [c for c in ["service_id", "physical_site_id", "service_type", "municipality_code", "municipality_name", "address_public", "validation_status"] if c in destinations.columns]
    out = destinations[keep].copy()
    out["distance_to_nearest_osm_node_m"] = all_dist
    out["nearest_osm_node_id"] = nearest_all_ids
    out["nearest_osm_node_in_primary_motor_graph"] = nearest_is_motor
    out["distance_to_nearest_primary_motor_node_m"] = motor_dist
    out["nearest_primary_motor_node_id"] = motor_nodes["node_id"].to_numpy()[motor_idx]
    out["nearest_nonmotor_incident_highway_classes"] = classes
    out["local_osm_path_distance_to_primary_motor_m"] = local_path
    out["local_osm_topologically_connected_to_primary_motor"] = local_connected

    output_dir = Path("artifacts/service_local_access_primary_motor_audit")
    output_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_dir / "service_local_access_to_primary_motor.csv.gz", index=False, compression="gzip")

    unresolved = (~nearest_is_motor) & (~local_connected)
    audit = {
        "service_site_count": int(len(out)),
        "nearest_osm_node_already_in_primary_motor_graph": int(nearest_is_motor.sum()),
        "nearest_osm_node_not_in_primary_motor_graph": int((~nearest_is_motor).sum()),
        "local_nonmotor_sites_topologically_connected_to_primary_motor": int(((~nearest_is_motor) & local_connected).sum()),
        "local_nonmotor_sites_not_connected_to_primary_motor": int(unresolved.sum()),
        "distance_to_any_osm_node": summary(all_dist),
        "distance_to_primary_motor_node": summary(motor_dist),
        "local_osm_path_distance_to_primary_motor_for_nonmotor_sites": summary(local_path[~nearest_is_motor]),
        "nonmotor_nearest_node_incident_highway_class_counts": dict(Counter(c for c in classes if c).most_common()),
        "service_connector_promoted": False,
        "straight_line_distance_to_time_conversion_used": False,
        "walking_speed_assigned": False,
        "track_speed_assigned": False,
        "service_access_temporal_connector_rule_resolved": False,
        "scientific_policy": (
            "Physical service sites are audited against native OSM topology using the same conservative logic as origins. "
            "Nearest geometry alone does not authorize a connector; non-primary nearest nodes must have an actual OSM topological path to the primary motor graph. "
            "No Euclidean distance, walking speed, track speed, or travel time is assigned in this audit."
        ),
    }
    (output_dir / "service_local_access_primary_motor_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
