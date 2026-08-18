"""Reused with adaptation from https://github.com/wilhelmsaulo/explainable-municipal-prioritization-framework/blob/main/src/empriority/connectors/sidra.py (blob 56da49447799cac20695b000d03e0011643d76fb).
Authorized by the repository owner for this project; provenance retained pending final licensing audit.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import httpx
import pandas as pd

from src.data.provenance import CollectionMetadata


@dataclass(frozen=True)
class SidraQuery:
    """Declarative representation of a SIDRA API query."""

    table: int
    territorial_level: int
    territories: str = "all"
    variables: str = "all"
    periods: str = "last"
    classifications: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.table <= 0:
            raise ValueError("SIDRA table must be a positive integer.")
        if self.territorial_level <= 0:
            raise ValueError("SIDRA territorial level must be a positive integer.")
        if any(identifier <= 0 for identifier in self.classifications):
            raise ValueError("SIDRA classification identifiers must be positive integers.")

    def as_parameters(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "territorial_level": self.territorial_level,
            "territories": self.territories,
            "variables": self.variables,
            "periods": self.periods,
            "classifications": self.classifications,
        }


class SidraConnector:
    """Client for the official IBGE SIDRA values API."""

    def __init__(self, base_url: str, timeout: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def build_url(self, query: SidraQuery) -> str:
        parts = [
            self.base_url,
            "t",
            str(query.table),
            f"n{query.territorial_level}",
            query.territories,
            "v",
            query.variables,
            "p",
            query.periods,
        ]
        for classification_id, categories in sorted(query.classifications.items()):
            parts.extend([f"c{classification_id}", categories])
        return "/".join(parts)

    def fetch(self, query: SidraQuery) -> tuple[pd.DataFrame, CollectionMetadata]:
        url = self.build_url(query)
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            payload: list[dict[str, Any]] = response.json()

        frame, column_labels = self._normalize(payload)
        metadata = CollectionMetadata.create(
            source="IBGE SIDRA",
            endpoint=url,
            parameters=query.as_parameters(),
            record_count=len(frame),
            column_labels=column_labels,
        )
        return frame, metadata

    @classmethod
    def _normalize(
        cls,
        payload: list[dict[str, Any]],
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        if not payload:
            return pd.DataFrame(), {}

        header = payload[0]
        rows = payload[1:]
        raw_to_normalized: dict[str, str] = {}
        used: set[str] = set()

        for raw_code, label in header.items():
            base_name = cls._safe_column_name(str(label)) or cls._safe_column_name(raw_code)
            candidate = base_name
            suffix = 2
            while candidate in used:
                candidate = f"{base_name}_{suffix}"
                suffix += 1
            used.add(candidate)
            raw_to_normalized[raw_code] = candidate

        frame = pd.DataFrame.from_records(rows)
        if frame.empty:
            frame = pd.DataFrame(columns=list(raw_to_normalized.values()))
        else:
            frame = frame.rename(columns=raw_to_normalized)
            ordered = [name for name in raw_to_normalized.values() if name in frame.columns]
            frame = frame.loc[:, ordered]

        column_labels = {
            normalized: str(header[raw_code]) for raw_code, normalized in raw_to_normalized.items()
        }
        return frame.reset_index(drop=True), column_labels

    @staticmethod
    def _safe_column_name(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        snake = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_value).strip("_").lower()
        return snake
