from __future__ import annotations

"""Acquire complete municipal female age composition for Stage 5 SOM.

Official source: IBGE Census 2022 universe results, SIDRA aggregate/table 9514
(População residente, por sexo, idade e forma de declaração da idade).

This replaces the *SOM age-profile candidate* previously derived from incomplete
sector-level age fields. It does not modify Stage 3/4 MCDM inputs or results.
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd

API_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
AGGREGATE = 9514
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


def grouped_age_categories(age_class: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    groups: dict[str, list[tuple[str, str]]] = {"15_29": [], "30_59": [], "60_plus": []}
    for category_id, label in iter_categories(age_class):
        n = norm(label)
        match = re.fullmatch(r"(\d+) a (\d+) anos", n)
        if match:
            lo, hi = int(match.group(1)), int(match.group(2))
            if 15 <= lo and hi <= 29:
                groups["15_29"].append((category_id, label))
            elif 30 <= lo and hi <= 59:
                groups["30_59"].append((category_id, label))
            elif lo >= 60:
                groups["60_plus"].append((category_id, label))
            continue
        match_plus = re.fullmatch(r"(\d+) anos ou mais", n)
        if match_plus and int(match_plus.group(1)) >= 60:
            groups["60_plus"].append((category_id, label))

    def interval_bounds(label: str) -> tuple[int, int]:
        n = norm(label)
        m = re.fullmatch(r"(\d+) a (\d+) anos", n)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.fullmatch(r"(\d+) anos ou mais", n)
        if m:
            return int(m.group(1)), 200
        raise ValueError(label)

    for key in groups:
        groups[key].sort(key=lambda item: interval_bounds(item[1])[0])
    # Require exact coverage boundaries for the first two bands and a 60+ start.
    if not groups["15_29"] or interval_bounds(groups["15_29"][0][1])[0] != 15 or interval_bounds(groups["15_29"][-1][1])[1] != 29:
        raise RuntimeError(f"Could not resolve complete grouped ages 15–29: {groups['15_29']}")
    if not groups["30_59"] or interval_bounds(groups["30_59"][0][1])[0] != 30 or interval_bounds(groups["30_59"][-1][1])[1] != 59:
        raise RuntimeError(f"Could not resolve complete grouped ages 30–59: {groups['30_59']}")
    if not groups["60_plus"] or interval_bounds(groups["60_plus"][0][1])[0] != 60:
        raise RuntimeError(f"Could not resolve complete grouped ages 60+: {groups['60_plus']}")
    return groups


def parse_numeric(value: object) -> float | None:
    text = str(value).strip()
    if text in {"-", "...", "..", "X", "None", "nan"}:
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
                code = str(locality.get("id", ""))
                value = parse_numeric(entry.get("serie", {}).get(PERIOD))
                rows.append(
                    {
                        "municipality_code": code,
                        "municipality_name": str(locality.get("nome", "")),
                        "value": value,
                    }
                )
    return pd.DataFrame(rows)


def query_age_set(
    client: httpx.Client,
    sex_class: str,
    women_cat: str,
    declaration_class: str,
    declaration_total: str,
    age_class: str,
    age_categories: list[str],
) -> tuple[pd.DataFrame, str]:
    age_part = ",".join(age_categories)
    classification = (
        f"{sex_class}[{women_cat}]|{declaration_class}[{declaration_total}]|{age_class}[{age_part}]"
    )
    locations = f"N6[N3[{PARA_UF_CODE}]]"
    url = (
        f"{API_BASE}/{AGGREGATE}/periodos/{PERIOD}/variaveis?"
        f"localidades={quote(locations, safe='[]')}"
        f"&classificacao={quote(classification, safe='[]|,')}"
    )
    payload = get_json(client, url)
    frame = extract_population(payload)
    if frame.empty:
        raise RuntimeError(f"Table 9514 returned no population rows for classification {classification}")
    frame["municipality_code"] = frame["municipality_code"].astype(str).str.extract(r"(\d{7})", expand=False)
    frame = frame[frame["municipality_code"].str.startswith(PARA_UF_CODE, na=False)].copy()
    if frame["value"].isna().any():
        bad = frame.loc[frame["value"].isna(), ["municipality_code", "municipality_name"]]
        raise RuntimeError(f"Unavailable/suppressed age values in table 9514: {bad.to_dict(orient='records')[:10]}")
    grouped = frame.groupby("municipality_code", as_index=False).agg(
        municipality_name=("municipality_name", "first"),
        value=("value", "sum"),
    )
    if len(grouped) != EXPECTED_MUNICIPALITIES or grouped["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(
            f"Expected 144 municipalities from table 9514, got rows={len(grouped)}, unique={grouped['municipality_code'].nunique()}"
        )
    return grouped, url


def main() -> None:
    out = Path("results/stage5/tables")
    out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=90, follow_redirects=True) as client:
        metadata = get_json(client, f"{API_BASE}/{AGGREGATE}/metadados")
        sex = find_classification(metadata, "sexo")
        age = find_classification(metadata, "idade")
        declaration = find_classification(metadata, "forma", "declaracao")
        sex_id, women_id = str(sex["id"]), find_category(sex, "Mulheres")[0]
        age_id, age_total_id = str(age["id"]), find_category(age, "Total")[0]
        declaration_id, declaration_total_id = str(declaration["id"]), find_category(declaration, "Total")[0]
        groups = grouped_age_categories(age)

        total, total_url = query_age_set(
            client, sex_id, women_id, declaration_id, declaration_total_id, age_id, [age_total_id]
        )
        band_frames: dict[str, pd.DataFrame] = {}
        band_urls: dict[str, str] = {}
        for band, categories in groups.items():
            band_frames[band], band_urls[band] = query_age_set(
                client,
                sex_id,
                women_id,
                declaration_id,
                declaration_total_id,
                age_id,
                [category_id for category_id, _ in categories],
            )

    result = total.rename(columns={"value": "diagnostic__female_population_9514"})
    for band, frame in band_frames.items():
        result = result.merge(
            frame[["municipality_code", "value"]].rename(columns={"value": f"female_{band}_count"}),
            on="municipality_code",
            how="left",
            validate="one_to_one",
        )
    denom = result["diagnostic__female_population_9514"].replace(0, pd.NA)
    result["socio__female_age_share_15_29"] = result["female_15_29_count"] / denom
    result["socio__female_age_share_30_59"] = result["female_30_59_count"] / denom
    result["socio__female_age_share_60_plus"] = result["female_60_plus_count"] / denom
    share_cols = [
        "socio__female_age_share_15_29",
        "socio__female_age_share_30_59",
        "socio__female_age_share_60_plus",
    ]
    result["diagnostic__female_age_selected_share_sum"] = result[share_cols].sum(axis=1)

    if result[share_cols].isna().any().any():
        raise RuntimeError("Complete municipal female age shares contain missing values")
    if ((result[share_cols] < 0) | (result[share_cols] > 1)).any().any():
        raise RuntimeError("Complete municipal female age shares fall outside [0,1]")

    result = result.sort_values("municipality_code").reset_index(drop=True)
    result.to_csv(out / "stage5_complete_female_age_candidate.csv", index=False)

    audit = {
        "stage": "Stage 5 complete municipal female age acquisition audit",
        "source": "IBGE Census 2022 universe results via SIDRA table 9514",
        "sidra_table": AGGREGATE,
        "period": int(PERIOD),
        "municipalities": int(result["municipality_code"].nunique()),
        "female_specific": True,
        "universe_results": True,
        "missing_share_cells": int(result[share_cols].isna().sum().sum()),
        "candidate_features": share_cols,
        "resolved_age_categories": {
            band: [{"id": category_id, "label": label} for category_id, label in categories]
            for band, categories in groups.items()
        },
        "selected_share_sum_min": float(result["diagnostic__female_age_selected_share_sum"].min()),
        "selected_share_sum_median": float(result["diagnostic__female_age_selected_share_sum"].median()),
        "selected_share_sum_max": float(result["diagnostic__female_age_selected_share_sum"].max()),
        "request_urls": {"total": total_url, **band_urls},
        "source_note": "IBGE corrected tables 1209, 9514 and 9515 on 2023-12-22 for Abel Figueiredo (PA) / São Pedro da Água Branca (MA); the current API is the corrected dissemination.",
        "replacement_decision": "For Stage 5 SOM profiling, use complete municipality-level table 9514 age shares instead of the partial sector-derived age shares. Stage 3/4 MCDM remains unchanged.",
    }
    (out / "stage5_complete_female_age_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
