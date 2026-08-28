from __future__ import annotations

"""Acquire female municipal race/color composition for Stage 5 SOM.

Official source: IBGE Census 2022 universe results, SIDRA table 9606
(População residente, por cor ou raça, segundo o sexo e a idade).

Operational acquisition uses SIDRA's official values API with the published
classification codes for women and total age. This avoids the unstable
metadata/export routes while keeping the same official table.
"""

import json
import time
import unicodedata
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

EXPECTED_MUNICIPALITIES = 144
RACE_NAMES = ["Branca", "Preta", "Parda", "Amarela", "Indígena"]
RACE_COLUMNS = {
    "Branca": "socio__female_race_share_branca",
    "Preta": "socio__female_race_share_preta",
    "Parda": "socio__female_race_share_parda",
    "Amarela": "socio__female_race_share_amarela",
    "Indígena": "socio__female_race_share_indigena",
}

# 1000093 = População residente; c2/5 = Mulheres; c287/100362 = Total (idade).
# "n6/in n3 15" selects all municipalities contained in Pará.
SIDRA_VALUES_URL = (
    "https://apisidra.ibge.gov.br/values/t/9606/"
    "n6/in%20n3%2015/v/1000093/p/2022/c86/all/c2/5/c287/100362?formato=json"
)


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def get_payload(attempts: int = 4) -> list[dict[str, Any]]:
    timeout = httpx.Timeout(120.0, connect=45.0)
    headers = {"User-Agent": "Stage5-reproducible-research/1.0"}
    last_error: Exception | None = None
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = client.get(SIDRA_VALUES_URL)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list) or len(payload) < 2:
                    raise RuntimeError(f"Unexpected SIDRA payload type/length: {type(payload)}, {len(payload) if isinstance(payload, list) else 'NA'}")
                return payload
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt == attempts:
                    break
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError("Official SIDRA values API failed after retries") from last_error


