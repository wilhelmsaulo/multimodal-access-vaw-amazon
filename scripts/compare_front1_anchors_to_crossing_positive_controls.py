from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ANCHORS = Path("artifacts/validated_spatial_transfer_anchors/validated_spatial_transfer_anchors.csv")
CONTROLS = Path("artifacts/antaq_crossing_endpoint_positive_controls/pa_crossing_endpoints_positive_controls.csv")
OUT = Path("artifacts/front1_vs_crossing_positive_controls")


def empirical_position(value: float, reference: pd.Series) -> dict[str, object]:
    x = pd.to_numeric(reference, errors="coerce").dropna().sort_values().to_numpy(dtype=float)
    if x.size == 0:
        return {
            "n_reference": 0,
            "n_reference_le_anchor": 0,
            "n_reference_ge_anchor": 0,
            "empirical_cdf_le": None,
            "reference_min_m": None,
            "reference_median_m": None,
            "reference_max_m": None,
            "anchor_within_observed_range": None,
            "anchor_no_farther_than_reference_min": None,
        }
    return {
        "n_reference": int(x.size),
        "n_reference_le_anchor": int(np.sum(x <= value)),
        "n_reference_ge_anchor": int(np.sum(x >= value)),
        "empirical_cdf_le": float(np.mean(x <= value)),
        "reference_min_m": float(x.min()),
        "reference_median_m": float(np.median(x)),
        "reference_max_m": float(x.max()),
        "anchor_within_observed_range": bool(x.min() <= value <= x.max()),
        "anchor_no_farther_than_reference_min": bool(value <= x.min()),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    anchors = pd.read_csv(ANCHORS)
    controls = pd.read_csv(CONTROLS)

    required_anchor = {"port_name", "municipality", "hydro_distance_m", "road_distance_m"}
    required_control = {
        "endpoint_to_nearest_canonical_hydro_m",
        "endpoint_to_municipality_compatible_hydro_m",
        "endpoint_to_osm_road_m",
    }
    if not required_anchor.issubset(anchors.columns):
        raise RuntimeError(f"Missing anchor columns: {sorted(required_anchor - set(anchors.columns))}")
    if not required_control.issubset(controls.columns):
        raise RuntimeError(f"Missing control columns: {sorted(required_control - set(controls.columns))}")

    if len(anchors) != 3:
        raise RuntimeError(f"Expected 3 validated anchors, got {len(anchors)}")

    nearest_hydro = controls["endpoint_to_nearest_canonical_hydro_m"]
    compatible_hydro = controls["endpoint_to_municipality_compatible_hydro_m"]
    road = controls["endpoint_to_osm_road_m"]

    rows: list[dict[str, object]] = []
    for _, r in anchors.sort_values("evidence_rank").iterrows():
        h = float(r["hydro_distance_m"])
        rd = float(r["road_distance_m"])
        near_pos = empirical_position(h, nearest_hydro)
        compat_pos = empirical_position(h, compatible_hydro)
        road_pos = empirical_position(rd, road)

        # Evidence statement only: no cutoff, no promotion, no time conversion.
        # A candidate is described as geometrically consistent when it is not farther
        # from the hydro layer than the lower observed positive-control envelope.
        # This is not a routing rule and does not imply zero transfer time.
        hydro_consistent = bool(
            (compat_pos["n_reference"] and h <= float(compat_pos["reference_median_m"]))
            or (near_pos["n_reference"] and h <= float(near_pos["reference_median_m"]))
        )

        rows.append({
            "port_name": str(r["port_name"]),
            "municipality": str(r["municipality"]),
            "hydro_distance_m": h,
            "road_distance_m": rd,
            "nearest_hydro_reference_n": near_pos["n_reference"],
            "nearest_hydro_reference_le_anchor_n": near_pos["n_reference_le_anchor"],
            "nearest_hydro_empirical_cdf_le": near_pos["empirical_cdf_le"],
            "nearest_hydro_reference_min_m": near_pos["reference_min_m"],
            "nearest_hydro_reference_median_m": near_pos["reference_median_m"],
            "nearest_hydro_reference_max_m": near_pos["reference_max_m"],
            "compatible_hydro_reference_n": compat_pos["n_reference"],
            "compatible_hydro_reference_le_anchor_n": compat_pos["n_reference_le_anchor"],
            "compatible_hydro_empirical_cdf_le": compat_pos["empirical_cdf_le"],
            "compatible_hydro_reference_min_m": compat_pos["reference_min_m"],
            "compatible_hydro_reference_median_m": compat_pos["reference_median_m"],
            "compatible_hydro_reference_max_m": compat_pos["reference_max_m"],
            "road_reference_n": road_pos["n_reference"],
            "road_reference_le_anchor_n": road_pos["n_reference_le_anchor"],
            "road_empirical_cdf_le": road_pos["empirical_cdf_le"],
            "road_reference_min_m": road_pos["reference_min_m"],
            "road_reference_median_m": road_pos["reference_median_m"],
            "road_reference_max_m": road_pos["reference_max_m"],
            "positive_control_geometry_consistent": hydro_consistent,
            "connector_rule_adopted": False,
            "distance_threshold_adopted": False,
            "zero_time_transfer_adopted": False,
            "distance_to_time_conversion_used": False,
            "routing_enabled": False,
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "front1_anchor_positive_control_comparison.csv", index=False)

    compat = pd.to_numeric(compatible_hydro, errors="coerce").dropna()
    nearest = pd.to_numeric(nearest_hydro, errors="coerce").dropna()
    summary = {
        "anchors_compared": int(len(out)),
        "anchor_names": out["port_name"].tolist(),
        "official_positive_control_endpoints": int(len(controls)),
        "compatible_hydro_positive_controls_n": int(len(compat)),
        "nearest_hydro_positive_controls_n": int(len(nearest)),
        "compatible_hydro_reference_m": {
            "min": None if compat.empty else float(compat.min()),
            "median": None if compat.empty else float(compat.median()),
            "max": None if compat.empty else float(compat.max()),
        },
        "nearest_hydro_reference_m": {
            "min": None if nearest.empty else float(nearest.min()),
            "median": None if nearest.empty else float(nearest.median()),
            "max": None if nearest.empty else float(nearest.max()),
        },
        "geometry_consistent_count": int(out["positive_control_geometry_consistent"].sum()),
        "all_front1_geometry_consistent_with_positive_controls": bool(out["positive_control_geometry_consistent"].all()),
        "connector_rule_adopted": False,
        "distance_threshold_adopted": False,
        "zero_time_transfer_adopted": False,
        "distance_to_time_conversion_used": False,
        "routing_enabled": False,
        "sample_size_caution": "Municipality-compatible hydro positive controls are few (n=4); evidence supports geometric plausibility but is not used to estimate a temporal connector cost or a universal distance cutoff.",
        "scientific_interpretation": "Front-1 anchor distances are positioned empirically against official ANTAQ crossing endpoints. This comparison evaluates whether apparent port-to-route offsets are compatible with known official transfer-terminal geometry. It does not convert distance to time, select a threshold, or promote any connector for temporal routing.",
    }
    (OUT / "front1_anchor_positive_control_comparison_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
