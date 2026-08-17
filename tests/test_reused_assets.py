from __future__ import annotations

import pandas as pd
import pytest

from src.data.harmonization import clean_ibge_code, normalize_text, parse_brazilian_number
from src.data.sidra import SidraQuery
from src.network.source_catalog import SOURCES


def test_ibge_code_cleaning_preserves_seven_digits():
    observed = clean_ibge_code(pd.Series(["1500107", "1500206.0"]))
    assert observed.tolist() == ["1500107", "1500206"]


def test_brazilian_numeric_parser_preserves_missing_values():
    observed = parse_brazilian_number(pd.Series(["1.234,5", "-", "X"]))
    assert observed.iloc[0] == pytest.approx(1234.5)
    assert observed.iloc[1:].isna().all()


def test_text_normalization_handles_accents_and_spacing():
    assert normalize_text("  Mojuí   dos Campos ") == "mojui dos campos"


def test_sidra_query_is_declarative():
    query = SidraQuery(table=9514, territorial_level=6, periods="2022")
    assert query.as_parameters()["table"] == 9514


def test_transport_catalog_has_unique_source_ids():
    source_ids = [item["source_id"] for item in SOURCES]
    assert source_ids and len(source_ids) == len(set(source_ids))
