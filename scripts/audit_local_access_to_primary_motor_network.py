from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

DISTANCE_CRS = "EPSG:5880"
GEOGRAPHIC_CRS = "EPSG:4674"


def summary(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    return {
        "n": int(x.size),
        "median_m": float(np.median(x)),
        "p90_m": float(np.quantile(x, 0.90)),
        "p95_m": float(np.quantile(x, 0.95)),
        "p99_m": float(np.quantile(x, 0.99)),
        "max_m": float(np.max(x)),
    }


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
    motor_nodes = nodes[nodes["node_id"].isin(motor_ids)].copy()

    tr = Transformer.from_crs(GEOGRAPHIC_CRS, DISTANCE_CRS, always_xy=True)
    ox, oy = tr.transform(origins["longitude"].to_numpy(), origins["latitude"].to_numpy())
    ax, ay = tr.transform(nodes["longitude"].to_numpy(), nodes["latitude"].to_numpy())
    mx, my = tr.transform(motor_nodes["longitude"].to_numpy(), motor_nodes["latitude"].to_numpy())

    all_tree = cKDTree(np.c_[ax, ay])
    motor_tree = cKDTree(np.c_[mx, my])
    all_dist, all_idx = all_tree.query(np.c_[ox, oy], workers=-1)
    motor_dist, motor_idx = motor_tree.query(np.c_[ox, oy], workers=-1)
    nearest_all_ids = nodes["node_id"].to_numpy()[all_idx]
    nearest_is_motor = pd.Index(nearest_all_ids).isin(motor_ids)

    nonmotor_nearest_ids = set(nearest_all_ids[~nearest_is_motor].tolist())
    incident: dict[int, set[str]] = defaultdict(set)
    if nonmotor_nearest_ids:
        for chunk in pd.read_csv(args.road_edges, usecols=["u", "v", "highway"], chunksize=500_000):
            sub = chunk[chunk["u"].isin(nonmotor_nearest_ids) | chunk["v"].isin(nonmotor_nearest_ids)]
            for r in sub.itertuples(index=False):
                hw = str(r.highway)
                if r.u in nonmotor_nearest_ids:
                    incident[int(r.u)].add(hw)
                if r.v in nonmotor_nearest_ids:
                    incident[int(r.v)].add(hw)
    class_counts = Counter("|".join(sorted(v)) for v in incident.values())

    out = origins[[c for c in ["origin_id", "municipality_code", "municipality_name", "female_population", "origin_method", "origin_validation_status"] if c in origins.columns]].copy()
    out["distance_to_nearest_osm_node_m"] = all_dist
    out["nearest_osm_node_id"] = nearest_all_ids
    out["nearest_osm_node_in_primary_motor_graph"] = nearest_is_motor
    out["distance_to_nearest_primary_motor_node_m"] = motor_dist
    out["nearest_primary_motor_node_id"] = motor_nodes["node_id"].to_numpy()[motor_idx]
    out["nearest_nonmotor_incident_highway_classes"] = ["" if flag else "|".join(sorted(incident.get(int(nid), set()))) for nid, flag in zip(nearest_all_ids, nearest_is_motor)]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output_dir / "origin_local_access_to_primary_motor.csv.gz", index=False, compression="gzip")

    audit = {
        "origin_count": int(len(out)),
        "primary_motor_node_count": int(len(motor_nodes)),
        "nearest_osm_node_already_in_primary_motor_graph": int(nearest_is_motor.sum()),
        "nearest_osm_node_not_in_primary_motor_graph": int((~nearest_is_motor).sum()),
        "nearest_osm_node_already_in_primary_motor_fraction": float(nearest_is_motor.mean()),
        "distance_to_any_osm_node": summary(all_dist),
        "distance_to_primary_motor_node": summary(motor_dist),
        "nonmotor_nearest_node_incident_highway_class_counts": dict(class_counts.most_common()),
        "straight_line_distance_to_time_conversion_used": False,
        "walking_speed_assigned": False,
        "track_speed_assigned": False,
        "connector_rule_resolved": False,
        "scientific_policy": (
            "This audit distinguishes local OSM access topology from the temporally weighted primary motor graph. "
            "Nearest-node distances are diagnostic only and are not converted to time. Non-primary local classes are retained explicitly "
            "so pedestrian/path/track access can be modeled by network topology rather than by a statewide Euclidean connector."
        ),
    }
    (args.output_dir / "local_access_primary_motor_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
