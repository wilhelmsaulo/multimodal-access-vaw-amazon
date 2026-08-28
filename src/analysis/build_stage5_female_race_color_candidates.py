from __future__ import annotations

"""Acquire female municipal race/color composition for Stage 5 SOM.

Official source: IBGE Census 2022 universe results, SIDRA table 9606
(População residente, por cor ou raça, segundo o sexo e a idade).

Operational acquisition uses the official SIDRA XLSX export endpoint. This
avoids the intermittently unreachable aggregates-metadata service while keeping
exactly the same IBGE table and classifications.
"""

import io
import json
import time
import unicodedata
from pathlib import Path

import httpx
import pandas as pd

EXPECTED_MUNICIPALITIES = 144
PARA_CODE_PREFIX = "15"
RACE_NAMES = ["Branca", "Preta", "Parda", "Amarela", "Indígena"]
RACE_COLUMNS = {
    "Branca": "socio__female_race_share_branca",
    "Preta": "socio__female_race_share_preta",
    "Parda": "socio__female_race_share_parda",
    "Amarela": "socio__female_race_share_amarela",
    "Indígena": "socio__female_race_share_indigena",
}

# Table-9606 classifications from SIDRA itself:
# c2/6794 = Mulheres; c287/100362 = Total (idade); c86/all = all race/color categories.
# The final layout fragment mirrors SIDRA's own downloadable-table URL.
SIDRA_XLSX_URL = (
    "https://sidra.ibge.gov.br/geratabela?format=xlsx&name=stage5_female_race.xlsx&terr=N&rank=-&query="
    "t/9606/n3/15/n6/all/v/all/p/2022/c86/all/c2/6794/c287/100362/"
    "d/v1000093%202/l/,p%2Bv%2Bc2,t%2Bc86%2Bc287/resultado"
)


def norm(value: object) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def download_workbook(attempts: int = 4) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 Stage5-reproducible-research/1.0"}
    timeout = httpx.Timeout(120.0, connect=45.0)
    last_error: Exception | None = None
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = client.get(SIDRA_XLSX_URL)
                response.raise_for_status()
                content = response.content
                if len(content) < 10_000 or not content.startswith(b"PK"):
                    raise RuntimeError(
                        f"Unexpected SIDRA XLSX response: bytes={len(content)}, prefix={content[:20]!r}"
                    )
                return content
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, RuntimeError) as exc:
                last_error = exc
                if attempt == attempts:
                    break
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError("Official SIDRA XLSX export failed after retries") from last_error


def find_header_row(raw: pd.DataFrame) -> int:
    for idx in range(min(40, len(raw))):
        joined = " | ".join(norm(v) for v in raw.iloc[idx].tolist())
        if "branca" in joined and "preta" in joined and "parda" in joined and "indigena" in joined:
            return idx
    raise RuntimeError("Could not identify race/color header row in SIDRA XLSX export")


def flatten_headers(raw: pd.DataFrame, header_row: int) -> list[str]:
    start = max(0, header_row - 3)
    context = raw.iloc[start : header_row + 1].copy().ffill(axis=1)
    headers: list[str] = []
    seen: dict[str, int] = {}
    for j in range(raw.shape[1]):
        parts: list[str] = []
        for i in range(context.shape[0]):
            value = norm(context.iloc[i, j])
            if value and value not in parts:
                parts.append(value)
        label = " ".join(parts) or f"col_{j}"
        count = seen.get(label, 0)
        seen[label] = count + 1
        headers.append(label if count == 0 else f"{label}__{count + 1}")
    return headers


def numeric(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().replace({"-": "0", "...": pd.NA, "..": pd.NA, "X": pd.NA, "nan": pd.NA})
    direct = pd.to_numeric(s.str.replace(",", ".", regex=False), errors="coerce")
    formatted = pd.to_numeric(
        s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False).str.replace(" ", "", regex=False),
        errors="coerce",
    )
    return direct.fillna(formatted)


def find_race_col(columns: list[str], race: str) -> str:
    nr = norm(race)
    candidates = [c for c in columns if nr in norm(c) and "percentual" not in norm(c)]
    if not candidates:
        raise RuntimeError(f"Could not resolve race column for {race}; columns={columns}")
    # Prefer headers explicitly referring to population/people.
    preferred = [c for c in candidates if any(t in norm(c) for t in ("populacao", "pessoas", "pessoa"))]
    return (preferred or candidates)[-1]


