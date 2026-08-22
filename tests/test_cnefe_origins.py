import pandas as pd
import pytest

from src.data.cnefe_origins import build_cnefe_sector_origins


def test_cnefe_origin_is_observed_residential_anchor():
    addresses = pd.DataFrame(
        {
            "sector": ["1", "1", "1", "2"],
            "species": ["RES", "RES", "SHOP", "RES"],
            "quality": ["A", "A", "A", "A"],
            "lat": [-1.0, -1.2, -1.1, -2.0],
            "lon": [-48.0, -48.2, -48.1, -55.0],
        }
    )
    sectors = pd.DataFrame(
        {
            "CD_SETOR": ["1", "2", "3"],
            "CD_MUN": ["1501", "1502", "1503"],
            "NM_MUN": ["A", "B", "C"],
            "female_population": [100, 50, 25],
        }
    )
    origins, audit = build_cnefe_sector_origins(
        addresses,
        sectors,
        sector_col="sector",
        species_col="species",
        geo_quality_col="quality",
        latitude_col="lat",
        longitude_col="lon",
        residential_species_values=["RES"],
        accepted_geo_quality_values=["A"],
    )
    sector1 = origins.loc[origins["origin_id"] == "1"].iloc[0]
    assert (sector1["latitude"], sector1["longitude"]) in {(-1.0, -48.0), (-1.2, -48.2)}
    assert sector1["origin_validation_status"] == "validated_inhabited_location"
    sector3 = origins.loc[origins["origin_id"] == "3"].iloc[0]
    assert sector3["origin_validation_status"] == "needs_fallback_origin"
    assert audit.sectors_with_eligible_addresses == 2


def test_cnefe_rules_cannot_be_guessed():
    addresses = pd.DataFrame(
        {"sector": ["1"], "species": ["x"], "quality": ["x"], "lat": [-1], "lon": [-48]}
    )
    sectors = pd.DataFrame(
        {"CD_SETOR": ["1"], "CD_MUN": ["1501"], "NM_MUN": ["A"], "female_population": [10]}
    )
    with pytest.raises(ValueError, match="do not guess"):
        build_cnefe_sector_origins(
            addresses,
            sectors,
            sector_col="sector",
            species_col="species",
            geo_quality_col="quality",
            latitude_col="lat",
            longitude_col="lon",
            residential_species_values=[],
            accepted_geo_quality_values=[],
        )
