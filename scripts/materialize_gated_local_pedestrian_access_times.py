from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

WALKING_SPEED_MPS = 1.0


def main() -> None:
    attach = pd.read_csv("artifacts/local_topology_empirical_node_attachments/local_topology_empirical_node_attachments.csv.gz", dtype={"origin_id": "string"})
    modal = pd.read_csv("artifacts/local_access_path_modal_composition/local_access_path_modal_composition.csv.gz", dtype={"origin_id": "string"}, low_memory=False)

    x = attach.merge(modal, on="origin_id", how="left", validate="one_to_one")
    target = x[x["path_exclusively_pedestrian_classes"].fillna(False).astype(bool)].copy()
    if len(target) == 0:
        raise RuntimeError("No gated exclusively pedestrian local paths found")
    if target["path_uses_track"].fillna(False).astype(bool).any():
        raise RuntimeError("Track-involved path entered pedestrian temporalization")

    dist = pd.to_numeric(target["local_osm_path_distance_to_primary_motor_m"], errors="coerce")
    if dist.isna().any() or (dist < 0).any():
        raise RuntimeError("Invalid physical OSM path distance")

    out = target[["origin_id", "nearest_osm_node_id", "local_osm_path_distance_to_primary_motor_m"]].copy()
    out["walking_speed_mps"] = WALKING_SPEED_MPS
    out["pedestrian_access_time_seconds"] = dist / WALKING_SPEED_MPS
    out["pedestrian_access_time_minutes"] = out["pedestrian_access_time_seconds"] / 60.0
    out["temporalization_basis"] = "actual_exclusively_pedestrian_OSM_topological_path_after_empirical_cartographic_node_identity"
    out["cartographic_attachment_distance_converted_to_time"] = False
    out["track_speed_assigned"] = False

    outdir = Path("artifacts/gated_local_pedestrian_access_times")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "gated_local_pedestrian_access_times.csv.gz", index=False, compression="gzip")

    t = out["pedestrian_access_time_minutes"]
    audit = {
        "gated_local_pedestrian_origin_count": int(len(out)),
        "walking_speed_mps": WALKING_SPEED_MPS,
        "time_minutes": {
            "median": float(t.median()),
            "p90": float(t.quantile(.90)),
            "p95": float(t.quantile(.95)),
            "max": float(t.max()),
        },
        "uses_actual_osm_topological_path_distance": True,
        "cartographic_attachment_distance_converted_to_time": False,
        "track_speed_assigned": False,
        "straight_line_time_used": False,
        "scientific_policy": (
            "Walking time is assigned only after the origin has a gated empirical structural identity to its nearest local OSM node and only when the subsequent OSM path to the primary motor graph is exclusively pedestrian. "
            "The conservative 1 m/s walking speed is applied to the actual OSM topological path length, never to cartographic attachment or Euclidean distance."
        ),
    }
    (outdir / "gated_local_pedestrian_access_times_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