def parse_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    header_row = find_header_row(raw)
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = flatten_headers(raw, header_row)
    data = data.dropna(how="all")
    columns = list(data.columns)

    code_col: str | None = None
    for col in columns[:8]:
        extracted = data[col].astype(str).str.extract(r"(\d{7})", expand=False)
        if extracted.notna().sum() >= EXPECTED_MUNICIPALITIES:
            code_col = col
            break
    if code_col is None:
        code_col = next((c for c in columns if "cod" in norm(c)), None)
    if code_col is None:
        raise RuntimeError(f"Could not identify municipality-code column: {columns}")

    name_col: str | None = None
    for col in columns[:10]:
        if col == code_col:
            continue
        sample = data[col].astype(str)
        if sample.str.contains("Abaetetuba|Belém|Belem|Santarém|Santarem", case=False, regex=True).any():
            name_col = col
            break
    if name_col is None:
        name_col = next((c for c in columns if c != code_col and "municip" in norm(c)), None)
    if name_col is None:
        raise RuntimeError(f"Could not identify municipality-name column: {columns}")

    data["municipality_code"] = data[code_col].astype(str).str.extract(r"(\d{7})", expand=False)
    data = data[data["municipality_code"].str.startswith(PARA_CODE_PREFIX, na=False)].copy()
    data["municipality_name"] = data[name_col].astype(str).str.strip()
    data = data.drop_duplicates("municipality_code")
    if data["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(f"Expected 144 Pará municipalities in SIDRA XLSX export; got {data['municipality_code'].nunique()}")

    race_cols = {name: find_race_col(columns, name) for name in RACE_NAMES}
    total_candidates = [
        c for c in columns
        if "total" in norm(c)
        and c not in race_cols.values()
        and "percentual" not in norm(c)
        and any(t in norm(c) for t in ("populacao", "pessoas", "pessoa"))
    ]
    if not total_candidates:
        total_candidates = [c for c in columns if "total" in norm(c) and c not in race_cols.values() and "percentual" not in norm(c)]
    if not total_candidates:
        raise RuntimeError(f"Could not identify female-total column: {columns}")
    total_col = total_candidates[-1]

    total = numeric(data[total_col])
    result = data[["municipality_code", "municipality_name"]].copy()
    if total.isna().any():
        raise RuntimeError("Female total contains unavailable values in table 9606 export")
    result["diagnostic__female_population_9606"] = total.to_numpy()
    for name, col in race_cols.items():
        values = numeric(data[col])
        if values.isna().any():
            raise RuntimeError(f"Female race/color count contains unavailable values for {name}")
        result[f"female_race_{norm(name).replace(' ', '_')}_count"] = values.to_numpy()
        result[RACE_COLUMNS[name]] = values.to_numpy() / total.to_numpy()

    share_cols = list(RACE_COLUMNS.values())
    result["diagnostic__female_race_declared_share_sum"] = result[share_cols].sum(axis=1)
    result["diagnostic__female_race_residual_share"] = 1.0 - result["diagnostic__female_race_declared_share_sum"]
    return result


def main() -> None:
    out = Path("results/stage5/tables")
    out.mkdir(parents=True, exist_ok=True)

    content = download_workbook()
    xls = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
    parse_errors: dict[str, str] = {}
    result: pd.DataFrame | None = None
    selected_sheet: str | None = None
    for sheet in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=sheet, header=None, engine="openpyxl")
        try:
            candidate = parse_sheet(raw)
        except Exception as exc:
            parse_errors[sheet] = str(exc)
            continue
        if candidate["municipality_code"].nunique() == EXPECTED_MUNICIPALITIES:
            result = candidate
            selected_sheet = sheet
            break
    if result is None or selected_sheet is None:
        raise RuntimeError(f"No SIDRA workbook sheet produced the female 144-municipality matrix: {parse_errors}")

    result = result.sort_values("municipality_code").reset_index(drop=True)
    share_cols = list(RACE_COLUMNS.values())
    if result[share_cols].isna().any().any():
        raise RuntimeError("Female race/color shares contain missing values")
    if ((result[share_cols] < 0) | (result[share_cols] > 1)).any().any():
        raise RuntimeError("Female race/color shares fall outside [0,1]")
    if (result["diagnostic__female_race_residual_share"] < -1e-10).any():
        raise RuntimeError("Female declared race/color categories exceed female total")

    result.to_csv(out / "stage5_female_race_color_candidates.csv", index=False)
    audit = {
        "stage": "Stage 5 female race/color acquisition audit",
        "source": "IBGE Census 2022 universe results via SIDRA table 9606",
        "operational_route": "official SIDRA geratabela XLSX export",
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
        "declared_share_sum_median": float(result["diagnostic__female_race_declared_share_sum"].median()),
        "declared_share_sum_max": float(result["diagnostic__female_race_declared_share_sum"].max()),
        "residual_share_max": float(result["diagnostic__female_race_residual_share"].max()),
        "source_file_bytes": len(content),
        "selected_workbook_sheet": selected_sheet,
        "request_url": SIDRA_XLSX_URL,
        "parse_errors_other_sheets": parse_errors,
        "replacement_decision": "Use female-specific table 9606 composition for Stage 5 SOM instead of total-population table 9605. Preserve 9605 only as an earlier audit artifact.",
        "interpretation_warning": "Race/color composition is a descriptive municipal profile block, not a violence-risk score or normative hierarchy.",
    }
    (out / "stage5_female_race_color_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
