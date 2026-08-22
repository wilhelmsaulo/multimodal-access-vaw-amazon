from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


ORIGIN_COLUMNS = [
    "origin_id",
    "municipality_code",
    "municipality_name",
    "female_population",
    "latitude",
    "longitude",
    "origin_method",
    "origin_validation_status",
]

DESTINATION_COLUMNS = [
    "service_id",
    "service_type",
    "municipality_code",
    "municipality_name",
    "latitude",
    "longitude",
    "capacity",
    "capacity_type",
    "validation_status",
]


@dataclass(frozen=True)
class ODAudit:
    origins_total: int
    origins_ready: int
    destinations_total: int
    destinations_ready_routing: int
    destinations_ready_e2sfca: int
    candidate_pairs_routing: int
    candidate_pairs_e2sfca: int


def validate_origin_points(origins: pd.DataFrame) -> None:
    missing = set(ORIGIN_COLUMNS).difference(origins.columns)
    if missing:
        raise ValueError(f"Origin table missing columns: {sorted(missing)}")
    if origins["origin_id"].isna().any() or origins["origin_id"].duplicated().any():
        raise ValueError("origin_id must be non-missing and unique")
    lat = pd.to_numeric(origins["latitude"], errors="coerce")
    lon = pd.to_numeric(origins["longitude"], errors="coerce")
    bad_lat = lat.notna() & ((lat < -90) | (lat > 90))
    bad_lon = lon.notna() & ((lon < -180) | (lon > 180))
    if bad_lat.any() or bad_lon.any():
        raise ValueError("Invalid origin coordinates")
    pop = pd.to_numeric(origins["female_population"], errors="coerce")
    if (pop.dropna() < 0).any():
        raise ValueError("female_population cannot be negative")

    method = origins["origin_method"].astype("string").str.lower().fillna("")
    status = origins["origin_validation_status"].astype("string").str.lower().fillna("")
    rural_centroid = method.str.contains("centroid") & method.str.contains("rural")
    if (rural_centroid & ~status.eq("validated_inhabited_location")).any():
        raise ValueError("Unvalidated rural centroids cannot be used as final accessibility origins.")


def ready_origins(origins: pd.DataFrame) -> pd.DataFrame:
    """Return analytical origins with a defensible location and observed demand.

    E2SFCA demand is the observed female resident population. A sector with a
    coordinate but missing female population is therefore not analytically ready.
    The documented CNEFE level-3 fallback is accepted because it was explicitly
    retained as a defensible fallback after the level-1/2 audit.
    """
    validate_origin_points(origins)
    lat = pd.to_numeric(origins["latitude"], errors="coerce")
    lon = pd.to_numeric(origins["longitude"], errors="coerce")
    pop = pd.to_numeric(origins["female_population"], errors="coerce")
    status = origins["origin_validation_status"].astype("string")
    location_valid = status.isin(
        [
            "validated",
            "validated_inhabited_location",
            "official_locality",
            "urban_representative_point",
            "accepted_estimated_address_fallback",
        ]
    )
    mask = lat.notna() & lon.notna() & pop.notna() & (pop >= 0) & location_valid
    return origins.loc[mask, ORIGIN_COLUMNS].copy()


def _functionally_validated_status(status: pd.Series) -> pd.Series:
    text = status.astype("string").fillna("").str.lower()
    explicitly_valid = text.str.startswith("function_validated") | text.isin(
        [
            "validated",
            "official_geocoded_validated",
            "official_directory_validated",
            "official_sagi_georeference_requires_routing_validation",
            "official_sagi_unit_requires_geocoding",
        ]
    )
    explicitly_excluded = text.str.contains("excluded", regex=False)
    return explicitly_valid & ~explicitly_excluded


def ready_destinations(services: pd.DataFrame, *, require_capacity: bool = False) -> pd.DataFrame:
    """Return routing-ready service destinations.

    Primary Stage-2 supply follows the harmonized rule fixed for this study:
    one validated physical service unit equals one supply opportunity within its
    own service category. Capacity is therefore *not* required for the primary
    E2SFCA analysis. ``require_capacity=True`` is retained only for an optional
    category-specific capacity sensitivity analysis.

    If a readiness artifact is supplied, its explicit ``ready_for_routing`` flag
    is authoritative. Otherwise, readiness is reconstructed conservatively from
    coordinates plus the current functional-validation statuses.
    """
    missing = set(DESTINATION_COLUMNS).difference(services.columns)
    if missing:
        raise ValueError(f"Service table missing columns: {sorted(missing)}")

    lat = pd.to_numeric(services["latitude"], errors="coerce")
    lon = pd.to_numeric(services["longitude"], errors="coerce")
    coordinates_ok = lat.notna() & lon.notna()

    if "ready_for_routing" in services.columns:
        explicit_ready = services["ready_for_routing"].fillna(False).astype(bool)
        mask = coordinates_ok & explicit_ready
    else:
        mask = coordinates_ok & _functionally_validated_status(services["validation_status"])

    if require_capacity:
        capacity = pd.to_numeric(services["capacity"], errors="coerce")
        mask &= capacity.notna() & (capacity >= 0)

    return services.loc[mask, DESTINATION_COLUMNS].copy()


def build_candidate_pairs(
    origins: pd.DataFrame,
    destinations: pd.DataFrame,
    *,
    scenarios: Iterable[str] = ("flood_season", "dry_season"),
) -> pd.DataFrame:
    """Create origin-service pairs to be solved by the multimodal routing engine.

    This function deliberately does not estimate travel time or straight-line access.
    It only materializes candidate OD pairs and scenario labels. Real travel times
    must be produced by the validated multimodal routing workflow.
    """
    o = ready_origins(origins)
    d = destinations.copy()
    if o.empty or d.empty:
        return pd.DataFrame(
            columns=["origin_id", "service_id", "service_type", "scenario", "travel_time_min"]
        )
    o = o[["origin_id"]].assign(_key=1)
    d = d[["service_id", "service_type"]].assign(_key=1)
    pairs = o.merge(d, on="_key", how="inner").drop(columns="_key")
    scenario_frame = pd.DataFrame({"scenario": list(scenarios)}).assign(_key=1)
    pairs = pairs.assign(_key=1).merge(scenario_frame, on="_key", how="inner").drop(columns="_key")
    pairs["travel_time_min"] = np.nan
    return pairs


def audit_od_inputs(origins: pd.DataFrame, services: pd.DataFrame) -> ODAudit:
    o_ready = ready_origins(origins)
    d_route = ready_destinations(services, require_capacity=False)

    # The primary E2SFCA model uses the same routing-ready physical destinations.
    # Missing observed capacity is not a blocker because primary supply is S_j = 1.
    d_e2_primary = d_route
    scenarios = 2
    return ODAudit(
        origins_total=int(len(origins)),
        origins_ready=int(len(o_ready)),
        destinations_total=int(len(services)),
        destinations_ready_routing=int(len(d_route)),
        destinations_ready_e2sfca=int(len(d_e2_primary)),
        candidate_pairs_routing=int(len(o_ready) * len(d_route) * scenarios),
        candidate_pairs_e2sfca=int(len(o_ready) * len(d_e2_primary) * scenarios),
    )
