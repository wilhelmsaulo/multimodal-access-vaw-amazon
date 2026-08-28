from __future__ import annotations

"""Acquire and audit Census 2022 municipal race/color composition for Stage 5 SOM.

The operational source is the official IBGE Census 2022 selected-table workbook
for municipalities. SIDRA table 9605 remains the conceptual/dissemination
reference. The source is total-population composition, not female-specific.
"""

import io
import json
import re
import unicodedata
from pathlib import Path

import httpx
import pandas as pd

IBGE_XLSX_URL = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Populacao_por_cor_ou_raca_Resultados_do_universo/Tabelas_selecionadas/xlsx/"
    "Tabela_04_Pop_resid_por_cor_ou_raca_e_pessoas_indigenas_2022_MU.xlsx"
)
EXPECTED_MUNICIPALITIES = 144
PARA_CODE_PREFIX = "15"
RACE_LABELS = {
    "branca": "socio__race_share_branca",
    "preta": "socio__race_share_preta",
    "parda": "socio__race_share_parda",
    "amarela": "socio__race_share_amarela",
    "indigena": "socio__race_share_indigena",
}


def norm_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def download_workbook() -> bytes:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(IBGE_XLSX_URL)
        response.raise_for_status()
    if len(response.content) < 100_000:
        raise RuntimeError(f"Unexpectedly small IBGE workbook: {len(response.content)} bytes")
    return response.content


def find_header_row(raw: pd.DataFrame) -> int:
    for idx in range(min(40, len(raw))):
        values = [norm_text(v) for v in raw.iloc[idx].tolist()]
        joined = " | ".join(values)
        if "branca" in joined and "preta" in joined and "parda" in joined and "indigena" in joined:
            return idx
    raise RuntimeError("Could not identify the race/color header row in the official IBGE workbook")


def flatten_headers(raw: pd.DataFrame, header_row: int) -> list[str]:
    # Some IBGE selected tables use two adjacent header rows. Combine the race
    # labels visible on the detected row with the preceding structural labels.
    previous = raw.iloc[max(0, header_row - 1)].tolist()
    current = raw.iloc[header_row].tolist()
    headers: list[str] = []
    for i, (a, b) in enumerate(zip(previous, current)):
        na, nb = norm_text(a), norm_text(b)
        label = " ".join(x for x in (na, nb) if x)
        headers.append(label or f"col_{i}")
    return headers


def find_col(columns: list[str], required: tuple[str, ...], excluded: tuple[str, ...] = ()) -> str:
    for col in columns:
        nc = norm_text(col)
        if all(token in nc for token in required) and not any(token in nc for token in excluded):
            return col
    raise RuntimeError(f"Could not resolve column required={required} excluded={excluded}; columns={columns}")


def numeric(series: pd.Series) -> pd.Series:
    out = series.astype(str).str.strip()
    out = out.replace({"-": "0", "...": pd.NA, "..": pd.NA, "X": pd.NA, "nan": pd.NA})
    out = out.str.replace(".", "", regex=False).str.replace(",", ".", regex=False).str.replace(" ", "", regex=False)
    return pd.to_numeric(out, errors="coerce")


