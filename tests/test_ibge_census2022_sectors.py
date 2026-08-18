from __future__ import annotations

import pandas as pd
import pytest

from src.data.ibge_census2022_sectors import validate_demography


def test_demography_validation_accepts_consistent_sex_totals():
    frame = pd.DataFrame(
        {
            "CD_setor": ["150000000000001"],
            "V01006": [10],
            "V01007": [4],
            "V01008": [6],
        }
    )
    audit = validate_demography(frame)
    assert audit["female_population_observed"] == 6


def test_demography_validation_rejects_inconsistent_sex_totals():
    frame = pd.DataFrame(
        {
            "CD_setor": ["150000000000001"],
            "V01006": [10],
            "V01007": [4],
            "V01008": [5],
        }
    )
    with pytest.raises(ValueError, match="total = male"):
        validate_demography(frame)


def test_missing_female_is_preserved_in_audit():
    frame = pd.DataFrame(
        {
            "CD_setor": ["150000000000001"],
            "V01006": [pd.NA],
            "V01007": [pd.NA],
            "V01008": [pd.NA],
        }
    )
    audit = validate_demography(frame)
    assert audit["missing_female"] == 1
