from __future__ import annotations

"""Freeze and standardize the final Stage-5 SOM feature matrix.

This script is strictly Stage 5. It does not alter Stage 3/4 MCDM inputs or
rankings. Race/color and age are represented with isometric log-ratio (ILR)
coordinates so full compositional information is retained without the linear
dependence of raw shares.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("results/stage5/tables")
EXPECTED = 144
BASE = Path("results/stage3/tables/municipal_analytical_matrix.csv")
RACE = OUT / "stage5_female_race_color_candidates.csv"
AGE = OUT / "stage5_complete_female_age_candidate.csv"
LITERACY = OUT / "stage5_female_literacy_candidate.csv"
INCOME = OUT / "stage5_income_candidate.csv"

RACE_ORDER = ["branca", "preta", "parda", "amarela", "indigena"]
RACE_COUNT_COLS = [f"female_race_{x}_count" for x in RACE_ORDER]
AGE_RAW_COLS = [
    "socio__female_age_share_15_29",
    "socio__female_age_share_30_59",
    "socio__female_age_share_60_plus",
]
OTHER_RAW = [
    "criterion__rural_female_share",
    "socio__female_literacy_rate_15plus",
    "socio__household_per_capita_income_mean_brl",
]
FINAL_FEATURES = [
    *OTHER_RAW,
    "profile__female_age_ilr_1",
    "profile__female_age_ilr_2",
    "profile__female_age_ilr_3",
    "profile__female_race_ilr_1",
    "profile__female_race_ilr_2",
    "profile__female_race_ilr_3",
    "profile__female_race_ilr_4",
]


def read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"municipality_code": str}, low_memory=False)
    df["municipality_code"] = df["municipality_code"].astype(str).str.zfill(7)
    if len(df) != EXPECTED or df["municipality_code"].nunique() != EXPECTED:
        raise RuntimeError(f"Expected 144 unique municipalities in {path}")
    return df


def ilr_sequential(comp: np.ndarray) -> np.ndarray:
    """Sequential binary-partition ILR with fixed ordered parts.

    Coordinate j contrasts the geometric mean of parts 1..j against part j+1:
    sqrt(j/(j+1)) * (mean(log(parts[:j])) - log(parts[j])).
    This is an orthonormal ILR basis. Signs/order are parameterization only.
    """
    comp = np.asarray(comp, dtype=float)
    if np.any(comp <= 0):
        raise RuntimeError("ILR requires strictly positive compositions")
    comp = comp / comp.sum(axis=1, keepdims=True)
    logs = np.log(comp)
    n, d = logs.shape
    out = np.empty((n, d - 1), dtype=float)
    for j in range(1, d):
        out[:, j - 1] = np.sqrt(j / (j + 1.0)) * (logs[:, :j].mean(axis=1) - logs[:, j])
    return out


def vif_table(frame: pd.DataFrame) -> pd.DataFrame:
    x = frame.astype(float).to_numpy()
    rows = []
    for i, name in enumerate(frame.columns):
        y = x[:, i]
        others = np.delete(x, i, axis=1)
        design = np.column_stack([np.ones(len(y)), others])
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        fitted = design @ coef
        ss_res = float(np.square(y - fitted).sum())
        ss_tot = float(np.square(y - y.mean()).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
        vif = float("inf") if r2 >= 1 - 1e-12 else 1.0 / (1.0 - r2)
        rows.append({"feature": name, "vif": vif})
    return pd.DataFrame(rows).sort_values("vif", ascending=False)


def high_pairs(corr: pd.DataFrame, threshold: float = 0.80) -> pd.DataFrame:
    rows = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            r = float(corr.loc[a, b])
            if abs(r) >= threshold:
                rows.append({"feature_a": a, "feature_b": b, "correlation": r, "abs_correlation": abs(r)})
    return pd.DataFrame(rows, columns=["feature_a", "feature_b", "correlation", "abs_correlation"]).sort_values(
        "abs_correlation", ascending=False
    ) if rows else pd.DataFrame(columns=["feature_a", "feature_b", "correlation", "abs_correlation"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base, race, age, literacy, income = map(read, [BASE, RACE, AGE, LITERACY, INCOME])

    matrix = base[["municipality_code", "municipality_name", "criterion__rural_female_share"]].copy()
    matrix = matrix.merge(literacy[["municipality_code", "socio__female_literacy_rate_15plus"]], on="municipality_code", validate="one_to_one")
    matrix = matrix.merge(income[["municipality_code", "socio__household_per_capita_income_mean_brl"]], on="municipality_code", validate="one_to_one")
    matrix = matrix.merge(age[["municipality_code", *AGE_RAW_COLS]], on="municipality_code", validate="one_to_one")
    matrix = matrix.merge(race[["municipality_code", *RACE_COUNT_COLS]], on="municipality_code", validate="one_to_one")

    if matrix.isna().any().any():
        raise RuntimeError(f"Missing cells before final transform: {matrix.isna().sum()[matrix.isna().sum()>0].to_dict()}")

    # Age: add the omitted <15 share to form a complete four-part female composition.
    age_selected = matrix[AGE_RAW_COLS].to_numpy(float)
    under15 = 1.0 - age_selected.sum(axis=1)
    if np.any(under15 <= 0):
        raise RuntimeError("Derived female under-15 share is not strictly positive")
    age_comp = np.column_stack([under15, age_selected])
    age_ilr = ilr_sequential(age_comp)
    for j in range(3):
        matrix[f"profile__female_age_ilr_{j+1}"] = age_ilr[:, j]

    # Race/color: retain raw counts for provenance, but smooth zeros ONLY in the
    # transformed training copy with Jeffreys 0.5 pseudo-count. This prevents
    # undefined log-ratios while having negligible influence on nonzero cells.
    race_counts = matrix[RACE_COUNT_COLS].to_numpy(float)
    zero_cells = int((race_counts == 0).sum())
    smoothed = race_counts + 0.5
    race_comp = smoothed / smoothed.sum(axis=1, keepdims=True)
    race_ilr = ilr_sequential(race_comp)
    for j in range(4):
        matrix[f"profile__female_race_ilr_{j+1}"] = race_ilr[:, j]

    raw_final = matrix[["municipality_code", "municipality_name", *FINAL_FEATURES]].copy()
    if raw_final[FINAL_FEATURES].isna().any().any():
        raise RuntimeError("Final transformed feature matrix contains missing values")

    means = raw_final[FINAL_FEATURES].mean()
    stds = raw_final[FINAL_FEATURES].std(ddof=0)
    if (stds <= 0).any():
        raise RuntimeError(f"Zero-variance final features: {stds[stds<=0].index.tolist()}")
    standardized = raw_final[["municipality_code", "municipality_name"]].copy()
    standardized[FINAL_FEATURES] = (raw_final[FINAL_FEATURES] - means) / stds

    corr_p = standardized[FINAL_FEATURES].corr(method="pearson")
    corr_s = standardized[FINAL_FEATURES].corr(method="spearman")
    vif = vif_table(standardized[FINAL_FEATURES])
    hp = high_pairs(corr_p)
    hs = high_pairs(corr_s)
    max_abs_p = float(np.max(np.abs(corr_p.to_numpy() - np.eye(len(FINAL_FEATURES)))))
    max_abs_s = float(np.max(np.abs(corr_s.to_numpy() - np.eye(len(FINAL_FEATURES)))))
    max_vif = float(vif["vif"].replace([np.inf, -np.inf], np.nan).max())

    # Gate: no missingness; no near-collinearity; VIF below conventional 10.
    authorized = bool(
        standardized[FINAL_FEATURES].notna().all().all()
        and np.isfinite(standardized[FINAL_FEATURES].to_numpy()).all()
        and max_vif < 10.0
        and max_abs_p < 0.95
    )

    raw_final.to_csv(OUT / "stage5_som_final_unstandardized_matrix.csv", index=False)
    standardized.to_csv(OUT / "stage5_som_final_standardized_matrix.csv", index=False)
    vif.to_csv(OUT / "stage5_final_vif.csv", index=False)
    corr_p.to_csv(OUT / "stage5_final_correlation_pearson.csv")
    corr_s.to_csv(OUT / "stage5_final_correlation_spearman.csv")
    hp.to_csv(OUT / "stage5_final_high_pairs_pearson.csv", index=False)
    hs.to_csv(OUT / "stage5_final_high_pairs_spearman.csv", index=False)

    scaling = pd.DataFrame({"feature": FINAL_FEATURES, "mean": means.values, "std_population": stds.values})
    scaling.to_csv(OUT / "stage5_final_standardization_parameters.csv", index=False)

    audit = {
        "stage": "Stage 5 final SOM feature freeze and quality gate",
        "municipalities": int(len(standardized)),
        "final_feature_count": len(FINAL_FEATURES),
        "final_features": FINAL_FEATURES,
        "race_block": {
            "source": "IBGE Census 2022 SIDRA 9606, women, all ages, municipality",
            "parts_order": RACE_ORDER,
            "representation": "4 orthonormal sequential ILR coordinates",
            "zero_cells_in_raw_counts": zero_cells,
            "zero_treatment_for_transform_only": "Jeffreys additive 0.5 pseudo-count before closure; raw observed counts/shares remain unchanged in source audit",
            "normative_reference": None,
        },
        "age_block": {
            "source": "IBGE Census 2022 SIDRA 9514, women, municipality universe",
            "parts_order": ["under_15", "15_29", "30_59", "60_plus"],
            "under_15_derivation": "1 - (share15_29 + share30_59 + share60_plus)",
            "representation": "3 orthonormal sequential ILR coordinates",
        },
        "other_features": OTHER_RAW,
        "income_note": "Retained as mean household per-capita income from Census 2022 sample-based estimate; it is not labelled poverty.",
        "standardization": "z-score using population mean/std fitted once on the frozen 144-municipality Stage-5 matrix",
        "missing_final_cells": int(standardized[FINAL_FEATURES].isna().sum().sum()),
        "max_abs_pearson": max_abs_p,
        "max_abs_spearman": max_abs_s,
        "high_pearson_pairs_ge_0_80": int(len(hp)),
        "high_spearman_pairs_ge_0_80": int(len(hs)),
        "max_vif": max_vif,
        "gate_thresholds": {"max_vif_lt": 10.0, "max_abs_pearson_lt": 0.95},
        "som_training_authorized": authorized,
        "analytical_separation": "These profile features remain outside the Stage-4 MCDM model and do not alter the priority ranking.",
    }
    (OUT / "stage5_final_feature_gate.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not authorized:
        raise RuntimeError("Final Stage-5 feature gate did not authorize SOM training")


if __name__ == "__main__":
    main()
