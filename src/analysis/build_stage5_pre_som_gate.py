from __future__ import annotations

"""Build the Stage 5 municipal candidate matrix and execute the pre-SOM quality gate.

This step does NOT train a SOM. It joins the already-audited Census 2022 profile
blocks, tests 144-municipality integrity, missingness, distributions, outliers,
correlation/redundancy and compositional constraints, and records what must be
resolved before the training feature set can be frozen.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_MUNICIPALITIES = 144
OUT = Path("results/stage5/tables")

BASE_PATH = Path("results/stage3/tables/municipal_analytical_matrix.csv")
RACE_PATH = OUT / "stage5_race_color_candidates.csv"
LITERACY_PATH = OUT / "stage5_female_literacy_candidate.csv"
INCOME_PATH = OUT / "stage5_income_candidate.csv"

AGE_FEATURES = [
    "diagnostic__female_15_29_share_age_covered",
    "diagnostic__female_30_59_share_age_covered",
    "diagnostic__female_60_plus_share_age_covered",
]
RACE_FEATURES = [
    "socio__race_share_branca",
    "socio__race_share_preta",
    "socio__race_share_parda",
    "socio__race_share_amarela",
    "socio__race_share_indigena",
]
OTHER_FEATURES = [
    "criterion__rural_female_share",
    "socio__female_literacy_rate_15plus",
    "socio__household_per_capita_income_mean_brl",
]
CANDIDATE_FEATURES = [*OTHER_FEATURES, *AGE_FEATURES, *RACE_FEATURES]
QUALITY_FIELDS = [
    "diagnostic__age_female_coverage_fraction",
    "diagnostic__race_ignored_share",
]


def read_keyed(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"municipality_code": str}, low_memory=False)
    if "municipality_code" not in frame.columns:
        raise RuntimeError(f"Missing municipality_code in {path}")
    frame["municipality_code"] = frame["municipality_code"].astype(str).str.zfill(7)
    if len(frame) != EXPECTED_MUNICIPALITIES or frame["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(
            f"Expected 144 unique municipalities in {path}; rows={len(frame)}, unique={frame['municipality_code'].nunique()}"
        )
    return frame


def vif_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute VIF from standardized linear regressions using complete rows."""
    x = frame.astype(float).copy()
    rows: list[dict[str, float | str]] = []
    for target in x.columns:
        y = x[target].to_numpy(float)
        others = x.drop(columns=[target]).to_numpy(float)
        y_std = y.std(ddof=0)
        if y_std == 0:
            vif = float("inf")
        else:
            yz = (y - y.mean()) / y_std
            if others.shape[1] == 0:
                r2 = 0.0
            else:
                means = others.mean(axis=0)
                stds = others.std(axis=0, ddof=0)
                keep = stds > 0
                z = (others[:, keep] - means[keep]) / stds[keep]
                design = np.column_stack([np.ones(len(z)), z])
                coef, *_ = np.linalg.lstsq(design, yz, rcond=None)
                fitted = design @ coef
                ss_res = float(np.square(yz - fitted).sum())
                ss_tot = float(np.square(yz - yz.mean()).sum())
                r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
            vif = float("inf") if r2 >= 1 - 1e-12 else 1.0 / (1.0 - r2)
        rows.append({"feature": target, "vif": vif})
    return pd.DataFrame(rows).sort_values("vif", ascending=False, na_position="first")


def distribution_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in frame.columns:
        s = pd.to_numeric(frame[col], errors="coerce")
        q1, median, q3 = s.quantile([0.25, 0.5, 0.75])
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        rows.append(
            {
                "feature": col,
                "n": int(s.notna().sum()),
                "missing": int(s.isna().sum()),
                "mean": float(s.mean()),
                "std": float(s.std(ddof=1)),
                "min": float(s.min()),
                "q1": float(q1),
                "median": float(median),
                "q3": float(q3),
                "max": float(s.max()),
                "iqr": float(iqr),
                "iqr_outlier_count": int(((s < lower) | (s > upper)).sum()),
                "zero_count": int((s == 0).sum()),
            }
        )
    return pd.DataFrame(rows)


