from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

WALK_SPEED_MPS = 1.0  # 3.6 km/h, conservative evidence-backed pedestrian speed


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--classified", type=Path, default=Path("artifacts/aligned_local_path_modal_composition/aligned_local_path_modal_composition.csv.gz"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/pedestrian_local_access_times"))
    args = p.parse_args()

    df = pd.read_csv(args.classified, low_memory=False)
    ped = df[df["aligned_local_path_evidence_class"] == "exclusively_pedestrian_osm_path"].copy()
    if ped.empty:
        raise ValueError("No exclusively pedestrian aligned local paths found")

    d = pd.to_numeric(ped["local_osm_path_distance_to_primary_motor_m"], errors="coerce")
    if d.isna().any() or (d < 0).any():
        raise ValueError("Pedestrian path distances must be finite and non-negative")

    ped["pedestrian_speed_mps"] = WALK_SPEED_MPS
    ped["pedestrian_access_time_s"] = d / WALK_SPEED_MPS
    ped["pedestrian_access_time_min"] = ped["pedestrian_access_time_s"] / 60.0
    ped["temporal_role"] = "physical_osm_pedestrian_path_to_primary_motor_graph"
    ped["cartographic_attachment_time_min"] = 0.0
    ped["cartographic_attachment_role"] = "non_temporal_alignment_only"
    ped["track_speed_used"] = False

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ped.to_csv(args.output_dir / "pedestrian_local_access_times.csv.gz", index=False, compression="gzip")

    t = ped["pedestrian_access_time_min"]
    audit = {
        "pedestrian_local_access_origins": int(len(ped)),
        "walking_speed_kmh": 3.6,
        "walking_speed_mps": WALK_SPEED_MPS,
        "time_min_quantiles": {
            "min": float(t.min()),
            "median": float(t.median()),
            "p75": float(t.quantile(.75)),
            "p90": float(t.quantile(.90)),
            "p95": float(t.quantile(.95)),
            "max": float(t.max()),
        },
        "time_applied_only_to_actual_osm_topological_path": True,
        "cartographic_alignment_distance_converted_to_time": False,
        "cartographic_attachment_is_non_temporal": True,
        "track_speed_assigned": False,
        "mixed_or_other_paths_temporalized": False,
        "origin_access_temporal_connector_rule_fully_resolved": False,
        "scientific_policy": (
            "A conservative walking speed of 3.6 km/h (1.0 m/s), supported by Brazilian accessibility practice, "
            "is applied only to actual OSM shortest-path distance for origins whose local path is exclusively composed of pedestrian classes. "
            "The empirically supported CNEFE-to-OSM cartographic alignment remains non-temporal and is not converted to walking time. "
            "Mixed paths and paths involving track remain unresolved."
        ),
    }
    (args.output_dir / "pedestrian_local_access_times_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
