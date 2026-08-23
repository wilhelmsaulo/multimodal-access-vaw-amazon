from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra


PEDESTRIAN_CLASSES = {"footway", "path", "pedestrian", "steps", "cycleway"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--local-access", type=Path, default=Path("artifacts/local_access_primary_motor_audit/origin_local_access_to_primary_motor.csv.gz"))
    p.add_argument("--road-nodes", type=Path, default=Path("artifacts/transport_topology/road_nodes.csv.gz"))
    p.add_argument("--road-edges", type=Path, default=Path("artifacts/transport_topology/road_edges.csv.gz"))
    p.add_argument("--primary-motor-edges", type=Path, default=Path("artifacts/primary_motor_road_times_complete/primary_motor_edges_with_complete_times.csv.gz"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/local_access_path_modal_composition"))
    args = p.parse_args()

    local = pd.read_csv(args.local_access, low_memory=False)
    nodes = pd.read_csv(args.road_nodes, usecols=["node_id"])
    motor = pd.read_csv(args.primary_motor_edges, usecols=["u", "v"])
    motor_ids = pd.Index(pd.unique(pd.concat([motor["u"], motor["v"]], ignore_index=True)))

    non_ids = nodes.loc[~nodes["node_id"].isin(motor_ids), "node_id"].to_numpy(dtype=np.int64)
    non_index = {int(n): i for i, n in enumerate(non_ids)}
    n_non = len(non_ids)
    source = n_non
    boundary = np.full(n_non, np.inf)
    boundary_class = np.full(n_non, "", dtype=object)
    ri: list[int] = []
    rj: list[int] = []
    rw: list[float] = []
    pair_meta: dict[tuple[int, int], tuple[float, str]] = {}

    for chunk in pd.read_csv(args.road_edges, usecols=["u", "v", "highway", "length_m"], chunksize=500_000):
        u_non = chunk["u"].isin(non_index)
        v_non = chunk["v"].isin(non_index)
        both = u_non & v_non
        if both.any():
            for r in chunk.loc[both].itertuples(index=False):
                w = float(r.length_m)
                if not np.isfinite(w) or w < 0:
                    continue
                u_id, v_id = int(r.u), int(r.v)
                ui, vi = non_index[u_id], non_index[v_id]
                ri.extend([ui, vi]); rj.extend([vi, ui]); rw.extend([w, w])
                key = (min(u_id, v_id), max(u_id, v_id))
                old = pair_meta.get(key)
                if old is None or w < old[0]:
                    pair_meta[key] = (w, str(r.highway))
        for mask, col in ((u_non & ~v_non, "u"), (~u_non & v_non, "v")):
            if mask.any():
                for r in chunk.loc[mask].itertuples(index=False):
                    node_id = int(getattr(r, col))
                    i = non_index[node_id]
                    w = float(r.length_m)
                    if np.isfinite(w) and w >= 0 and w < boundary[i]:
                        boundary[i] = w
                        boundary_class[i] = str(r.highway)

    bidx = np.flatnonzero(np.isfinite(boundary))
    rows = np.asarray(ri + bidx.tolist() + [source] * len(bidx), dtype=np.int32)
    cols = np.asarray(rj + [source] * len(bidx) + bidx.tolist(), dtype=np.int32)
    vals = np.asarray(rw + boundary[bidx].tolist() + boundary[bidx].tolist(), dtype=float)
    graph = coo_matrix((vals, (rows, cols)), shape=(n_non + 1, n_non + 1)).tocsr()
    _, pred = dijkstra(graph, directed=False, indices=source, return_predecessors=True)

    target = local[(~local["nearest_osm_node_in_primary_motor_graph"]) & local["local_osm_topologically_connected_to_primary_motor"]].copy()
    out_rows: list[dict] = []
    for r in target.itertuples(index=False):
        cur = non_index[int(r.nearest_osm_node_id)]
        classes: list[str] = []
        while cur != source:
            parent = int(pred[cur])
            if parent == -9999:
                raise RuntimeError(f"Missing predecessor for connected origin {r.origin_id}")
            if parent == source:
                classes.append(str(boundary_class[cur]) or "unknown_boundary")
                cur = parent
                continue
            a, b = int(non_ids[cur]), int(non_ids[parent])
            meta = pair_meta.get((min(a, b), max(a, b)))
            classes.append(meta[1] if meta else "unknown")
            cur = parent

        counts = Counter(classes)
        nonempty = sorted(counts)
        only_pedestrian = bool(classes) and all(c in PEDESTRIAN_CLASSES for c in classes)
        out_rows.append({
            "origin_id": r.origin_id,
            "female_population": getattr(r, "female_population", None),
            "local_osm_path_distance_to_primary_motor_m": r.local_osm_path_distance_to_primary_motor_m,
            "path_highway_classes": "|".join(nonempty),
            "path_uses_track": "track" in counts,
            "path_uses_pedestrian_class": any(c in PEDESTRIAN_CLASSES for c in counts),
            "path_exclusively_pedestrian_classes": only_pedestrian,
        })

    out = pd.DataFrame(out_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output_dir / "local_access_path_modal_composition.csv.gz", index=False, compression="gzip")

    audit = {
        "topologically_connected_local_access_origins": int(len(out)),
        "paths_using_track": int(out["path_uses_track"].sum()),
        "paths_not_using_track": int((~out["path_uses_track"]).sum()),
        "paths_using_pedestrian_class": int(out["path_uses_pedestrian_class"].sum()),
        "paths_exclusively_pedestrian_classes": int(out["path_exclusively_pedestrian_classes"].sum()),
        "walking_speed_assigned": False,
        "track_speed_assigned": False,
        "path_distance_is_osm_topological_not_euclidean": True,
        "origin_access_temporal_connector_rule_resolved": False,
        "scientific_policy": (
            "Modal composition is reconstructed on the actual shortest OSM local-access path to the primary motor graph. "
            "Pedestrian-only paths are identified separately from track and other ambiguous classes. No speed or travel time is assigned here; "
            "track remains a sensitivity-only class and no Euclidean distance is used as access travel distance."
        ),
    }
    (args.output_dir / "local_access_path_modal_composition_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
