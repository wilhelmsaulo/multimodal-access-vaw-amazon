from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

COMPARISON = Path("artifacts/front1_vs_crossing_positive_controls/front1_anchor_positive_control_comparison.csv")
ANCHORS = Path("artifacts/validated_spatial_transfer_anchors/validated_spatial_transfer_anchors.csv")
OUT = Path("artifacts/spatial_transfer_snap_rule")


def as_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().eq("true")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    comparison = pd.read_csv(COMPARISON)
    anchors = pd.read_csv(ANCHORS)

    if len(comparison) != 3 or len(anchors) != 3:
        raise RuntimeError(
            f"Expected 3 validated front-1 anchors and 3 comparisons; got {len(anchors)} and {len(comparison)}"
        )

    required_cmp = {
        "port_name",
        "municipality",
        "hydro_distance_m",
        "road_distance_m",
        "positive_control_geometry_consistent",
        "connector_rule_adopted",
        "distance_threshold_adopted",
        "zero_time_transfer_adopted",
        "distance_to_time_conversion_used",
        "routing_enabled",
    }
    missing = required_cmp.difference(comparison.columns)
    if missing:
        raise RuntimeError(f"Missing comparison columns: {sorted(missing)}")

    if not as_bool(comparison["positive_control_geometry_consistent"]).all():
        raise RuntimeError("Not all front-1 anchors are geometrically consistent with official positive controls")
    for c in (
        "connector_rule_adopted",
        "distance_threshold_adopted",
        "zero_time_transfer_adopted",
        "distance_to_time_conversion_used",
        "routing_enabled",
    ):
        if as_bool(comparison[c]).any():
            raise RuntimeError(f"Upstream safeguard violated: {c}")

    merged = anchors.merge(
        comparison[
            [
                "port_name",
                "municipality",
                "hydro_distance_m",
                "road_distance_m",
                "positive_control_geometry_consistent",
                "compatible_hydro_empirical_cdf_le",
                "nearest_hydro_empirical_cdf_le",
                "road_empirical_cdf_le",
            ]
        ],
        on=["port_name", "municipality", "hydro_distance_m", "road_distance_m"],
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != 3:
        raise RuntimeError(f"Expected 3 merged anchors, got {len(merged)}")

    merged["spatial_snap_eligible"] = True
    merged["spatial_snap_role"] = "cartographic_topology_alignment"
    merged["spatial_snap_basis"] = (
        "official_antaq_port+official_route_endpoint_match+canonical_geometry_reproducibility+"
        "official_crossing_positive_control_consistency"
    )
    merged["snap_distance_is_travel_distance"] = False
    merged["spatial_distance_threshold_used"] = False
    merged["temporal_connector_impedance_status"] = "pending_sensitivity_and_final_temporal_rule"
    merged["zero_time_transfer_adopted"] = False
    merged["distance_to_time_conversion_used"] = False
    merged["routing_enabled"] = False

    out_cols = [
        "anchor_id",
        "evidence_rank",
        "port_name",
        "municipality",
        "hydro_id",
        "river_name",
        "road_distance_m",
        "hydro_distance_m",
        "positive_control_geometry_consistent",
        "compatible_hydro_empirical_cdf_le",
        "nearest_hydro_empirical_cdf_le",
        "road_empirical_cdf_le",
        "spatial_snap_eligible",
        "spatial_snap_role",
        "spatial_snap_basis",
        "snap_distance_is_travel_distance",
        "spatial_distance_threshold_used",
        "temporal_connector_impedance_status",
        "zero_time_transfer_adopted",
        "distance_to_time_conversion_used",
        "routing_enabled",
    ]
    merged[out_cols].to_csv(OUT / "validated_spatial_snap_anchors.csv", index=False)

    summary = {
        "anchors_evaluated": int(len(merged)),
        "anchor_names": merged["port_name"].tolist(),
        "spatial_snap_eligible_count": int(merged["spatial_snap_eligible"].sum()),
        "spatial_snap_rule_adopted": True,
        "spatial_snap_rule": (
            "A validated ANTAQ port may be snapped topologically to its compatible canonical ANTAQ hydro route when "
            "the port is an official installation, municipality/UF is an official route endpoint, the matched route "
            "geometry is reproducible, and the apparent port-to-route offset is empirically consistent with official "
            "ANTAQ crossing-terminal positive controls. The snap is a cartographic topology alignment, not a modeled "
            "movement over the geometric offset."
        ),
        "universal_distance_cutoff_used": False,
        "snap_distance_interpreted_as_travel_distance": False,
        "temporal_connector_impedance_resolved": False,
        "zero_time_transfer_adopted": False,
        "distance_to_time_conversion_used": False,
        "routing_enabled": False,
        "next_required_step": "sensitivity analysis for topological snap treatment before final temporal-routing enablement",
        "sample_size_caution": (
            "The municipality-compatible official crossing positive-control sample is small (n=4). It supports "
            "geometric plausibility for these individually validated anchors, not a statewide universal distance threshold."
        ),
    }
    (OUT / "spatial_transfer_snap_rule_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(merged[out_cols].to_string(index=False))


if __name__ == "__main__":
    main()
