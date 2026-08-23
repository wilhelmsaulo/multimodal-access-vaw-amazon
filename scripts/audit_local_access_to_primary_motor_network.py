from __future__ import annotations

import argparse
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
    return {"n": int(x.size), "median_m": float(np.median(x)), "p90_m": float(np.quantile(x, .90)), "p95_m": float(np.quantile(x, .95)), "p99_m": float(np.quantile(x, .99)), "max_m": float(np.max(x))}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--origins", type=Path, default=Path("artifacts/routing_inputs/origins_for_routing.csv"))
    p.add_argument("--road-nodes", type=Path, default=Path("artifacts/transport_topology/road_nodes.csv.gz"))
    p.add_argument("--road-edges", type=Path, default=Path("artifacts/transport_topology/road_edges.csv.gz"))
    p.add_argument("--primary-motor-edges", type=Path, default=Path("artifacts/primary_motor_road_times_complete/primary_motor_edges_with_complete_times.csv.gz"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/local_access_primary_motor_audit"))
    args = p.parse_args()

    origins = pd.read_csv(args.origins, low_memory=False)
    nodes = pd.read_csv(args.road_nodes)
    motor = pd.read_csv(args.primary_motor_edges, usecols=["u", "v"])
    motor_ids = pd.Index(pd.unique(pd.concat([motor["u"], motor["v"]], ignore_index=True)))
    motor_set = set(int(v) for v in motor_ids)
    motor_nodes = nodes[nodes["node_id"].isin(motor_ids)].copy()

    tr = Transformer.from_crs(GEOGRAPHIC_CRS, DISTANCE_CRS, always_xy=True)
    ox, oy = tr.transform(origins["longitude"].to_numpy(), origins["latitude"].to_numpy())
    ax, ay = tr.transform(nodes["longitude"].to_numpy(), nodes["latitude"].to_numpy())
    mx, my = tr.transform(motor_nodes["longitude"].to_numpy(), motor_nodes["latitude"].to_numpy())
    all_dist, all_idx = cKDTree(np.c_[ax, ay]).query(np.c_[ox, oy], workers=-1)
    motor_dist, motor_idx = cKDTree(np.c_[mx, my]).query(np.c_[ox, oy], workers=-1)
    nearest_all_ids = nodes["node_id"].to_numpy()[all_idx]
    nearest_is_motor = pd.Index(nearest_all_ids).isin(motor_ids)

    # Build only the non-primary part of the OSM graph plus a synthetic source
    # representing any primary-motor node. This yields actual OSM-path distance
    # from local-access nodes to the primary motor graph without Euclidean timing.
    non_nodes = nodes.loc[~nodes["node_id"].isin(motor_ids), ["node_id"]].copy()
    non_ids = non_nodes["node_id"].to_numpy()
    non_index = {int(n): i for i, n in enumerate(non_ids)}
    n_non = len(non_ids)
    boundary = np.full(n_non, np.inf)
    ri: list[int] = []
    rj: list[int] = []
    rw: list[float] = []
    incident: dict[int, set[str]] = defaultdict(set)
    target_nonmotor = set(int(n) for n in nearest_all_ids[~nearest_is_motor])

    for chunk in pd.read_csv(args.road_edges, usecols=["u", "v", "highway", "length_m"], chunksize=500_000):
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
        b1 = u_non & ~v_non
        if b1.any():
            sub = chunk.loc[b1]
            idx = sub["u"].map(non_index).to_numpy(dtype=int)
            w = pd.to_numeric(sub["length_m"], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(w) & (w >= 0)
            np.minimum.at(boundary, idx[ok], w[ok])
        b2 = ~u_non & v_non
        if b2.any():
            sub = chunk.loc[b2]
            idx = sub["v"].map(non_index).to_numpy(dtype=int)
            w = pd.to_numeric(sub["length_m"], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(w) & (w >= 0)
            np.minimum.at(boundary, idx[ok], w[ok])
        local = chunk[chunk["u"].isin(target_nonmotor) | chunk["v"].isin(target_nonmotor)]
        for r in local.itertuples(index=False):
            if int(r.u) in target_nonmotor: incident[int(r.u)].add(str(r.highway))
            if int(r.v) in target_nonmotor: incident[int(r.v)].add(str(r.highway))

    source = n_non
    bidx = np.flatnonzero(np.isfinite(boundary))
    rows = np.asarray(ri + bidx.tolist() + [source] * len(bidx), dtype=np.int32)
    cols = np.asarray(rj + [source] * len(bidx) + bidx.tolist(), dtype=np.int32)
    vals = np.asarray(rw + boundary[bidx].tolist() + boundary[bidx].tolist(), dtype=float)
    graph = coo_matrix((vals, (rows, cols)), shape=(n_non + 1, n_non + 1)).tocsr()
    to_motor = dijkstra(graph, directed=False, indices=source, return_predecessors=False)[:-1]

    local_path = np.full(len(origins), np.nan)
    local_connected = np.ones(len(origins), dtype=bool)
    non_positions = np.flatnonzero(~nearest_is_motor)
    for pos in non_positions:
        d = to_motor[non_index[int(nearest_all_ids[pos])]]
        local_path[pos] = d
        local_connected[pos] = bool(np.isfinite(d))

    classes = ["" if flag else "|".join(sorted(incident.get(int(nid), set()))) for nid, flag in zip(nearest_all_ids, nearest_is_motor)]
    out = origins[[c for c in ["origin_id", "municipality_code", "municipality_name", "female_population", "origin_method", "origin_validation_status"] if c in origins.columns]].copy()
    out["distance_to_nearest_osm_node_m"] = all_dist
    out["nearest_osm_node_id"] = nearest_all_ids
    out["nearest_osm_node_in_primary_motor_graph"] = nearest_is_motor
    out["distance_to_nearest_primary_motor_node_m"] = motor_dist
    out["nearest_primary_motor_node_id"] = motor_nodes["node_id"].to_numpy()[motor_idx]
    out["nearest_nonmotor_incident_highway_classes"] = classes
    out["local_osm_path_distance_to_primary_motor_m"] = local_path
    out["local_osm_topologically_connected_to_primary_motor"] = local_connected

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output_dir / "origin_local_access_to_primary_motor.csv.gz", index=False, compression="gzip")
    nonmotor_path = local_path[~nearest_is_motor]
    unresolved = (~nearest_is_motor) & (~local_connected)
    audit = {
        "origin_count": int(len(out)),
        "primary_motor_node_count": int(len(motor_nodes)),
        "nearest_osm_node_already_in_primary_motor_graph": int(nearest_is_motor.sum()),
        "nearest_osm_node_not_in_primary_motor_graph": int((~nearest_is_motor).sum()),
        "local_nonmotor_origins_topologically_connected_to_primary_motor": int(((~nearest_is_motor) & local_connected).sum()),
        "local_nonmotor_origins_not_connected_to_primary_motor": int(unresolved.sum()),
        "female_population_in_not_connected_group": float(pd.to_numeric(out.loc[unresolved, "female_population"], errors="coerce").sum()) if "female_population" in out else None,
        "distance_to_any_osm_node": summary(all_dist),
        "distance_to_primary_motor_node": summary(motor_dist),
        "local_osm_path_distance_to_primary_motor_for_nonmotor_origins": summary(nonmotor_path),
        "nonmotor_nearest_node_incident_highway_class_counts": dict(Counter(c for c in classes if c).most_common()),
        "straight_line_distance_to_time_conversion_used": False,
        "walking_speed_assigned": False,
        "track_speed_assigned": False,
        "connector_rule_resolved": False,
        "scientific_policy": "Local access is audited along actual OSM topology. Euclidean distances remain diagnostic only. No local path is converted to time in this audit; pedestrian and ambiguous track speeds require an explicit evidence-backed rule, while disconnected origins remain an explicit residual group rather than being silently snapped to the primary motor graph."
    }
    (args.output_dir / "local_access_primary_motor_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
