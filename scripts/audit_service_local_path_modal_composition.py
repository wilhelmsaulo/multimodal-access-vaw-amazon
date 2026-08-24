from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

PEDESTRIAN_CLASSES = {"footway", "path", "pedestrian", "steps", "cycleway"}


def main() -> None:
    local = pd.read_csv("artifacts/service_local_access_primary_motor_audit/service_local_access_to_primary_motor.csv.gz", low_memory=False)
    nodes = pd.read_csv("artifacts/transport_topology/road_nodes.csv.gz", usecols=["node_id"])
    motor = pd.read_csv("artifacts/primary_motor_road_times_complete/primary_motor_edges_with_complete_times.csv.gz", usecols=["u", "v"])
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

    for chunk in pd.read_csv("artifacts/transport_topology/road_edges.csv.gz", usecols=["u", "v", "highway", "length_m"], chunksize=500_000):
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
    rows_out = []
    for r in target.itertuples(index=False):
        cur = non_index[int(r.nearest_osm_node_id)]
        classes: list[str] = []
        while cur != source:
            parent = int(pred[cur])
            if parent == -9999:
                raise RuntimeError(f"Missing predecessor for service {r.service_id}")
            if parent == source:
                classes.append(str(boundary_class[cur]) or "unknown_boundary")
                cur = parent
                continue
            a, b = int(non_ids[cur]), int(non_ids[parent])
            meta = pair_meta.get((min(a, b), max(a, b)))
            classes.append(meta[1] if meta else "unknown")
            cur = parent
        toks = sorted(set(classes))
        uses_track = "track" in toks
        only_ped = bool(toks) and all(x in PEDESTRIAN_CLASSES for x in toks)
        cls = "mixed_or_other_local_osm_path"
        if uses_track:
            cls = "track_involved_sensitivity_only"
        elif only_ped:
            cls = "exclusively_pedestrian_osm_path"
        rows_out.append({
            "service_id": r.service_id,
            "service_type": getattr(r, "service_type", None),
            "municipality_name": getattr(r, "municipality_name", None),
            "local_osm_path_distance_to_primary_motor_m": r.local_osm_path_distance_to_primary_motor_m,
            "path_highway_classes": "|".join(toks),
            "service_local_path_evidence_class": cls,
        })

    out = pd.DataFrame(rows_out)
    if len(out) != 8:
        raise RuntimeError(f"Expected 8 connected non-primary service sites, found {len(out)}")
    output_dir = Path("artifacts/service_local_path_modal_composition")
    output_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_dir / "service_local_path_modal_composition.csv.gz", index=False, compression="gzip")

    audit = {
        "service_local_path_sites": int(len(out)),
        "evidence_class_counts": {str(k): int(v) for k, v in out["service_local_path_evidence_class"].value_counts().to_dict().items()},
        "path_class_combinations": {str(k): int(v) for k, v in out["path_highway_classes"].value_counts().to_dict().items()},
        "walking_speed_assigned": False,
        "track_speed_assigned": False,
        "travel_time_assigned": False,
        "service_access_temporal_connector_rule_resolved": False,
        "scientific_policy": "The eight service sites requiring a real local OSM path are classified by the actual shortest-path highway composition. Pedestrian-only, track-involved, and mixed/other paths remain distinct; no speed or time is assigned by this audit."
    }
    (output_dir / "service_local_path_modal_composition_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
