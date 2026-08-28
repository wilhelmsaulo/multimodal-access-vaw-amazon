from __future__ import annotations

"""Acquire and audit Census 2022 municipal race/color composition for Stage 5 SOM.

This module deliberately treats SIDRA table 9605 as a total-population municipal
composition source. It must not be labelled as female-specific. The output keeps
all five official race/color shares as candidate/diagnostic columns; the later
pre-SOM compositional audit decides the final parameterization.
"""

import json
import unicodedata
from pathlib import Path

import pandas as pd

from src.data.sidra import SidraConnector, SidraQuery

SIDRA_BASE = "https://apisidra.ibge.gov.br/values"
PARA_UF_CODE = "15"
EXPECTED_MUNICIPALITIES = 144
RACE_LABELS = {
    "branca": "socio__race_share_branca",
    "preta": "socio__race_share_preta",
    "parda": "socio__race_share_parda",
    "amarela": "socio__race_share_amarela",
    "indigena": "socio__race_share_indigena",
}


def norm_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def find_column(frame: pd.DataFrame, *needles: str, exclude: tuple[str, ...] = ()) -> str:
    normalized = {c: norm_text(c) for c in frame.columns}
    for c, nc in normalized.items():
        if all(norm_text(n) in nc for n in needles) and not any(norm_text(x) in nc for x in exclude):
            return c
    raise RuntimeError(
        f"Could not resolve SIDRA column containing {needles} excluding {exclude}; columns={list(frame.columns)}"
    )


def to_numeric_sidra(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.strip().replace({"-": "0", "...": pd.NA, "..": pd.NA, "X": pd.NA})
    cleaned = cleaned.str.replace(" ", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def main() -> None:
    out = Path("results/stage5/tables")
    out.mkdir(parents=True, exist_ok=True)

    connector = SidraConnector(SIDRA_BASE, timeout=90)
    query = SidraQuery(
        table=9605,
        territorial_level=6,
        territories="in%20n3%2015",
        variables="all",
        periods="2022",
    )
    frame, metadata = connector.fetch(query)
    if frame.empty:
        raise RuntimeError("SIDRA table 9605 returned no records for Pará municipalities")

    municipality_code = find_column(frame, "municipio", "codigo")
    municipality_name = find_column(frame, "municipio", exclude=("codigo",))
    race_col = find_column(frame, "cor", "raca", exclude=("codigo",))
    value_col = find_column(frame, "valor")

    work = frame[[municipality_code, municipality_name, race_col, value_col]].copy()
    work.columns = ["municipality_code", "municipality_name", "race_color", "value"]
    work["municipality_code"] = work["municipality_code"].astype(str).str.extract(r"(\d{7})", expand=False)
    work = work[work["municipality_code"].str.startswith(PARA_UF_CODE, na=False)].copy()
    work["race_norm"] = work["race_color"].map(norm_text)
    work["value"] = to_numeric_sidra(work["value"])

    municipality_count = work["municipality_code"].nunique()
    if municipality_count != EXPECTED_MUNICIPALITIES:
        raise RuntimeError(f"Expected 144 Pará municipalities, got {municipality_count}")

    total_rows = work[work["race_norm"].eq("total")][["municipality_code", "municipality_name", "value"]].copy()
    total_rows = total_rows.rename(columns={"value": "race_population_total"})
    if total_rows["municipality_code"].nunique() != EXPECTED_MUNICIPALITIES:
        raise RuntimeError("Table 9605 did not expose one Total row for every Pará municipality")

    result = total_rows.drop_duplicates("municipality_code").set_index("municipality_code")
    category_audit: dict[str, int] = {}

    for label, output_col in RACE_LABELS.items():
        rows = work[work["race_norm"].eq(label)][["municipality_code", "value"]].copy()
        category_audit[label] = int(rows["municipality_code"].nunique())
        if category_audit[label] != EXPECTED_MUNICIPALITIES:
            available = sorted(work["race_norm"].dropna().unique().tolist())
            raise RuntimeError(
                f"Race/color category {label!r} is not available for all 144 municipalities; available labels={available}"
            )
        values = rows.drop_duplicates("municipality_code").set_index("municipality_code")["value"]
        result[output_col] = values / result["race_population_total"].replace(0, pd.NA)

    result = result.reset_index()
    share_cols = list(RACE_LABELS.values())
    result["diagnostic__race_share_sum"] = result[share_cols].sum(axis=1, min_count=len(share_cols))
    result["diagnostic__race_share_residual"] = 1.0 - result["diagnostic__race_share_sum"]

    if result[share_cols].isna().any().any():
        raise RuntimeError("Race/color candidate shares contain missing values")
    if ((result[share_cols] < 0) | (result[share_cols] > 1)).any().any():
        raise RuntimeError("Race/color shares fall outside [0,1]")

    result.to_csv(out / "stage5_race_color_candidates.csv", index=False)
    frame.to_csv(out / "stage5_sidra_9605_raw_normalized.csv", index=False)

    audit = {
        "stage": "Stage 5 SOM race/color acquisition audit",
        "source": "IBGE Census 2022 universe results via SIDRA table 9605",
        "sidra_table": 9605,
        "period": 2022,
        "territorial_level": "municipality",
        "state": "Pará",
        "municipalities": municipality_count,
        "female_specific": False,
        "categories_complete_municipalities": category_audit,
        "share_columns": share_cols,
        "share_sum_min": float(result["diagnostic__race_share_sum"].min()),
        "share_sum_max": float(result["diagnostic__race_share_sum"].max()),
        "max_abs_residual": float(result["diagnostic__race_share_residual"].abs().max()),
        "missing_share_cells": int(result[share_cols].isna().sum().sum()),
        "compositional_warning": "Do not feed the complete raw share vector mechanically into SOM; final representation is decided at the pre-SOM redundancy/compositional gate.",
        "interpretation_warning": "Race/color composition is a descriptive profile block, not a violence-risk score and not a normative hierarchy.",
        "collection_metadata": metadata.__dict__,
    }
    (out / "stage5_race_color_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
