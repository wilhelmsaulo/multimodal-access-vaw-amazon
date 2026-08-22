from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import httpx
import pandas as pd


CNES_API = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
TJPA_CONTACTS = "https://centralservicos.tjpa.jus.br/bv/todos.php"

# Legacy CNES establishment-type codes documented by DATASUS. These are used
# only to validate that a candidate is a fixed assistential destination; they
# are not used as capacity weights.
CNES_FIXED_ACUTE_OR_OBSTETRIC_TYPES = {5, 7, 15, 20, 21, 61, 73}
CNES_PSYCHOSOCIAL_TYPE = 70
CNES_NON_FIXED_OR_ADMIN_TYPES = {32, 40, 42, 60, 76}


@dataclass(frozen=True)
class ServiceInventoryRecord:
    service_id: str
    service_name: str
    service_type: str
    provider_source: str
    municipality_code: str | None
    municipality_name: str | None
    address_public: str | None
    latitude: float | None
    longitude: float | None
    capacity: float | None
    capacity_type: str | None
    capacity_source: str | None
    reference_date: str | None
    validation_status: str
    redistribution_status: str


def fetch_cnes_establishments_pa(
    *,
    client: httpx.Client | None = None,
    status: int = 1,
    page_size: int = 20,
    max_pages: int | None = None,
) -> pd.DataFrame:
    """Fetch active CNES establishments for Pará from the official DEMAS API."""
    if not 1 <= page_size <= 20:
        raise ValueError("CNES page_size must be between 1 and 20.")
    own_client = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True)
    frames: list[pd.DataFrame] = []
    try:
        offset = 0
        while max_pages is None or offset < max_pages:
            response = client.get(
                CNES_API,
                params={"codigo_uf": 15, "status": status, "limit": page_size, "offset": offset},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                rows = (
                    payload.get("estabelecimentos")
                    or payload.get("items")
                    or payload.get("results")
                    or payload.get("data")
                    or []
                )
            elif isinstance(payload, list):
                rows = payload
            else:
                raise ValueError("Unexpected CNES API response type.")
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
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def filter_cnes_vaw_relevant(
    establishments: pd.DataFrame,
    *,
    name_columns: Iterable[str] = (
        "nome_fantasia",
        "nome_razao_social",
        "nome_empresarial",
        "descricao_tipo_unidade",
        "tipo_unidade",
    ),
) -> pd.DataFrame:
    """Conservative screening of potentially VAW-relevant health establishments.

    This step deliberately over-includes candidates. Final primary-routing
    eligibility is assigned by :func:`validate_cnes_health_destinations` using
    official establishment type plus explicit service naming.
    """
    candidates = [c for c in name_columns if c in establishments.columns]
    if not candidates:
        return establishments.iloc[0:0].copy()
    text = establishments[candidates].fillna("").astype(str).agg(" ".join, axis=1).str.upper()
    pattern = re.compile(
        r"HOSPITAL|PRONTO\s*ATENDIMENTO|URG[EÊ]NCIA|EMERG[EÊ]NCIA|CAPS|"
        r"MATERNIDADE|SA[ÚU]DE\s+DA\s+MULHER|VIOL[EÊ]NCIA\s+SEXUAL"
    )
    return establishments[text.str.contains(pattern, regex=True)].copy()


def validate_cnes_health_destinations(candidates: pd.DataFrame) -> pd.DataFrame:
    """Assign an auditable health-function status to screened CNES candidates.

    Primary destinations are fixed facilities in one of four defensible groups:
    acute/hospital care, obstetric/maternity care, psychosocial care (CAPS), or
    an explicitly named women's-health/sexual-violence service. Mobile units,
    regulation centers and other non-fixed/administrative types are not treated
    as physical destinations even if their names contain emergency terms.

    This validation concerns service function only. It does not assert quality,
    VAW specialization, available beds, staffing, or actual service capacity.
    """
    if candidates.empty:
        return candidates.copy()
    out = candidates.copy()
    code = pd.to_numeric(out.get("codigo_tipo_unidade"), errors="coerce")
    text_cols = [c for c in ("nome_fantasia", "nome_razao_social", "nome_empresarial") if c in out.columns]
    text = out[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.upper() if text_cols else pd.Series("", index=out.index)

    explicit_women = text.str.contains(
        r"SA[ÚU]DE\s+DA\s+MULHER|ATENDIMENTO\s+(?:A|À)\s+MULHER|"
        r"VIOL[EÊ]NCIA\s+SEXUAL|MATERNIDADE|MATERNO\s*INFANTIL",
        regex=True,
        na=False,
    )
    fixed_core = code.isin(CNES_FIXED_ACUTE_OR_OBSTETRIC_TYPES)
    psychosocial = code.eq(CNES_PSYCHOSOCIAL_TYPE)
    excluded_nonfixed = code.isin(CNES_NON_FIXED_OR_ADMIN_TYPES)

    out["vaw_health_function"] = "screened_unresolved"
    out.loc[fixed_core, "vaw_health_function"] = "fixed_acute_or_obstetric_care"
    out.loc[psychosocial, "vaw_health_function"] = "psychosocial_care"
    out.loc[explicit_women & ~excluded_nonfixed, "vaw_health_function"] = "explicit_womens_health_or_maternity"
    out.loc[excluded_nonfixed, "vaw_health_function"] = "nonfixed_or_administrative_excluded"

    eligible = (fixed_core | psychosocial | explicit_women) & ~excluded_nonfixed
    out["primary_function_eligible"] = eligible
    out["validation_status"] = "screened_candidate_not_primary"
    out.loc[eligible, "validation_status"] = "function_validated_from_official_cnes_type"
    out.loc[excluded_nonfixed, "validation_status"] = "excluded_nonfixed_or_administrative"
    return out


def parse_tjpa_specialized_units(html: str) -> pd.DataFrame:
    """Parse explicitly specialized VAW justice units from the official TJPA directory.

    The directory itself is authoritative evidence that the named judicial unit
    exists and is functionally specialized. This parser does not infer or invent
    a street address or coordinates; location readiness is audited separately.
    """
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"&nbsp;", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    unit_pattern = re.compile(
        r"(?P<name>(?:SECRETARIA DA \d+ª VARA|VARA(?: DO JUIZADO ESPECIAL)?|VARA DE COMBATE|"
        r"VARA DE VIOLENCIA)[^.]{0,180}?(?:VIOL[EÊ]NCIA|VIOLENCIA)[^.]{0,120}?MULHER[^.]{0,120}?)"
        r"\s+Cidade\s*:\s*(?P<city>[A-Za-zÀ-ÿ\s]+?)\s*\|",
        re.I,
    )
    rows = []
    for match in unit_pattern.finditer(text):
        rows.append(
            {
                "service_name": re.sub(r"\s+", " ", match.group("name")).strip(),
                "municipality_name": match.group("city").strip(),
                "service_type": "specialized_justice",
                "provider_source": "TJPA",
                "validation_status": "function_validated_from_official_tjpa_directory",
            }
        )
    return pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame(
        columns=["service_name", "municipality_name", "service_type", "provider_source", "validation_status"]
    )


def fetch_tjpa_specialized_units(client: httpx.Client | None = None) -> pd.DataFrame:
    own_client = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True)
    try:
        response = client.get(TJPA_CONTACTS)
        response.raise_for_status()
        return parse_tjpa_specialized_units(response.text)
    finally:
        if own_client:
            client.close()


def harmonize_manual_service_table(
    table: pd.DataFrame,
    *,
    provider_source: str,
    reference_date: str,
) -> pd.DataFrame:
    """Normalize curated official-directory extracts without inventing missing fields."""
    required = {"service_id", "service_name", "service_type", "municipality_name"}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"Manual service table missing columns: {sorted(missing)}")
    out = table.copy()
    out["provider_source"] = provider_source
    out["reference_date"] = reference_date
    for col in [
        "municipality_code", "address_public", "latitude", "longitude", "capacity",
        "capacity_type", "capacity_source", "validation_status", "redistribution_status",
    ]:
        if col not in out:
            out[col] = pd.NA
    out["validation_status"] = out["validation_status"].fillna("needs_validation")
    out["redistribution_status"] = out["redistribution_status"].fillna("review_required")
    return out
