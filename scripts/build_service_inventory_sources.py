from __future__ import annotations

import argparse
import hashlib
import json
import time
from io import BytesIO
from pathlib import Path

import httpx
import pandas as pd

from src.data.health_capacity import fetch_hospital_beds_pa, summarize_beds_by_cnes
from src.data.service_inventory import (
    fetch_cnes_establishments_pa,
    filter_cnes_vaw_relevant,
    validate_cnes_health_destinations,
)


CREAS_SAGI_URL = (
    "https://aplicacoes.mds.gov.br/sagi/servicos/equipamentos"
    "?q=tipo_equipamento:CREAS&wt=csv"
    "&fl=id_equipamento,ibge,uf,cidade,nome,responsavel,telefone,endereco,numero,"
    "complemento,referencia,bairro,cep,georef_location,data_atualizacao"
    "&rows=999999999"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get_with_retries(
    client: httpx.Client,
    url: str,
    *,
    retries: int = 7,
    backoff_seconds: float = 1.5,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.get(url)
            response.raise_for_status()
            return response
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(backoff_seconds * (2**attempt))
    assert last_error is not None
    raise last_error


def _read_csv_bytes(data: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8", "latin1"):
        try:
            return pd.read_csv(BytesIO(data), encoding=encoding)
        except Exception as exc:  # pragma: no cover - alternate source encodings
            last_error = exc
    assert last_error is not None
    raise ValueError(f"Could not parse SAGI CREAS CSV: {last_error}")


def download_creas_sagi_pa(out_dir: Path, client: httpx.Client) -> dict:
    manifest: dict[str, object] = {
        "source": "MDS/SAGI equipment registry",
        "endpoint": CREAS_SAGI_URL,
        "query": "tipo_equipamento:CREAS",
        "source_status": "available",
        "source_error": None,
        "rows_total": 0,
        "rows_para": 0,
        "rows_para_with_georef": 0,
        "sha256": None,
        "columns": [],
        "primary_supply_rule": "One validated CREAS physical unit equals one supply opportunity within the CREAS category.",
        "capacity_rule": "Observed capacity is optional and is not required for the primary accessibility analysis.",
    }
    try:
        response = _get_with_retries(client, CREAS_SAGI_URL)
        data = response.content
        raw = _read_csv_bytes(data)
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        manifest["source_status"] = "temporarily_unavailable"
        manifest["source_error"] = f"{type(exc).__name__}: {exc}"
        (out_dir / "creas_sagi_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest

    required = {"id_equipamento", "ibge", "uf", "cidade", "nome", "georef_location", "data_atualizacao"}
    missing = required.difference(raw.columns)
    if missing:
        manifest["source_status"] = "invalid_schema"
        manifest["source_error"] = f"Missing expected SAGI columns: {sorted(missing)}"
        manifest["rows_total"] = int(len(raw))
        manifest["columns"] = [str(c) for c in raw.columns]
        (out_dir / "creas_sagi_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest

    pa = raw.loc[raw["uf"].astype(str).str.strip().str.upper().eq("PA")].copy()
    pa.to_csv(out_dir / "creas_sagi_pa.csv", index=False)

    georef = pa["georef_location"].astype("string").str.strip()
    manifest.update(
        {
            "rows_total": int(len(raw)),
            "rows_para": int(len(pa)),
            "rows_para_with_georef": int(georef.notna().sum()),
            "sha256": sha256_bytes(data),
            "columns": [str(c) for c in raw.columns],
        }
    )
    (out_dir / "creas_sagi_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def build_cnes(out_dir: Path) -> dict:
    raw = fetch_cnes_establishments_pa(page_size=20)
    raw.to_csv(out_dir / "cnes_pa_active_raw.csv", index=False)
    screened = filter_cnes_vaw_relevant(raw)
    candidates = validate_cnes_health_destinations(screened)
    candidates.to_csv(out_dir / "cnes_pa_vaw_health_candidates.csv", index=False)

    beds_status = "available"
    beds_error: str | None = None
    try:
        beds_raw = fetch_hospital_beds_pa(page_size=250, retries=4, backoff_seconds=2.0)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        beds_status = "temporarily_unavailable"
        beds_error = f"{type(exc).__name__}: {exc}"
        beds_raw = pd.DataFrame()

    beds_raw.to_csv(out_dir / "hospital_beds_pa_raw.csv", index=False)
    beds_summary = summarize_beds_by_cnes(beds_raw)
    beds_summary.to_csv(out_dir / "hospital_beds_pa_by_cnes.csv", index=False)

    eligible = candidates.get("primary_function_eligible", pd.Series(False, index=candidates.index)).fillna(False).astype(bool)
    function_counts = (
        candidates.get("vaw_health_function", pd.Series(dtype="object"))
        .value_counts(dropna=False)
        .to_dict()
    )
    manifest = {
        "source": "DEMAS CNES API + hospitais-e-leitos",
        "establishments_endpoint": "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos",
        "beds_endpoint": "https://apidadosabertos.saude.gov.br/assistencia-a-saude/hospitais-e-leitos",
        "uf_code": 15,
        "status": 1,
        "rows_active_para": int(len(raw)),
        "rows_vaw_health_screened": int(len(screened)),
        "rows_vaw_health_primary_function_eligible": int(eligible.sum()),
        "rows_vaw_health_not_primary": int((~eligible).sum()),
        "function_validation_counts": {str(k): int(v) for k, v in function_counts.items()},
        "beds_source_status": beds_status,
        "beds_source_error": beds_error,
        "rows_hospital_beds_raw": int(len(beds_raw)),
        "rows_hospital_beds_cnes_summary": int(len(beds_summary)),
        "raw_columns": [str(c) for c in raw.columns],
        "beds_raw_columns": [str(c) for c in beds_raw.columns],
        "primary_supply_rule": "One function-validated fixed health service unit equals one supply opportunity within the health category.",
        "function_validation_rule": (
            "Primary health destinations must be fixed acute/hospital/obstetric care, CAPS psychosocial care, "
            "or explicitly named women's-health/maternity/sexual-violence services. Mobile units and regulation/administrative centers are excluded."
        ),
        "capacity_rule": (
            "registered beds are retained only when an exact CNES match exists; "
            "capacity is optional and reserved for health-specific sensitivity analysis"
        ),
    }
    (out_dir / "cnes_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/service_inventory"))
    parser.add_argument("--skip-cnes", action="store_true")
    parser.add_argument("--skip-creas", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {}
    if not args.skip_cnes:
        summary["cnes"] = build_cnes(args.output_dir)
    if not args.skip_creas:
        timeout = httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0)
        headers = {
            "User-Agent": "multimodal-access-vaw-amazon/1.0 (research data retrieval)",
            "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            summary["creas"] = download_creas_sagi_pa(args.output_dir, client)
    (args.output_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
