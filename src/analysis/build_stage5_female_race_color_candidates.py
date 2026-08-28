from __future__ import annotations

"""Acquire female municipal race/color composition for Stage 5 SOM.

Official source: IBGE Census 2022 universe results, SIDRA aggregate/table 9606
(População residente, por cor ou raça, segundo o sexo e a idade).

The script resolves official category identifiers from metadata and retrieves
female, all-age counts for Branca, Preta, Parda, Amarela and Indígena. The
female total in the same table is used as denominator. No unavailable value is
filled synthetically.
"""

import json
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd

API_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
AGGREGATE = 9606
PERIOD = "2022"
EXPECTED_MUNICIPALITIES = 144
PARA_UF_CODE = "15"
RACE_NAMES = ["Branca", "Preta", "Parda", "Amarela", "Indígena"]
RACE_COLUMNS = {
    "Branca": "socio__female_race_share_branca",
    "Preta": "socio__female_race_share_preta",
    "Parda": "socio__female_race_share_parda",
    "Amarela": "socio__female_race_share_amarela",
    "Indígena": "socio__female_race_share_indigena",
}


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


def find_classification(metadata: dict[str, Any], *tokens: str) -> dict[str, Any]:
    for classification in metadata.get("classificacoes", []):
        name = norm(classification.get("nome", ""))
        if all(norm(t) in name for t in tokens):
            return classification
    raise RuntimeError(
        f"Classification tokens={tokens} not found; available="
        f"{[(c.get('id'), c.get('nome')) for c in metadata.get('classificacoes', [])]}"
    )


def find_category(classification: dict[str, Any], exact_name: str) -> tuple[str, str]:
    for category_id, label in iter_categories(classification):
        if norm(label) == norm(exact_name):
            return category_id, label
    raise RuntimeError(
        f"Category {exact_name!r} not found in {classification.get('nome')}: {list(iter_categories(classification))}"
    )