def parse_value(value: object) -> float | None:
    text = str(value).strip()
    if text == "-":
        return 0.0
    if text in {"...", "..", "X", "None", "nan", ""}:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def main() -> None:
    out = Path("results/stage5/tables")
    out.mkdir(parents=True, exist_ok=True)

    payload = get_payload()
    header = payload[0]
    rows = payload[1:]
    frame = pd.DataFrame(rows)

    # The SIDRA values API returns N6C/N6N for municipality code/name and
    # classification fields such as D2N/D3N/D4N. Resolve by header labels so
    # this remains auditable even if the D-order changes.
    label_by_key = {key: norm(value) for key, value in header.items()}
    code_key = next((k for k, v in label_by_key.items() if "municipio" in v and "codigo" in v), None)
    name_key = next((k for k, v in label_by_key.items() if v == "municipio" or ("municipio" in v and "codigo" not in v)), None)
    value_key = next((k for k, v in label_by_key.items() if v == "valor"), "V")
    race_name_key = next((k for k, v in label_by_key.items() if "cor ou raca" in v and "codigo" not in v), None)

    # Fallbacks follow the stable SIDRA API field convention.
    if code_key is None:
        code_key = "N6C" if "N6C" in frame.columns else "NC"
    if name_key is None:
        name_key = "N6N" if "N6N" in frame.columns else "NN"
    if race_name_key is None:
        race_name_key = next((k for k in frame.columns if k.endswith("N") and frame[k].astype(str).map(norm).isin([norm(x) for x in RACE_NAMES + ["Total"]]).any()), None)
    if race_name_key is None:
        raise RuntimeError(f"Could not resolve race/color classification field. Header={header}")

    parsed = pd.DataFrame({
        "municipality_code": frame[code_key].astype(str).str.extract(r"(\d{7})", expand=False),
        "municipality_name": frame[name_key].astype(str),
        "race": frame[race_name_key].astype(str),
        "value": frame[value_key].map(parse_value),
    })
    parsed = parsed[parsed["municipality_code"].str.startswith("15", na=False)].copy()

    if parsed["value"].isna().any():
        bad = parsed.loc[parsed["value"].isna(), ["municipality_code", "municipality_name", "race"]]
        raise RuntimeError(f"Unavailable/suppressed values in table 9606: {bad.to_dict(orient='records')[:10]}")

    parsed["race_norm"] = parsed["race"].map(norm)
    expected_labels = {norm(x): x for x in RACE_NAMES}
    available = sorted(parsed["race_norm"].unique().tolist())
    missing_races = [name for nr, name in expected_labels.items() if nr not in available]
    if missing_races:
        raise RuntimeError(f"Expected race/color categories absent from table 9606 payload: {missing_races}; available={available}")

    result = parsed[["municipality_code", "municipality_name"]].drop_duplicates("municipality_code").copy()
    for nr, display in expected_labels.items():
        part = parsed.loc[parsed["race_norm"] == nr, ["municipality_code", "value"]].copy()
        if part["municipality_code"].duplicated().any():
            part = part.groupby("municipality_code", as_index=False)["value"].sum()
        result = result.merge(
            part.rename(columns={"value": f"female_race_{norm(display).replace(' ', '_')}_count"}),
            on="municipality_code", how="left", validate="one_to_one"
        )

    count_cols = [f"female_race_{norm(name).replace(' ', '_')}_count" for name in RACE_NAMES]
    if len(result) != EXPECTED_MUNICIPALITIES or result["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(f"Expected 144 Pará municipalities, got rows={len(result)}, unique={result['municipality_code'].nunique()}")
    if result[count_cols].isna().any().any():
        raise RuntimeError("Female race/color counts are incomplete after pivot")

    declared_total = result[count_cols].sum(axis=1)
    # Table 9606 named categories are the declared race/color composition.
    # Close on the declared total so the five shares form a proper composition;
    # any non-declared residual is not silently assigned to a category.
    if (declared_total <= 0).any():
        raise RuntimeError("Invalid zero female declared race/color total")
    result["diagnostic__female_declared_race_total"] = declared_total
    for name in RACE_NAMES:
        count_col = f"female_race_{norm(name).replace(' ', '_')}_count"
        result[RACE_COLUMNS[name]] = result[count_col] / declared_total

    share_cols = list(RACE_COLUMNS.values())
    result["diagnostic__female_race_declared_share_sum"] = result[share_cols].sum(axis=1)
    result["diagnostic__female_race_residual_share"] = 1.0 - result["diagnostic__female_race_declared_share_sum"]

    if result[share_cols].isna().any().any() or ((result[share_cols] < 0) | (result[share_cols] > 1)).any().any():
        raise RuntimeError("Female race/color shares failed bounds/completeness validation")
    if (result["diagnostic__female_race_declared_share_sum"] - 1.0).abs().max() > 1e-10:
        raise RuntimeError("Closed female race/color shares do not sum to one")

    result = result.sort_values("municipality_code").reset_index(drop=True)
    result.to_csv(out / "stage5_female_race_color_candidates.csv", index=False)

    audit = {
        "stage": "Stage 5 female race/color acquisition audit",
        "source": "IBGE Census 2022 universe results via SIDRA table 9606",
        "operational_route": "official SIDRA values API",
        "sidra_table": 9606,
        "period": 2022,
        "municipalities": int(result["municipality_code"].nunique()),
        "female_specific": True,
        "all_ages": True,
        "universe_results": True,
        "candidate_features": share_cols,
        "missing_share_cells": int(result[share_cols].isna().sum().sum()),
        "zero_counts": {col: int((result[col] == 0).sum()) for col in share_cols},
        "declared_share_sum_min": float(result["diagnostic__female_race_declared_share_sum"].min()),
        "declared_share_sum_max": float(result["diagnostic__female_race_declared_share_sum"].max()),
        "request_url": SIDRA_VALUES_URL,
        "closure": "Shares are normalized over the five declared IBGE race/color categories returned by table 9606; no category is imputed.",
        "replacement_decision": "Use female-specific table 9606 composition for Stage 5 SOM instead of total-population table 9605. Preserve 9605 only as an earlier audit artifact.",
        "interpretation_warning": "Race/color composition is a descriptive municipal profile block, not a violence-risk score or normative hierarchy.",
    }
    (out / "stage5_female_race_color_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