def parse_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    header_row = find_header_row(raw)
    headers = flatten_headers(raw, header_row)
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = headers
    data = data.dropna(how="all")

    # Resolve location columns. Selected IBGE tables normally expose a code plus
    # a geographic-name column; keep a fallback for variants without explicit labels.
    columns = list(data.columns)
    code_candidates = [c for c in columns if "cod" in norm_text(c)]
    geo_candidates = [
        c for c in columns
        if any(token in norm_text(c) for token in ("municipio", "unidade da federacao", "brasil", "territorial"))
        and "cod" not in norm_text(c)
    ]
    if not code_candidates:
        # Detect a column dominated by seven-digit municipality codes.
        for c in columns[:4]:
            vals = data[c].astype(str).str.extract(r"(\d{7})", expand=False)
            if vals.notna().sum() >= EXPECTED_MUNICIPALITIES:
                code_candidates.append(c)
                break
    if not geo_candidates:
        # Geographic names are usually among the first three columns.
        geo_candidates = [c for c in columns[:4] if c not in code_candidates]
    if not code_candidates or not geo_candidates:
        raise RuntimeError(f"Could not resolve municipality code/name columns: {columns}")

    code_col = code_candidates[0]
    name_col = geo_candidates[0]
    data["municipality_code"] = data[code_col].astype(str).str.extract(r"(\d{7})", expand=False)
    data = data[data["municipality_code"].str.startswith(PARA_CODE_PREFIX, na=False)].copy()
    data["municipality_name"] = data[name_col].astype(str).str.strip()

    if data["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(
            f"Expected 144 Pará municipalities in official workbook; got {data['municipality_code'].nunique()}"
        )

    # Identify the total and race/color count columns from the combined headers.
    total_col = find_col(columns, ("total",), ("percent", "indigena"))
    race_cols: dict[str, str] = {}
    for race in RACE_LABELS:
        race_cols[race] = find_col(columns, (race,), ("percent", "pessoas indigenas"))

    result = data[["municipality_code", "municipality_name"]].copy()
    result["race_population_total"] = numeric(data[total_col])
    for race, output_col in RACE_LABELS.items():
        result[output_col] = numeric(data[race_cols[race]]) / result["race_population_total"].replace(0, pd.NA)

    return result.drop_duplicates("municipality_code")


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
        except Exception as exc:  # audited below; preserve diagnostics across sheets
            parse_errors[sheet] = str(exc)
            continue
        if candidate["municipality_code"].nunique() == EXPECTED_MUNICIPALITIES:
            result = candidate
            selected_sheet = sheet
            break

    if result is None or selected_sheet is None:
        raise RuntimeError(f"No workbook sheet produced the 144-municipality Pará matrix: {parse_errors}")

    share_cols = list(RACE_LABELS.values())
    result["diagnostic__race_share_sum"] = result[share_cols].sum(axis=1, min_count=len(share_cols))
    result["diagnostic__race_share_residual"] = 1.0 - result["diagnostic__race_share_sum"]

    if len(result) != EXPECTED_MUNICIPALITIES or result["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError("Race/color result failed 144-municipality key integrity")
    if result[share_cols].isna().any().any():
        missing = result.loc[result[share_cols].isna().any(axis=1), ["municipality_code", "municipality_name", *share_cols]]
        raise RuntimeError(f"Race/color candidate shares contain missing values: {missing.to_dict(orient='records')[:10]}")
    if ((result[share_cols] < 0) | (result[share_cols] > 1)).any().any():
        raise RuntimeError("Race/color shares fall outside [0,1]")

    result = result.sort_values("municipality_code").reset_index(drop=True)
    result.to_csv(out / "stage5_race_color_candidates.csv", index=False)

    audit = {
        "stage": "Stage 5 SOM race/color acquisition audit",
        "source": "IBGE Census 2022 universe results — official selected municipal table",
        "reference_sidra_table": 9605,
        "operational_file": IBGE_XLSX_URL,
        "period": 2022,
        "territorial_level": "municipality",
        "state": "Pará",
        "municipalities": int(result["municipality_code"].nunique()),
        "female_specific": False,
        "selected_workbook_sheet": selected_sheet,
        "share_columns": share_cols,
        "share_sum_min": float(result["diagnostic__race_share_sum"].min()),
        "share_sum_max": float(result["diagnostic__race_share_sum"].max()),
        "max_abs_residual": float(result["diagnostic__race_share_residual"].abs().max()),
        "missing_share_cells": int(result[share_cols].isna().sum().sum()),
        "source_file_bytes": len(content),
        "parse_errors_other_sheets": parse_errors,
        "compositional_warning": "Do not feed the complete raw share vector mechanically into SOM; final representation is decided at the pre-SOM redundancy/compositional gate.",
        "interpretation_warning": "Race/color composition is a descriptive profile block, not a violence-risk score and not a normative hierarchy.",
    }
    (out / "stage5_race_color_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
