"""Generic harmonization utilities adapted from the two preceding VAW repositories.

Sources:
- wilhelmsaulo/robust-underreporting-vaw-amazon, src/process_censo2022.py
- wilhelmsaulo/explainable-municipal-prioritization-framework, src/empriority/integration.py

Only source-agnostic parsing and key-cleaning logic is retained. No police, MCDA,
municipal ranking, or previous-study outcome logic is included.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

import numpy as np
import pandas as pd


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.strip().lower())


def slug(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", normalize_text(value)).strip("_")


def clean_ibge_code(series: pd.Series, width: int = 7) -> pd.Series:
    cleaned = series.astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    cleaned = cleaned.where(cleaned.str.fullmatch(r"\d+"))
    return cleaned.str.zfill(width)


def parse_brazilian_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype("string")
        .str.replace(" ", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .replace({"-": pd.NA, "..": pd.NA, "...": pd.NA, "X": pd.NA})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def find_column(columns: Iterable[object], *needles: str) -> str:
    for column in columns:
        normalized = normalize_text(column)
        if all(normalize_text(needle) in normalized for needle in needles):
            return str(column)
    raise KeyError(f"Column not found for terms: {needles}")


def read_sidra_payload(payload: list[dict[str, object]]) -> pd.DataFrame:
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("Unexpected SIDRA payload")
    return pd.DataFrame(payload[1:]).rename(columns=payload[0])
