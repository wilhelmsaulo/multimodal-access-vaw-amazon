from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def summary(x: pd.Series) -> dict:
    v = pd.to_numeric(x, errors="coerce").dropna().to_numpy(dtype=float)
    if not len(v):
        return {"n": 0}
    return {
        "n": int(len(v)),
        "min_m": float(np.min(v)),
        "median_m": float(np.median(v)),
        "p75_m": float(np.quantile(v, .75)),
        "p90_m": float(np.quantile(v, .90)),
        "p95_m": float(np.quantile(v, .95)),
        "p99_m": float(np.quantile(v, .99)),
        "max_m": float(np.max(v)),
    }


def main() -> None:
    origin = pd.read_csv(
        "artifacts/origin_network_access_evidence/origin_network_access_evidence.csv.gz",
        low_memory=False,
    )
    alignment = pd.read_csv(
        "artifacts/empirical_origin_cartographic_alignment/empirical_origin_cartographic_alignment.csv.gz",
        low_memory=False,
        usecols=[
            "origin_id",
            "any_nominal_match_same_municipality",
            "distance_to_any_same_name_osm_m",
            "empirical_local_cartographic_alignment",
        ],
    )

    direct = origin[origin["nearest_osm_node_in_primary_motor_graph"].astype(bool)].copy()
    if len(direct) != 14306:
        raise ValueError(f"Expected 14306 direct-primary origins, found {len(direct)}")

    x = direct.merge(alignment, on="origin_id", how="left")
    local = x["empirical_local_cartographic_alignment"].fillna(False).astype(bool)
    has_meta = x["any_nominal_match_same_municipality"].notna()
    any_match = x["any_nominal_match_same_municipality"].fillna(False).astype(bool)

    x["attachment_evidence_group"] = np.select(
        [local, ~has_meta, has_meta & ~any_match, has_meta & any_match & ~local],
        [
            "validated_local_nominal_positive_control",
            "no_recovered_cnefe_street_metadata",
            "cnefe_metadata_without_same_name_osm_match",
            "same_name_osm_match_outside_local_regime",
        ],
        default="unexpected",
    )

    controls = x.loc[local, "distance_to_nearest_osm_node_m"].astype(float).to_numpy()
    if len(controls) != 4368:
        raise ValueError(f"Expected 4368 positive controls, found {len(controls)}")
    controls_sorted = np.sort(controls)

    # Descriptive empirical support only: percentile position in validated-control ECDF.
    d = x["distance_to_nearest_osm_node_m"].astype(float).to_numpy()
    x["validated_control_ecdf_at_nearest_node_distance"] = np.searchsorted(controls_sorted, d, side="right") / len(controls_sorted)
    x["within_observed_positive_control_distance_range"] = d <= controls_sorted[-1]

    unvalidated = ~local
    outdir = Path("artifacts/direct_origin_attachment_transferability")
    outdir.mkdir(parents=True, exist_ok=True)
    x.to_csv(outdir / "direct_origin_attachment_transferability.csv.gz", index=False, compression="gzip")

    by_group = {}
    for group, g in x.groupby("attachment_evidence_group"):
        by_group[str(group)] = {
            "count": int(len(g)),
            "nearest_node_distance_m": summary(g["distance_to_nearest_osm_node_m"]),
            "within_observed_positive_control_distance_range_count": int(g["within_observed_positive_control_distance_range"].sum()),
            "within_observed_positive_control_distance_range_fraction": float(g["within_observed_positive_control_distance_range"].mean()),
        }

    audit = {
        "direct_primary_origin_count": int(len(x)),
        "validated_positive_control_count": int(local.sum()),
        "direct_primary_without_local_nominal_validation_count": int(unvalidated.sum()),
        "positive_control_nearest_node_distance_m": summary(pd.Series(controls)),
        "unvalidated_within_observed_positive_control_distance_range_count": int(x.loc[unvalidated, "within_observed_positive_control_distance_range"].sum()),
        "unvalidated_within_observed_positive_control_distance_range_fraction": float(x.loc[unvalidated, "within_observed_positive_control_distance_range"].mean()),
        "evidence_groups": by_group,
        "positive_control_range_is_routing_cutoff": False,
        "ecdf_used_for_connector_promotion": False,
        "connector_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "Validated local nominal CNEFE-OSM alignments already attached to the primary motor graph are used as positive controls to describe the empirical distribution of origin-to-nearest-OSM-node distances. "
            "For other direct-primary origins, the control ECDF and whether their distance falls inside the observed positive-control support range are diagnostic transferability evidence only. "
            "Neither the positive-control maximum nor any ECDF percentile is adopted as a routing cutoff; no connector or travel time is assigned by this audit."
        ),
    }
    (outdir / "direct_origin_attachment_transferability_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
