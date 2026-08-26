from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def municipal_accessibility_envelope(
    sector_scores: pd.DataFrame,
    full_origins: pd.DataFrame,
    *,
    stratum_cols: Sequence[str] = ("service_type", "scenario"),
    origin_col: str = "origin_id",
    municipality_code_col: str = "municipality_code",
    municipality_name_col: str = "municipality_name",
    population_col: str = "female_population",
    score_col: str = "e2sfca_score",
) -> pd.DataFrame:
    """Build empirical sensitivity envelopes for incomplete origin coverage.

    The lower envelope assigns zero accessibility to non-observed origins. The upper
    envelope assigns the largest observed sector score in the same service/scenario
    stratum. These are deterministic sensitivity completions, not confidence bounds.
    They do not correct the E2SFCA service-demand denominator for unknown connectors.
    """
    required_origins = {
        origin_col,
        municipality_code_col,
        municipality_name_col,
        population_col,
    }
    required_scores = {origin_col, score_col, *stratum_cols}
    missing_origins = required_origins - set(full_origins.columns)
    missing_scores = required_scores - set(sector_scores.columns)
    if missing_origins:
        raise ValueError(f"Missing full-origin columns: {sorted(missing_origins)}")
    if missing_scores:
        raise ValueError(f"Missing sector-score columns: {sorted(missing_scores)}")
    if full_origins[origin_col].duplicated().any():
        raise ValueError("full_origins must contain one row per origin")
    if sector_scores.duplicated([*stratum_cols, origin_col]).any():
        raise ValueError("sector_scores must contain one row per stratum and origin")

    origins = full_origins[
        [origin_col, municipality_code_col, municipality_name_col, population_col]
    ].copy()
    origins[population_col] = pd.to_numeric(origins[population_col], errors="raise")
    if origins[population_col].isna().any() or (origins[population_col] < 0).any():
        raise ValueError("Female population must be finite and non-negative")

    scores = sector_scores[[*stratum_cols, origin_col, score_col]].copy()
    scores[score_col] = pd.to_numeric(scores[score_col], errors="raise")
    if scores[score_col].isna().any() or (~np.isfinite(scores[score_col])).any():
        raise ValueError("E2SFCA scores must be finite")
    if (scores[score_col] < 0).any():
        raise ValueError("E2SFCA scores must be non-negative")
    unknown = set(scores[origin_col]) - set(origins[origin_col])
    if unknown:
        raise ValueError(f"Scores contain unknown origins: {sorted(unknown)[:5]}")

    strata = scores[list(stratum_cols)].drop_duplicates()
    expanded = strata.merge(origins, how="cross")
    x = expanded.merge(
        scores,
        on=[*stratum_cols, origin_col],
        how="left",
        validate="one_to_one",
    )
    x["score_observed"] = x[score_col].notna()
    x["observed_population"] = x[population_col] * x["score_observed"].astype(int)
    x["observed_weighted_score"] = x[population_col] * x[score_col].fillna(0)

    maxima = (
        scores.groupby(list(stratum_cols), dropna=False)[score_col]
        .max()
        .rename("stratum_observed_max_score")
        .reset_index()
    )
    x = x.merge(maxima, on=list(stratum_cols), how="left", validate="many_to_one")
    x["upper_weighted_score"] = x[population_col] * x[score_col].fillna(
        x["stratum_observed_max_score"]
    )

    group_cols = [
        *stratum_cols,
        municipality_code_col,
        municipality_name_col,
    ]
    out = (
        x.groupby(group_cols, dropna=False)
        .agg(
            origin_count=(origin_col, "size"),
            observed_origin_count=("score_observed", "sum"),
            female_population=(population_col, "sum"),
            observed_female_population=("observed_population", "sum"),
            observed_weighted_score_sum=("observed_weighted_score", "sum"),
            upper_weighted_score_sum=("upper_weighted_score", "sum"),
            empirical_upper_score=("stratum_observed_max_score", "first"),
        )
        .reset_index()
    )
    positive_population = out["female_population"] > 0
    out["female_population_coverage_fraction"] = np.where(
        positive_population,
        out["observed_female_population"] / out["female_population"],
        1.0,
    )
    out["observed_population_weighted_mean"] = np.where(
        out["observed_female_population"] > 0,
        out["observed_weighted_score_sum"] / out["observed_female_population"],
        np.nan,
    )
    out["lower_sensitivity_envelope"] = np.where(
        positive_population,
        out["observed_weighted_score_sum"] / out["female_population"],
        0.0,
    )
    out["upper_sensitivity_envelope"] = np.where(
        positive_population,
        out["upper_weighted_score_sum"] / out["female_population"],
        0.0,
    )
    out["sensitivity_envelope_width"] = (
        out["upper_sensitivity_envelope"] - out["lower_sensitivity_envelope"]
    )
    out["coverage_status"] = np.where(
        out["female_population_coverage_fraction"].eq(1.0),
        "fully_observed",
        "partially_identified",
    )
    out["is_confidence_interval"] = False
    out["corrects_unknown_connector_competition"] = False
    out["authorized_as_final_e2sfca"] = False
    return out
