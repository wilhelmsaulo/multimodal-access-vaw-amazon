from __future__ import annotations

"""Create a revised accessibility-candidate matrix for pre-MCDM audit.

This step preserves structural non-coverage instead of imputing travel time,
restores the full 144-municipality Pará universe when Afuá is absent from the
routing-ready origin artifact, and removes deterministic/highly redundant
accessibility variables from the candidate set. The output is not yet the full
MCDM matrix; it contains only candidate accessibility criteria.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

AFUA_CODE = "1500305"
AFUA_NAME = "Afuá"


def revise(input_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, dtype={"municipality_code": str})
    df["municipality_code"] = df["municipality_code"].astype(str).str.zfill(7)

    if df["municipality_code"].duplicated().any():
        raise RuntimeError("Duplicate municipality_code in municipal accessibility matrix")
    if len(df) != 143:
        raise RuntimeError(f"Expected 143 municipalities before universe restoration, got {len(df)}")
    if AFUA_CODE in set(df["municipality_code"]):
        raise RuntimeError("Afuá unexpectedly present; review the restoration rule before proceeding")

    # Afuá is part of the official IBGE Pará municipality universe but has no
    # primary routing-ready origin in the frozen Stage 2 endpoint artifact.
    # This is represented as structural non-coverage, not as zero accessibility.
    afua = {c: np.nan for c in df.columns}
    afua.update({
        "municipality_code": AFUA_CODE,
        "municipality_name": AFUA_NAME,
        "reference_year": 2022,
        "reference_date": "2026-08-26",
        "source": "IBGE municipality universe; no primary routing-ready origin in frozen Stage 2 endpoints",
        "routing_ready_origin_count": 0,
        "female_population_routing_ready": 0.0,
        "female_population_missing_origin_count": np.nan,
        "population_weighted": False,
    })
    df = pd.concat([df, pd.DataFrame([afua])], ignore_index=True)

    # Distinguish network representation failure from true routing disconnection.
    no_origin = df["routing_ready_origin_count"].fillna(0).eq(0)
    no_reachable = (~no_origin) & df["reachable_service_fraction"].fillna(0).eq(0)
    df["accessibility_coverage_status"] = "routing_ready_reachable"
    df.loc[no_reachable, "accessibility_coverage_status"] = "routing_ready_no_reachable_service"
    df.loc[no_origin, "accessibility_coverage_status"] = "no_primary_routing_ready_origin"

    # Candidate criteria retained after the first redundancy/VIF audit.
    # - unreachable_service_fraction is removed because it is exactly 1-reachable.
    # - 60/180 min shares and p90 are retained only in the diagnostic source matrix;
    #   the 120-min share is the central threshold candidate and can later be tested
    #   in sensitivity analysis against 60/180 min.
    # - routing counts/population are diagnostics, not accessibility criteria.
    candidate_map = {
        "reachable_service_fraction": "criterion__reachable_service_fraction",
        "services_within_120_fraction": "criterion__services_within_120_fraction",
        "nearest_reachable_service_time_min": "criterion__nearest_reachable_service_time_min",
        "median_reachable_service_time_min": "criterion__median_reachable_service_time_min",
    }

    out = df[[
        "municipality_code", "municipality_name", "reference_year", "reference_date",
        "source", "accessibility_coverage_status",
    ]].copy()
    for src, dst in candidate_map.items():
        out[dst] = pd.to_numeric(df[src], errors="coerce")

    # No travel-time imputation: Afuá and routing-disconnected municipalities keep
    # undefined time criteria. Zero reachability for routing-ready disconnected
    # municipalities is observed/model-derived and is retained as zero.
    out.loc[no_origin, [
        "criterion__reachable_service_fraction",
        "criterion__services_within_120_fraction",
        "criterion__nearest_reachable_service_time_min",
        "criterion__median_reachable_service_time_min",
    ]] = np.nan

    out = out.sort_values("municipality_code").reset_index(drop=True)
    if len(out) != 144 or out["municipality_code"].nunique() != 144:
        raise RuntimeError("Revised matrix does not contain exactly 144 unique Pará municipalities")

    path = out_dir / "municipal_accessibility_candidates_revised.csv"
    out.to_csv(path, index=False)

    counts = out["accessibility_coverage_status"].value_counts().to_dict()
    audit = {
        "stage": "Stage 3 accessibility candidate revision",
        "municipalities": 144,
        "restored_municipality": {"code": AFUA_CODE, "name": AFUA_NAME},
        "restoration_reason": "Official IBGE municipality universe member absent because no primary routing-ready origin exists in frozen Stage 2 endpoints.",
        "coverage_status_counts": {str(k): int(v) for k, v in counts.items()},
        "candidate_criteria": list(candidate_map.values()),
        "deterministic_redundancy_removed": ["unreachable_service_fraction"],
        "diagnostic_only_not_core_candidates": [
            "routing_ready_origin_count", "female_population_routing_ready",
            "services_within_60_fraction", "services_within_180_fraction",
            "p90_reachable_service_time_min",
        ],
        "threshold_policy": "120-minute share retained as central candidate; 60/180-minute shares reserved for sensitivity analysis.",
        "unreachable_time_imputed": False,
        "no_origin_accessibility_imputed": False,
        "complete_mcdm_matrix": False,
        "next_requirement": "Join audited non-transport indicators, then rerun full-matrix statistical and temporal-compatibility audit before MCDM.",
        "output": str(path),
    }
    (out_dir / "municipal_accessibility_candidates_revised_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return audit


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--out", type=Path, default=Path("artifacts/stage3_revised"))
    args = p.parse_args()
    revise(args.input, args.out)


if __name__ == "__main__":
    main()