def parse_numeric(value: object) -> float | None:
    text = str(value).strip()
    if text == "-":
        return 0.0
    if text in {"...", "..", "X", "None", "nan"}:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def extract_population(payload: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variable in payload:
        variable_name = str(variable.get("variavel") or variable.get("nome") or "")
        unit = str(variable.get("unidade") or "")
        nv = norm(variable_name)
        if "populacao residente" not in nv or "percentual" in nv or norm(unit) not in {"pessoas", "pessoa"}:
            continue
        for result in variable.get("resultados", []):
            for entry in result.get("series", []):
                locality = entry.get("localidade", {})
                rows.append(
                    {
                        "municipality_code": str(locality.get("id", "")),
                        "municipality_name": str(locality.get("nome", "")),
                        "value": parse_numeric(entry.get("serie", {}).get(PERIOD)),
                    }
                )
    return pd.DataFrame(rows)


def query_category(
    client: httpx.Client,
    sex_class: str,
    women_cat: str,
    age_class: str,
    age_total_cat: str,
    race_class: str,
    race_cat: str,
) -> tuple[pd.DataFrame, str]:
    classification = f"{sex_class}[{women_cat}]|{age_class}[{age_total_cat}]|{race_class}[{race_cat}]"
    locations = f"N6[N3[{PARA_UF_CODE}]]"
    url = (
        f"{API_BASE}/{AGGREGATE}/periodos/{PERIOD}/variaveis?"
        f"localidades={quote(locations, safe='[]')}"
        f"&classificacao={quote(classification, safe='[]|')}"
    )
    payload = get_json(client, url)
    frame = extract_population(payload)
    if frame.empty:
        raise RuntimeError(f"Table 9606 returned no population rows for classification {classification}")
    frame["municipality_code"] = frame["municipality_code"].astype(str).str.extract(r"(\d{7})", expand=False)
    frame = frame[frame["municipality_code"].str.startswith(PARA_UF_CODE, na=False)].copy()
    if frame["value"].isna().any():
        bad = frame.loc[frame["value"].isna(), ["municipality_code", "municipality_name"]]
        raise RuntimeError(f"Unavailable/suppressed race values in table 9606: {bad.to_dict(orient='records')[:10]}")
    grouped = frame.groupby("municipality_code", as_index=False).agg(
        municipality_name=("municipality_name", "first"),
        value=("value", "sum"),
    )
    if len(grouped) != EXPECTED_MUNICIPALITIES or grouped["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(
            f"Expected 144 municipalities from table 9606, got rows={len(grouped)}, unique={grouped['municipality_code'].nunique()}"
        )
    return grouped, url


def main() -> None:
    out = Path("results/stage5/tables")
    out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=90, follow_redirects=True) as client:
        metadata = get_json(client, f"{API_BASE}/{AGGREGATE}/metadados")
        sex = find_classification(metadata, "sexo")
        age = find_classification(metadata, "idade")
        race = find_classification(metadata, "cor", "raca")

        sex_id, women_id = str(sex["id"]), find_category(sex, "Mulheres")[0]
        age_id, age_total_id = str(age["id"]), find_category(age, "Total")[0]
        race_id = str(race["id"])
        race_total_id = find_category(race, "Total")[0]
        race_ids = {name: find_category(race, name)[0] for name in RACE_NAMES}

        total, total_url = query_category(client, sex_id, women_id, age_id, age_total_id, race_id, race_total_id)
        race_frames: dict[str, pd.DataFrame] = {}
        race_urls: dict[str, str] = {}
        for name, category_id in race_ids.items():
            race_frames[name], race_urls[name] = query_category(
                client, sex_id, women_id, age_id, age_total_id, race_id, category_id
            )

    result = total.rename(columns={"value": "diagnostic__female_population_9606"})
    for name, frame in race_frames.items():
        count_col = f"female_race_{norm(name).replace(' ', '_')}_count"
        result = result.merge(
            frame[["municipality_code", "value"]].rename(columns={"value": count_col}),
            on="municipality_code",
            how="left",
            validate="one_to_one",
        )
        result[RACE_COLUMNS[name]] = result[count_col] / result["diagnostic__female_population_9606"].replace(0, pd.NA)

    share_cols = list(RACE_COLUMNS.values())
    result["diagnostic__female_race_declared_share_sum"] = result[share_cols].sum(axis=1)
    result["diagnostic__female_race_residual_share"] = 1.0 - result["diagnostic__female_race_declared_share_sum"]

    if result[share_cols].isna().any().any():
        raise RuntimeError("Female race/color shares contain missing values")
    if ((result[share_cols] < 0) | (result[share_cols] > 1)).any().any():
        raise RuntimeError("Female race/color shares fall outside [0,1]")
    if (result["diagnostic__female_race_residual_share"] < -1e-10).any():
        raise RuntimeError("Female race/color declared categories exceed female total")

    result = result.sort_values("municipality_code").reset_index(drop=True)
    result.to_csv(out / "stage5_female_race_color_candidates.csv", index=False)

    audit = {
        "stage": "Stage 5 female race/color acquisition audit",
        "source": "IBGE Census 2022 universe results via SIDRA table 9606",
        "sidra_table": AGGREGATE,
        "period": int(PERIOD),
        "municipalities": int(result["municipality_code"].nunique()),
        "female_specific": True,
        "all_ages": True,
        "universe_results": True,
        "candidate_features": share_cols,
        "missing_share_cells": int(result[share_cols].isna().sum().sum()),
        "zero_counts": {col: int((result[col] == 0).sum()) for col in share_cols},
        "declared_share_sum_min": float(result["diagnostic__female_race_declared_share_sum"].min()),
        "declared_share_sum_median": float(result["diagnostic__female_race_declared_share_sum"].median()),
        "declared_share_sum_max": float(result["diagnostic__female_race_declared_share_sum"].max()),
        "residual_share_max": float(result["diagnostic__female_race_residual_share"].max()),
        "resolved_categories": {name: race_ids[name] for name in RACE_NAMES},
        "request_urls": {"total": total_url, **race_urls},
        "replacement_decision": "Use female-specific table 9606 composition for Stage 5 SOM instead of total-population table 9605. Preserve 9605 only as an earlier audit artifact.",
        "interpretation_warning": "Race/color composition is a descriptive municipal profile block, not a violence-risk score or normative hierarchy.",
    }
    (out / "stage5_female_race_color_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
