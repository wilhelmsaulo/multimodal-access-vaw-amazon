from __future__ import annotations

"""Acquire and audit the municipal household per-capita income candidate for Stage 5 SOM.

Official source: IBGE Census 2022 Trabalho e Rendimento, preliminary sample
results, SIDRA aggregate/table 10295. This is an income-profile descriptor and
must not be relabelled as a poverty rate.
"""

import json
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd

API_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
AGGREGATE = 10295
PERIOD = "2022"
EXPECTED_MUNICIPALITIES = 144
PARA_UF_CODE = "15"
MEAN_VARIABLE_ID = "13431"


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def get_json(client: httpx.Client, url: str) -> Any:
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def extract_series(payload: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variable in payload:
        variable_name = str(variable.get("variavel") or variable.get("nome") or "")
        variable_id = str(variable.get("id") or "")
        unit = str(variable.get("unidade") or "")
        for result in variable.get("resultados", []):
            classifications = result.get("classificacoes", [])
            for entry in result.get("series", []):
                locality = entry.get("localidade", {})
                values = entry.get("serie", {})
                rows.append(
                    {
                        "municipality_code": str(locality.get("id", "")),
                        "municipality_name": str(locality.get("nome", "")),
                        "value": values.get(PERIOD),
                        "variable": variable_name,
                        "variable_id": variable_id,
                        "unit": unit,
                        "classifications": json.dumps(classifications, ensure_ascii=False, sort_keys=True),
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    out = Path("results/stage5/tables")
    out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=90, follow_redirects=True) as client:
        metadata = get_json(client, f"{API_BASE}/{AGGREGATE}/metadados")
        locations = f"N6[N3[{PARA_UF_CODE}]]"
        url = (
            f"{API_BASE}/{AGGREGATE}/periodos/{PERIOD}/variaveis?"
            f"localidades={quote(locations, safe='[]')}"
        )
        payload = get_json(client, url)

    frame = extract_series(payload)
    if frame.empty:
        raise RuntimeError("IBGE aggregate 10295 returned no municipal income results")
    frame["municipality_code"] = frame["municipality_code"].astype(str).str.extract(r"(\d{7})", expand=False)
    frame = frame[frame["municipality_code"].str.startswith(PARA_UF_CODE, na=False)].copy()
    frame["value_numeric"] = pd.to_numeric(
        frame["value"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
        errors="coerce",
    )

    # The first audit confirmed that 10295 exposes mean (13431) and median
    # (13534). Select the mean explicitly and keep the median out of the SOM
    # candidate block to avoid an unjustified duplicate representation of income.
    selected = frame[frame["variable_id"].eq(MEAN_VARIABLE_ID)].copy()
    if selected.empty:
        mean_name_mask = frame["variable"].map(norm).str.contains(
            "rendimento nominal medio mensal domiciliar per capita", na=False
        )
        mean_name_mask &= ~frame["variable"].map(norm).str.contains("mediano", na=False)
        selected = frame[mean_name_mask].copy()
    if selected["variable"].nunique() != 1:
        raise RuntimeError(
            f"Could not uniquely select mean income variable 13431: "
            f"{frame[['variable_id','variable','unit']].drop_duplicates().to_dict(orient='records')}"
        )

    selected = selected.sort_values("municipality_code").drop_duplicates("municipality_code")
    if len(selected) != EXPECTED_MUNICIPALITIES or selected["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(
            f"Expected 144 Pará municipalities for income, got rows={len(selected)}, "
            f"unique={selected['municipality_code'].nunique()}"
        )
    if selected["value_numeric"].isna().any():
        bad = selected.loc[selected["value_numeric"].isna(), ["municipality_code", "municipality_name", "value"]]
        raise RuntimeError(f"Income candidate contains unavailable/suppressed values: {bad.to_dict(orient='records')}")
    if (selected["value_numeric"] <= 0).any():
        raise RuntimeError("Income candidate contains non-positive municipal values")

    result = selected[["municipality_code", "municipality_name"]].copy()
    result["socio__household_per_capita_income_mean_brl"] = selected["value_numeric"].to_numpy()
    result.to_csv(out / "stage5_income_candidate.csv", index=False)

    selected_meta = selected[["variable_id", "variable", "unit"]].drop_duplicates().iloc[0].to_dict()
    audit = {
        "stage": "Stage 5 SOM municipal income acquisition audit",
        "source": "IBGE Census 2022 Trabalho e Rendimento — preliminary sample results via SIDRA table 10295",
        "sidra_table": AGGREGATE,
        "period": int(PERIOD),
        "state": "Pará",
        "territorial_level": "municipality",
        "municipalities": int(result["municipality_code"].nunique()),
        "candidate_feature": "socio__household_per_capita_income_mean_brl",
        "selected_variable": selected_meta,
        "excluded_same_construct_variable": {
            "variable_id": "13534",
            "description": "municipal median household per-capita monthly income",
            "reason": "not included alongside mean income without a separate theoretical justification; avoids duplicating the same income construct",
        },
        "missing_values": int(result["socio__household_per_capita_income_mean_brl"].isna().sum()),
        "income_min_brl": float(result["socio__household_per_capita_income_mean_brl"].min()),
        "income_median_across_municipalities_brl": float(result["socio__household_per_capita_income_mean_brl"].median()),
        "income_max_brl": float(result["socio__household_per_capita_income_mean_brl"].max()),
        "sample_based": True,
        "poverty_measure": False,
        "retention_status": "candidate_pending_pre_SOM_gate",
        "methodological_warning": "This is a Census 2022 sample estimate of mean household per-capita monthly income; it is not a direct poverty rate and requires explicit retention review before SOM training.",
        "request_url": url,
        "metadata_name": metadata.get("nome") if isinstance(metadata, dict) else None,
    }
    (out / "stage5_income_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
