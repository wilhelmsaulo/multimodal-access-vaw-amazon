"""Reused with adaptation from https://github.com/wilhelmsaulo/explainable-municipal-prioritization-framework/blob/main/src/empriority/provenance.py (blob 03d5dc0eab0f65306b78fd18301590c3f188d846).
Authorized by the repository owner for this project; provenance retained pending final licensing audit.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CollectionMetadata:
    """Auditable metadata recorded for every external data collection."""

    source: str
    endpoint: str
    collected_at_utc: str
    parameters: dict[str, Any]
    record_count: int
    column_labels: dict[str, str]

    @classmethod
    def create(
        cls,
        *,
        source: str,
        endpoint: str,
        parameters: dict[str, Any],
        record_count: int,
        column_labels: dict[str, str] | None = None,
    ) -> CollectionMetadata:
        return cls(
            source=source,
            endpoint=endpoint,
            collected_at_utc=datetime.now(UTC).isoformat(),
            parameters=parameters,
            record_count=record_count,
            column_labels=column_labels or {},
        )

    def write_json(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return output_path