def upper_pairs(corr: pd.DataFrame, threshold: float = 0.80) -> pd.DataFrame:
    rows = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            value = float(corr.loc[a, b])
            if abs(value) >= threshold:
                rows.append({"feature_a": a, "feature_b": b, "correlation": value, "abs_correlation": abs(value)})
    return pd.DataFrame(rows).sort_values("abs_correlation", ascending=False) if rows else pd.DataFrame(
        columns=["feature_a", "feature_b", "correlation", "abs_correlation"]
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = read_keyed(BASE_PATH)
    race = read_keyed(RACE_PATH)
    literacy = read_keyed(LITERACY_PATH)
    income = read_keyed(INCOME_PATH)

    base_cols = [
        "municipality_code",
        "municipality_name",
        "criterion__rural_female_share",
        "diagnostic__age_female_coverage_fraction",
        *AGE_FEATURES,
    ]
    missing_base = [c for c in base_cols if c not in base.columns]
    if missing_base:
        raise RuntimeError(f"Stage 3 matrix lacks expected Stage 5 fields: {missing_base}")

    race_cols = ["municipality_code", *RACE_FEATURES, "diagnostic__race_ignored_share"]
    literacy_cols = ["municipality_code", "socio__female_literacy_rate_15plus"]
    income_cols = ["municipality_code", "socio__household_per_capita_income_mean_brl"]

    matrix = base[base_cols].copy()
    matrix = matrix.merge(race[race_cols], on="municipality_code", how="left", validate="one_to_one")
    matrix = matrix.merge(literacy[literacy_cols], on="municipality_code", how="left", validate="one_to_one")
    matrix = matrix.merge(income[income_cols], on="municipality_code", how="left", validate="one_to_one")

    if len(matrix) != EXPECTED_MUNICIPALITIES or matrix["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError("Combined Stage 5 candidate matrix lost municipality key integrity")

    missing_candidate_cells = int(matrix[CANDIDATE_FEATURES].isna().sum().sum())
    matrix.to_csv(OUT / "stage5_som_candidate_matrix.csv", index=False)

    distributions = distribution_table(matrix[CANDIDATE_FEATURES])
    distributions.to_csv(OUT / "stage5_candidate_distributions.csv", index=False)

    pearson = matrix[CANDIDATE_FEATURES].corr(method="pearson")
    spearman = matrix[CANDIDATE_FEATURES].corr(method="spearman")
    pearson.to_csv(OUT / "stage5_candidate_correlation_pearson.csv")
    spearman.to_csv(OUT / "stage5_candidate_correlation_spearman.csv")
    p_pairs = upper_pairs(pearson)
    s_pairs = upper_pairs(spearman)
    p_pairs.to_csv(OUT / "stage5_high_correlation_pairs_pearson.csv", index=False)
    s_pairs.to_csv(OUT / "stage5_high_correlation_pairs_spearman.csv", index=False)

    vif = vif_table(matrix[CANDIDATE_FEATURES])
    vif.to_csv(OUT / "stage5_candidate_vif.csv", index=False)

    # Compositional diagnostics.
    race_declared_sum = matrix[RACE_FEATURES].sum(axis=1)
    race_plus_ignored = race_declared_sum + matrix["diagnostic__race_ignored_share"]
    race_rank = int(np.linalg.matrix_rank(matrix[RACE_FEATURES].to_numpy(float)))
    race_zero_counts = {c: int((matrix[c] == 0).sum()) for c in RACE_FEATURES}

    age_selected_sum = matrix[AGE_FEATURES].sum(axis=1)
    age_zero_counts = {c: int((matrix[c] == 0).sum()) for c in AGE_FEATURES}
    age_coverage = matrix["diagnostic__age_female_coverage_fraction"]

    finite_vif = vif["vif"].replace([np.inf, -np.inf], np.nan).dropna()
    max_finite_vif = float(finite_vif.max()) if not finite_vif.empty else None
    infinite_vif_features = vif.loc[np.isinf(vif["vif"]), "feature"].tolist()

    gates = {
        "municipality_key_integrity": "PASS",
        "candidate_missingness": "PASS" if missing_candidate_cells == 0 else "REVIEW",
        "temporal_baseline": "PASS_WITH_CAVEAT",
        "scale_standardization": "PENDING_FINAL_FEATURE_FREEZE",
        "income_retention": "REVIEW_SAMPLE_BASED_CENSUS_2022_ESTIMATE",
        "race_compositional_representation": "REVIEW_REQUIRED",
        "age_coverage_representation": "REVIEW_REQUIRED",
        "som_training_authorized": False,
    }

    summary = {
        "stage": "Stage 5 pre-SOM candidate quality gate",
        "municipalities": int(matrix["municipality_code"].nunique()),
        "candidate_feature_count": len(CANDIDATE_FEATURES),
        "candidate_features": CANDIDATE_FEATURES,
        "quality_fields": QUALITY_FIELDS,
        "missing_candidate_cells": missing_candidate_cells,
        "high_abs_correlation_threshold": 0.80,
        "high_pearson_pair_count": int(len(p_pairs)),
        "high_spearman_pair_count": int(len(s_pairs)),
        "max_finite_vif": max_finite_vif,
        "infinite_vif_features": infinite_vif_features,
        "race_composition": {
            "declared_share_sum_min": float(race_declared_sum.min()),
            "declared_share_sum_max": float(race_declared_sum.max()),
            "declared_plus_ignored_min": float(race_plus_ignored.min()),
            "declared_plus_ignored_max": float(race_plus_ignored.max()),
            "raw_share_matrix_rank": race_rank,
            "raw_share_feature_count": len(RACE_FEATURES),
            "zero_counts": race_zero_counts,
            "decision": "Do not freeze the five raw shares for SOM until zero-aware compositional/reduced representation is selected and sensitivity checked.",
        },
        "age_block": {
            "selected_age_share_sum_min": float(age_selected_sum.min()),
            "selected_age_share_sum_median": float(age_selected_sum.median()),
            "selected_age_share_sum_max": float(age_selected_sum.max()),
            "age_population_coverage_min": float(age_coverage.min()),
            "age_population_coverage_median": float(age_coverage.median()),
            "age_population_coverage_max": float(age_coverage.max()),
            "zero_counts": age_zero_counts,
            "decision": "Retain age shares as candidates but inspect coverage sensitivity before freezing them as SOM training features.",
        },
        "income": {
            "source_year": 2022,
            "sample_based": True,
            "poverty_measure": False,
            "decision": "Candidate retained for gate review; final inclusion must acknowledge Census sample estimation and must not be called poverty.",
        },
        "gates": gates,
        "next_action": "Resolve race compositional representation and age-coverage sensitivity, then freeze/standardize the final SOM feature matrix. No SOM training before that decision.",
    }
    (OUT / "stage5_pre_som_gate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
