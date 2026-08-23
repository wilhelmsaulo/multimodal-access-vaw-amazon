from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--local-access", type=Path, default=Path("artifacts/local_access_primary_motor_audit/origin_local_access_to_primary_motor.csv.gz"))
    p.add_argument("--origin-semantics", type=Path, default=Path("artifacts/access_connector_semantics/origin_access_connector_semantics.csv.gz"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/origin_network_access_evidence"))
    args = p.parse_args()

    local = pd.read_csv(args.local_access, low_memory=False)
    sem = pd.read_csv(args.origin_semantics, low_memory=False)
    keep = [c for c in ["origin_id", "distance_to_road_m", "distance_to_waterway_m"] if c in sem.columns]
    x = local.merge(sem[keep], on="origin_id", how="left", validate="one_to_one")

    direct = x["nearest_osm_node_in_primary_motor_graph"].fillna(False).astype(bool)
    connected = x["local_osm_topologically_connected_to_primary_motor"].fillna(False).astype(bool)
    residual = ~connected
    hydro_closer = (
        pd.to_numeric(x["distance_to_waterway_m"], errors="coerce")
        < pd.to_numeric(x["distance_to_road_m"], errors="coerce")
    ).fillna(False)

    x["origin_access_evidence_class"] = np.select(
        [direct, (~direct) & connected, residual & hydro_closer],
        [
            "nearest_local_osm_node_in_primary_motor_graph",
            "local_osm_topology_connects_to_primary_motor",
            "residual_hydro_priority_candidate",
        ],
        default="residual_unresolved_network_gap",
    )
    x["temporal_access_connector_promoted"] = False
    x["euclidean_distance_converted_to_time"] = False
    x["hydro_candidate_promoted_by_distance"] = False

    args.output_dir.mkdir(parents=True, exist_ok=True)
    x.to_csv(args.output_dir / "origin_network_access_evidence.csv.gz", index=False, compression="gzip")

    female = pd.to_numeric(x.get("female_population"), errors="coerce")
    water = pd.to_numeric(x["distance_to_waterway_m"], errors="coerce")
    residual_mask = x["origin_access_evidence_class"].str.startswith("residual_")
    counts = x["origin_access_evidence_class"].value_counts().to_dict()
    female_by_class = {
        k: float(female[x["origin_access_evidence_class"] == k].sum())
        for k in counts
    }
    audit = {
        "origin_count": int(len(x)),
        "evidence_class_counts": {str(k): int(v) for k, v in counts.items()},
        "female_population_by_evidence_class": female_by_class,
        "residual_origin_count": int(residual_mask.sum()),
        "residual_female_population": float(female[residual_mask].sum()),
        "residual_hydro_closer_than_road_count": int((residual_mask & hydro_closer).sum()),
        "residual_hydro_distance_descriptive_counts": {
            "within_1km": int((residual_mask & (water <= 1000)).sum()),
            "within_5km": int((residual_mask & (water <= 5000)).sum()),
            "within_10km": int((residual_mask & (water <= 10000)).sum()),
        },
        "distance_threshold_used_for_promotion": False,
        "hydro_candidate_promoted_by_distance": False,
        "euclidean_distance_converted_to_time": False,
        "walking_speed_assigned": False,
        "track_speed_assigned": False,
        "origin_access_temporal_connector_rule_resolved": False,
        "scientific_policy": (
            "Origins are classified by observed OSM topology, not by a statewide distance cutoff. "
            "Origins whose nearest local OSM node belongs to the primary motor graph are distinguished from origins that require an actual local OSM path to reach that graph. "
            "Origins with no OSM-topological connection to the primary motor graph remain explicit residual cases; waterway proximity is used only to prioritize hydro-access investigation, never to promote a connector or convert Euclidean distance to time."
        ),
    }
    (args.output_dir / "origin_network_access_evidence_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
