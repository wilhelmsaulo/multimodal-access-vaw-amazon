from __future__ import annotations

from typing import Iterable

import httpx
import pandas as pd

HOSPITAL_BEDS_API = "https://apidadosabertos.saude.gov.br/assistencia-a-saude/hospitais-e-leitos"


def _payload_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("hospitais", "estabelecimentos", "items", "results", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def fetch_hospital_beds_pa(
    *,
    client: httpx.Client | None = None,
    page_size: int = 1000,
    max_pages: int | None = None,
) -> pd.DataFrame:
    """Fetch official hospital/bed records for Pará from DEMAS.

    The official Swagger documents `uf`, `limit` (<=1000) and zero-based `offset`.
    The raw schema is preserved because field names may evolve independently of this project.
    """
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000")
    own_client = client is None
    client = client or httpx.Client(timeout=120.0, follow_redirects=True)
    frames: list[pd.DataFrame] = []
    try:
        offset = 0
        while max_pages is None or offset < max_pages:
            response = client.get(
                HOSPITAL_BEDS_API,
                params={"uf": "PA", "limit": page_size, "offset": offset},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            rows = _payload_rows(response.json())
            if not rows:
                break
            page = pd.DataFrame(rows)
            frames.append(page)
            if len(page) < page_size:
                break
            offset += 1
    finally:
        if own_client:
            client.close()
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _first_numeric(frame: pd.DataFrame, candidates: Iterable[str]) -> pd.Series:
    for col in candidates:
        if col in frame.columns:
            return pd.to_numeric(frame[col], errors="coerce")
    return pd.Series(float("nan"), index=frame.index)


def _first_text(frame: pd.DataFrame, candidates: Iterable[str]) -> pd.Series:
    for col in candidates:
        if col in frame.columns:
            return frame[col].astype("string")
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def summarize_beds_by_cnes(raw: pd.DataFrame) -> pd.DataFrame:
    """Create a conservative CNES-level bed-capacity table when the raw schema permits it.

    No capacity is fabricated: if neither a CNES identifier nor a recognizable bed-count field
    exists, an empty table is returned and the raw extract remains available for audit.
    """
    if raw.empty:
        return pd.DataFrame(columns=["codigo_cnes", "capacity", "capacity_type", "capacity_source"])
    cnes = _first_text(
        raw,
        ["codigo_cnes", "cnes", "co_cnes", "CO_CNES", "cod_cnes", "CNES"],
    )
    beds = _first_numeric(
        raw,
        [
            "quantidade_leitos",
            "qt_leitos",
            "qtd_leitos",
            "total_leitos",
            "leitos_total",
            "QT_EXIST",
            "qt_exist",
        ],
    )
    usable = cnes.notna() & beds.notna() & (beds >= 0)
    if not usable.any():
        return pd.DataFrame(columns=["codigo_cnes", "capacity", "capacity_type", "capacity_source"])
    table = pd.DataFrame({"codigo_cnes": cnes[usable].str.replace(r"\.0$", "", regex=True), "beds": beds[usable]})
    table = table.groupby("codigo_cnes", as_index=False)["beds"].sum()
    table = table.rename(columns={"beds": "capacity"})
    table["capacity_type"] = "registered_beds"
    table["capacity_source"] = "DEMAS hospitais-e-leitos"
    return table
