from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


DecayFunction = Callable[[pd.Series], pd.Series]


@dataclass(frozen=True)
class E2SFCAResult:
    service_ratios: pd.DataFrame
    sector_scores: pd.DataFrame


def exponential_decay(beta: float) -> DecayFunction:
    if beta <= 0:
        raise ValueError("beta must be positive")

    def _decay(minutes: pd.Series) -> pd.Series:
        return np.exp(-beta * minutes.astype(float))

    return _decay


def gaussian_decay(sigma: float) -> DecayFunction:
    if sigma <= 0:
        raise ValueError("sigma must be positive")

    def _decay(minutes: pd.Series) -> pd.Series:
        x = minutes.astype(float)
        return np.exp(-0.5 * (x / sigma) ** 2)

    return _decay


def e2sfca(
    travel: pd.DataFrame,
    origins: pd.DataFrame,
    services: pd.DataFrame,
    *,
    origin_col: str = "origin_id",
    service_col: str = "service_id",
    time_col: str = "travel_time_min",
    population_col: str = "female_population",
    capacity_col: str = "capacity",
    service_type_col: str = "service_type",
    scenario_col: str = "scenario",
    threshold_minutes: float | None = None,
    decay: DecayFunction | None = None,
) -> E2SFCAResult:
    """Compute enhanced two-step floating catchment accessibility.

    Travel rows are origin-service pairs for one or more scenarios. Scores are computed
    independently by scenario and service type so functionally different services are not
    treated as substitutes.
    """
    required_travel = {origin_col, service_col, time_col, scenario_col}
    required_origins = {origin_col, population_col}
    required_services = {service_col, capacity_col, service_type_col}
    if missing := required_travel.difference(travel.columns):
        raise ValueError(f"Travel matrix missing columns: {sorted(missing)}")
    if missing := required_origins.difference(origins.columns):
        raise ValueError(f"Origins missing columns: {sorted(missing)}")
    if missing := required_services.difference(services.columns):
        raise ValueError(f"Services missing columns: {sorted(missing)}")

    pairs = travel.copy()
    pairs[time_col] = pd.to_numeric(pairs[time_col], errors="coerce")
    pairs = pairs.dropna(subset=[time_col])
    pairs = pairs[pairs[time_col] >= 0]
    if threshold_minutes is not None:
        pairs = pairs[pairs[time_col] <= float(threshold_minutes)]

    pairs = pairs.merge(
        origins[[origin_col, population_col]], on=origin_col, how="left", validate="many_to_one"
    )
    pairs = pairs.merge(
        services[[service_col, capacity_col, service_type_col]],
        on=service_col,
        how="left",
        validate="many_to_one",
    )
    if pairs[[population_col, capacity_col, service_type_col]].isna().any().any():
        raise ValueError("Unmatched origin population or service metadata in travel matrix.")

    pairs[population_col] = pd.to_numeric(pairs[population_col], errors="raise").astype(float)
    pairs[capacity_col] = pd.to_numeric(pairs[capacity_col], errors="raise").astype(float)
    if (pairs[population_col] < 0).any() or (pairs[capacity_col] < 0).any():
        raise ValueError("Population and capacity must be non-negative.")

    pairs["decay_weight"] = 1.0 if decay is None else decay(pairs[time_col])
    pairs["weighted_demand"] = pairs[population_col] * pairs["decay_weight"]

    group = [scenario_col, service_type_col, service_col]
    demand = pairs.groupby(group, as_index=False)["weighted_demand"].sum()
    service_meta = services[[service_col, capacity_col, service_type_col]].drop_duplicates()
    service_ratios = demand.merge(
        service_meta, on=[service_type_col, service_col], how="left", validate="one_to_one"
    )
    service_ratios["supply_demand_ratio"] = np.where(
        service_ratios["weighted_demand"] > 0,
        service_ratios[capacity_col] / service_ratios["weighted_demand"],
        np.nan,
    )

    pairs = pairs.merge(
        service_ratios[[scenario_col, service_type_col, service_col, "supply_demand_ratio"]],
        on=[scenario_col, service_type_col, service_col],
        how="left",
        validate="many_to_one",
    )
    pairs["access_contribution"] = pairs["supply_demand_ratio"] * pairs["decay_weight"]
    score_group = [scenario_col, service_type_col, origin_col]
    sector_scores = pairs.groupby(score_group, as_index=False)["access_contribution"].sum()
    sector_scores = sector_scores.rename(columns={"access_contribution": "e2sfca_score"})
    return E2SFCAResult(service_ratios=service_ratios, sector_scores=sector_scores)


def compare_seasons(
    scores: pd.DataFrame,
    *,
    origin_col: str = "origin_id",
    service_type_col: str = "service_type",
    scenario_col: str = "scenario",
    score_col: str = "e2sfca_score",
    flood_label: str = "flood_season",
    dry_label: str = "dry_season",
) -> pd.DataFrame:
    x = scores[scores[scenario_col].isin([flood_label, dry_label])].copy()
    wide = x.pivot_table(
        index=[origin_col, service_type_col], columns=scenario_col, values=score_col, aggfunc="first"
    ).reset_index()
    if flood_label not in wide or dry_label not in wide:
        raise ValueError("Both flood and dry season scores are required.")
    wide["absolute_change"] = (wide[flood_label] - wide[dry_label]).abs()
    denom = wide[[flood_label, dry_label]].mean(axis=1).replace(0, np.nan)
    wide["relative_change"] = wide["absolute_change"] / denom
    wide["flood_rank"] = wide.groupby(service_type_col)[flood_label].rank(
        method="average", ascending=False
    )
    wide["dry_rank"] = wide.groupby(service_type_col)[dry_label].rank(
        method="average", ascending=False
    )
    wide["absolute_rank_change"] = (wide["flood_rank"] - wide["dry_rank"]).abs()
    return wide
