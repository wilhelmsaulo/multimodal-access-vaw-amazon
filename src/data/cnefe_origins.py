from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CNEFEOriginAudit:
    sectors_input: int
    sectors_with_eligible_addresses: int
    sectors_without_eligible_addresses: int
    eligible_addresses: int
    minimum_addresses_in_covered_sector: int
    median_addresses_in_covered_sector: float
    maximum_addresses_in_covered_sector: int


def _require_nonempty(values: Iterable[object], label: str) -> set[str]:
    normalized = {str(v).strip() for v in values if str(v).strip()}
    if not normalized:
        raise ValueError(
            f"{label} is empty. Populate it from the official CNEFE schema audit; do not guess."
        )
    return normalized


def build_cnefe_sector_origins(
    addresses: pd.DataFrame,
    sectors: pd.DataFrame,
    *,
    sector_col: str,
    species_col: str,
    geo_quality_col: str,
    latitude_col: str,
    longitude_col: str,
    residential_species_values: Iterable[object],
    accepted_geo_quality_values: Iterable[object],
    sector_id_col: str = "CD_SETOR",
    municipality_code_col: str = "CD_MUN",
    municipality_name_col: str = "NM_MUN",
    female_population_col: str = "female_population",
) -> tuple[pd.DataFrame, CNEFEOriginAudit]:
    """Derive one observed residentially anchored representative point per census sector.

    Eligible CNEFE residential coordinates are filtered using values documented by the schema
    audit. For each sector, the coordinate-wise median is computed and the actual eligible
    CNEFE point closest to that median is selected. The output therefore remains anchored at an
    observed/accepted address coordinate rather than creating a synthetic polygon centroid.
    """
    residential = _require_nonempty(residential_species_values, "residential_species_values")
    accepted_quality = _require_nonempty(
        accepted_geo_quality_values, "accepted_geo_quality_values"
    )
    required_address = {
        sector_col,
        species_col,
        geo_quality_col,
        latitude_col,
        longitude_col,
    }
    missing = required_address.difference(addresses.columns)
    if missing:
        raise ValueError(f"CNEFE table missing columns: {sorted(missing)}")
    required_sector = {
        sector_id_col,
        municipality_code_col,
        municipality_name_col,
        female_population_col,
    }
    missing = required_sector.difference(sectors.columns)
    if missing:
        raise ValueError(f"Sector table missing columns: {sorted(missing)}")

    x = addresses[list(required_address)].copy()
    x[sector_col] = x[sector_col].astype("string")
    x[species_col] = x[species_col].astype("string").str.strip()
    x[geo_quality_col] = x[geo_quality_col].astype("string").str.strip()
    x[latitude_col] = pd.to_numeric(x[latitude_col], errors="coerce")
    x[longitude_col] = pd.to_numeric(x[longitude_col], errors="coerce")
    x = x[
        x[species_col].isin(residential)
        & x[geo_quality_col].isin(accepted_quality)
        & x[latitude_col].between(-90, 90)
        & x[longitude_col].between(-180, 180)
    ].copy()

    selected_rows = []
    address_counts = x.groupby(sector_col).size()
    for sector_id, group in x.groupby(sector_col, sort=True):
        median_lat = float(group[latitude_col].median())
        median_lon = float(group[longitude_col].median())
        # For points inside one sector, squared degrees are sufficient only for selecting the
        # nearest observed address to the local median; no travel metric is derived here.
        distance2 = (
            (group[latitude_col].astype(float) - median_lat) ** 2
            + (group[longitude_col].astype(float) - median_lon) ** 2
        )
        row = group.loc[distance2.idxmin()]
        selected_rows.append(
            {
                "origin_id": str(sector_id),
                "latitude": float(row[latitude_col]),
                "longitude": float(row[longitude_col]),
                "eligible_residential_address_count": int(len(group)),
                "origin_method": "cnefe_residential_median_anchored_observed_point",
                "origin_validation_status": "validated_inhabited_location",
            }
        )

    selected = pd.DataFrame(selected_rows)
    sector_base = sectors[
        [sector_id_col, municipality_code_col, municipality_name_col, female_population_col]
    ].copy()
    sector_base[sector_id_col] = sector_base[sector_id_col].astype("string")
    origins = sector_base.merge(
        selected,
        left_on=sector_id_col,
        right_on="origin_id",
        how="left",
        validate="one_to_one",
    )
    origins = origins.rename(
        columns={
            municipality_code_col: "municipality_code",
            municipality_name_col: "municipality_name",
            female_population_col: "female_population",
        }
    )
    origins["origin_id"] = origins["origin_id"].fillna(origins[sector_id_col])
    origins["origin_validation_status"] = origins["origin_validation_status"].fillna(
        "needs_fallback_origin"
    )
    origins["origin_method"] = origins["origin_method"].fillna("not_assigned")
    origins = origins.drop(columns=[sector_id_col])

    covered = int(origins["latitude"].notna().sum()) if "latitude" in origins else 0
    counts = address_counts.astype(int)
    audit = CNEFEOriginAudit(
        sectors_input=int(len(sector_base)),
        sectors_with_eligible_addresses=covered,
        sectors_without_eligible_addresses=int(len(sector_base) - covered),
        eligible_addresses=int(len(x)),
        minimum_addresses_in_covered_sector=int(counts.min()) if len(counts) else 0,
        median_addresses_in_covered_sector=float(counts.median()) if len(counts) else 0.0,
        maximum_addresses_in_covered_sector=int(counts.max()) if len(counts) else 0,
    )
    return origins, audit
