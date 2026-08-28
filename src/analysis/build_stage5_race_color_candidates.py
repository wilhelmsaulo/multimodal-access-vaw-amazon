from __future__ import annotations

"""Acquire and audit Census 2022 municipal race/color composition for Stage 5 SOM.

The operational source is the official IBGE Census 2022 selected-table workbook
for municipalities. SIDRA table 9605 remains the conceptual/dissemination
reference. The source is total-population composition, not female-specific.
"""

import io
import json
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
    # IBGE uses merged cells for the 'Absoluto' and 'Percentual' column groups.
    # Forward-fill the group row so that every race column has a unique label.
    previous = pd.Series(raw.iloc[max(0, header_row - 1)].tolist()).ffill().tolist()
    current = raw.iloc[header_row].tolist()
    headers: list[str] = []
    seen: dict[str, int] = {}
    for i, (a, b) in enumerate(zip(previous, current)):
        na, nb = norm_text(a), norm_text(b)
        label = " ".join(x for x in (na, nb) if x) or f"col_{i}"
        count = seen.get(label, 0)
        seen[label] = count + 1
        headers.append(label if count == 0 else f"{label}__{count + 1}")
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
    # Excel usually supplies numeric cells directly; this path also handles
    # formatted Brazilian strings if they occur.
    direct = pd.to_numeric(out, errors="coerce")
    formatted = pd.to_numeric(
        out.str.replace(".", "", regex=False).str.replace(",", ".", regex=False).str.replace(" ", "", regex=False),
        errors="coerce",
    )
    return direct.fillna(formatted)


def parse_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    header_row = find_header_row(raw)
    headers = flatten_headers(raw, header_row)
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = headers
    data = data.dropna(how="all")

    columns = list(data.columns)
    code_candidates = [c for c in columns if "cod" in norm_text(c)]
    geo_candidates = [
        c for c in columns
        if any(token in norm_text(c) for token in ("municipio", "unidade da federacao", "brasil", "territorial"))
        and "cod" not in norm_text(c)
    ]
    if not code_candidates:
        for c in columns[:4]:
            vals = data[c].astype(str).str.extract(r"(\d{7})", expand=False)
            if vals.notna().sum() >= EXPECTED_MUNICIPALITIES:
                code_candidates.append(c)
                break
    if not geo_candidates:
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

    race_cols: dict[str, str] = {}
    for race in RACE_LABELS:
        race_cols[race] = find_col(columns, ("absoluto", race), ("percentual",))
    ignored_col = find_col(columns, ("absoluto", "ignorados"), ("percentual",))

    result = data[["municipality_code", "municipality_name"]].copy()
    absolute_counts: dict[str, pd.Series] = {race: numeric(data[col]) for race, col in race_cols.items()}
    ignored = numeric(data[ignored_col]).fillna(0)
    denominator = ignored.copy()
    for counts in absolute_counts.values():
        denominator = denominator.add(counts, fill_value=pd.NA)
    result["race_population_total"] = denominator
    result["diagnostic__race_ignored_count"] = ignored
    result["diagnostic__race_ignored_share"] = ignored / denominator.replace(0, pd.NA)
    for race, output_col in RACE_LABELS.items():
        result[output_col] = absolute_counts[race] / denominator.replace(0, pd.NA)

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
        except Exception as exc:
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

    # Because the five declared race/color shares exclude 'Ignorados', their
    # residual must equal the explicitly retained ignored-response share.
    residual_gap = (result["diagnostic__race_share_residual"] - result["diagnostic__race_ignored_share"]).abs()
    if residual_gap.max() > 1e-10:
        raise RuntimeError(f"Race/color residual does not reconcile to ignored share; max gap={residual_gap.max()}")

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
        "ignored_share_min": float(result["diagnostic__race_ignored_share"].min()),
        "ignored_share_max": float(result["diagnostic__race_ignored_share"].max()),
        "max_abs_residual_reconciliation_gap": float(residual_gap.max()),
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
