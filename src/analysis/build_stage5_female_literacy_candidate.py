from __future__ import annotations

"""Acquire and audit the female 15+ literacy profile candidate for Stage 5 SOM.

Official source: IBGE Census 2022, SIDRA aggregate/table 9543.  The script uses
IBGE's Aggregates API metadata to resolve category identifiers by label rather
than hard-coding undocumented category codes.
"""

import json
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd

API_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
AGGREGATE = 9543
PERIOD = "2022"
EXPECTED_MUNICIPALITIES = 144
PARA_UF_CODE = "15"


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def get_json(client: httpx.Client, url: str) -> Any:
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def iter_categories(classification: dict[str, Any]):
    cats = classification.get("categorias", [])
    if isinstance(cats, dict):
        for key, value in cats.items():
            if isinstance(value, dict):
                yield str(value.get("id", key)), str(value.get("nome", value.get("name", "")))
            else:
                yield str(key), str(value)
    elif isinstance(cats, list):
        for value in cats:
            if isinstance(value, dict):
                yield str(value.get("id", value.get("codigo", ""))), str(value.get("nome", value.get("name", "")))


def resolve_classification(metadata: dict[str, Any], class_name: str, category_name: str) -> tuple[str, str]:
    for classification in metadata.get("classificacoes", []):
        if norm(classification.get("nome", "")) != norm(class_name):
            continue
        class_id = str(classification.get("id"))
        for category_id, category_label in iter_categories(classification):
            if norm(category_label) == norm(category_name):
                return class_id, category_id
        raise RuntimeError(
            f"Classification {class_name!r} found but category {category_name!r} was not found: "
            f"{list(iter_categories(classification))}"
        )
    raise RuntimeError(
        f"Classification {class_name!r} not found; available="
        f"{[(c.get('id'), c.get('nome')) for c in metadata.get('classificacoes', [])]}"
    )


def extract_series(payload: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variable in payload:
        variable_name = variable.get("variavel") or variable.get("nome") or ""
        unit = variable.get("unidade") or ""
        for result in variable.get("resultados", []):
            classifications = result.get("classificacoes", [])
            series_entries = result.get("series", [])
            for entry in series_entries:
                locality = entry.get("localidade", {})
                code = str(locality.get("id", ""))
                name = str(locality.get("nome", ""))
                values = entry.get("serie", {})
                value = values.get(PERIOD)
                rows.append(
                    {
                        "municipality_code": code,
                        "municipality_name": name,
                        "value": value,
                        "variable": variable_name,
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
        sex_class, women_cat = resolve_classification(metadata, "Sexo", "Mulheres")
        race_class, race_total_cat = resolve_classification(metadata, "Cor ou raça", "Total")
        age_class, age_total_cat = resolve_classification(metadata, "Idade", "Total")

        classification = f"{sex_class}[{women_cat}]|{race_class}[{race_total_cat}]|{age_class}[{age_total_cat}]"
        locations = f"N6[N3[{PARA_UF_CODE}]]"
        url = (
            f"{API_BASE}/{AGGREGATE}/periodos/{PERIOD}/variaveis?"
            f"localidades={quote(locations, safe='[]')}"
            f"&classificacao={quote(classification, safe='[]|')}"
        )
        payload = get_json(client, url)

    frame = extract_series(payload)
    if frame.empty:
        raise RuntimeError("IBGE aggregate 9543 returned no female 15+ municipal literacy results")

    frame["municipality_code"] = frame["municipality_code"].astype(str).str.extract(r"(\d{7})", expand=False)
    frame = frame[frame["municipality_code"].str.startswith(PARA_UF_CODE, na=False)].copy()
    frame["value_numeric"] = pd.to_numeric(frame["value"].astype(str).str.replace(",", ".", regex=False), errors="coerce")

    # The aggregate contains only one variable (literacy rate). If the API ever
    # exposes more than one, select the explicitly named rate and fail otherwise.
    if frame["variable"].nunique() > 1:
        rate_mask = frame["variable"].map(norm).str.contains("taxa de alfabetizacao", na=False)
        frame = frame[rate_mask].copy()

    frame = frame.sort_values("municipality_code").drop_duplicates("municipality_code")
    if len(frame) != EXPECTED_MUNICIPALITIES or frame["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(
            f"Expected 144 Pará municipalities for female literacy, got rows={len(frame)}, "
            f"unique={frame['municipality_code'].nunique()}"
        )
    if frame["value_numeric"].isna().any():
        bad = frame.loc[frame["value_numeric"].isna(), ["municipality_code", "municipality_name", "value"]]
        raise RuntimeError(f"Female literacy contains unavailable/suppressed values: {bad.to_dict(orient='records')}")

    rate = frame["value_numeric"].copy()
    # SIDRA 9543 is expressed as percent. Guard against a future API unit change.
    if rate.max() > 1.0:
        rate = rate / 100.0
    if ((rate < 0) | (rate > 1)).any():
        raise RuntimeError("Female literacy rate falls outside [0,1] after unit normalization")

    result = frame[["municipality_code", "municipality_name"]].copy()
    result["socio__female_literacy_rate_15plus"] = rate.to_numpy()
    result["diagnostic__female_illiteracy_rate_15plus"] = 1.0 - rate.to_numpy()
    result.to_csv(out / "stage5_female_literacy_candidate.csv", index=False)

    audit = {
        "stage": "Stage 5 SOM female literacy acquisition audit",
        "source": "IBGE Census 2022 literacy universe results via Aggregates/SIDRA table 9543",
        "sidra_table": AGGREGATE,
        "period": int(PERIOD),
        "state": "Pará",
        "territorial_level": "municipality",
        "municipalities": int(result["municipality_code"].nunique()),
        "sex": "Mulheres",
        "age_universe": "15 years or older (table universe; age category Total)",
        "race_color_category": "Total",
        "candidate_feature": "socio__female_literacy_rate_15plus",
        "illiteracy_complement_role": "diagnostic_only_due_to_perfect_redundancy",
        "missing_values": int(result["socio__female_literacy_rate_15plus"].isna().sum()),
        "literacy_rate_min": float(result["socio__female_literacy_rate_15plus"].min()),
        "literacy_rate_median": float(result["socio__female_literacy_rate_15plus"].median()),
        "literacy_rate_max": float(result["socio__female_literacy_rate_15plus"].max()),
        "resolved_classifications": {
            "sex": {"classification_id": sex_class, "category_id": women_cat},
            "race_color": {"classification_id": race_class, "category_id": race_total_cat},
            "age": {"classification_id": age_class, "category_id": age_total_cat},
        },
        "interpretation_warning": "Female literacy is a socioeconomic profile descriptor for SOM, not a violence-risk score.",
        "request_url": url,
    }
    (out / "stage5_female_literacy_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
