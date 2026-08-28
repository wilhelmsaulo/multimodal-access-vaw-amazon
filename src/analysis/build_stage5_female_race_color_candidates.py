from __future__ import annotations

"""Acquire female municipal race/color composition for Stage 5 SOM.

Official source: IBGE Census 2022 universe results, SIDRA table 9606
(População residente, por cor ou raça, segundo o sexo e a idade).

Operational acquisition uses SIDRA's official ``geratabela`` CSV export rather
than the aggregates-metadata endpoint, which can be intermittently unreachable
from hosted runners. The statistical source and table remain exactly the same.
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

# Classification codes are those exposed by table 9606 itself:
# c2=6794 -> Mulheres; c287=100362 -> Total de idade; c86=all -> all race/color categories.
SIDRA_CSV_URL = (
    "https://sidra.ibge.gov.br/geratabela?format=csv&name=stage5_female_race.csv&terr=N&rank=-&query="
    "t/9606/n3/15/n6/all/v/all/p/2022/c86/all/c2/6794/c287/100362/"
    "l/v,p%2Bc86,c2,t%2Bc287"
)


def norm(value: object) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def download_csv(attempts: int = 4) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 Stage5-reproducible-research/1.0"}
    timeout = httpx.Timeout(120.0, connect=45.0)
    last_error: Exception | None = None
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = client.get(SIDRA_CSV_URL)
                response.raise_for_status()
                content = response.content
                if len(content) < 1_000:
                    raise RuntimeError(f"Unexpectedly small SIDRA CSV export: {len(content)} bytes")
                return content
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, RuntimeError) as exc:
                last_error = exc
                if attempt == attempts:
                    break
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError("Official SIDRA CSV export failed after retries") from last_error


def decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content.decode(encoding)
            if "Branca" in text and "Parda" in text:
                return text
        except UnicodeDecodeError:
            continue
    raise RuntimeError("Could not decode SIDRA CSV export with expected race/color labels")


def read_raw(text: str) -> pd.DataFrame:
    candidates: list[pd.DataFrame] = []
    for sep in (";", ",", "\t"):
        try:
            frame = pd.read_csv(io.StringIO(text), sep=sep, header=None, dtype=str, engine="python", on_bad_lines="skip")
        except Exception:
            continue
        candidates.append(frame)
    if not candidates:
        raise RuntimeError("Could not parse SIDRA CSV export")
    return max(candidates, key=lambda f: f.shape[1])


def find_header_row(raw: pd.DataFrame) -> int:
    for idx in range(min(30, len(raw))):
        joined = " | ".join(norm(v) for v in raw.iloc[idx].tolist())
        if "branca" in joined and "preta" in joined and "parda" in joined and "indigena" in joined:
            return idx
    raise RuntimeError("Could not identify race/color header row in SIDRA CSV export")


def flatten_headers(raw: pd.DataFrame, header_row: int) -> list[str]:
    start = max(0, header_row - 2)
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


def find_col(columns: list[str], token: str, excluded: tuple[str, ...] = ()) -> str:
    nt = norm(token)
    for col in columns:
        nc = norm(col)
        if nt in nc and not any(norm(x) in nc for x in excluded):
            return col
    raise RuntimeError(f"Could not resolve column for {token}; columns={columns}")


def parse_export(raw: pd.DataFrame) -> pd.DataFrame:
    header_row = find_header_row(raw)
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = flatten_headers(raw, header_row)
    data = data.dropna(how="all")
    columns = list(data.columns)

    code_col: str | None = None
    name_col: str | None = None
    for col in columns[:6]:
        extracted = data[col].astype(str).str.extract(r"(\d{7})", expand=False)
        if extracted.notna().sum() >= EXPECTED_MUNICIPALITIES:
            code_col = col
            break
    if code_col is None:
        for col in columns:
            if "cod" in norm(col):
                code_col = col
                break
    if code_col is None:
        raise RuntimeError(f"Could not identify municipality-code column: {columns}")

    for col in columns[:8]:
        if col == code_col:
            continue
        sample = data[col].astype(str)
        if sample.str.contains(" - PA|Abaetetuba|Belém|Belem", case=False, regex=True).any():
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
        raise RuntimeError(f"Expected 144 Pará municipalities in SIDRA export; got {data['municipality_code'].nunique()}")

    race_cols = {name: find_col(columns, name, ("percentual",)) for name in RACE_NAMES}
    # Prefer a Total column that is not merely a textual geography/age heading.
    total_candidates = [
        c for c in columns
        if "total" in norm(c)
        and c not in race_cols.values()
        and not any(x in norm(c) for x in ("percentual", "idade"))
    ]
    if not total_candidates:
        raise RuntimeError(f"Could not identify female total column: {columns}")
    total_col = total_candidates[-1]

    result = data[["municipality_code", "municipality_name"]].copy()
    total = numeric(data[total_col])
    counts: dict[str, pd.Series] = {name: numeric(data[col]) for name, col in race_cols.items()}
    if total.isna().any():
        raise RuntimeError("Female total contains unavailable values in table 9606 export")
    for name, values in counts.items():
        if values.isna().any():
            raise RuntimeError(f"Female race/color count contains unavailable values for {name}")
        result[f"female_race_{norm(name).replace(' ', '_')}_count"] = values.to_numpy()
        result[RACE_COLUMNS[name]] = values.to_numpy() / total.to_numpy()
    result["diagnostic__female_population_9606"] = total.to_numpy()
    share_cols = list(RACE_COLUMNS.values())
    result["diagnostic__female_race_declared_share_sum"] = result[share_cols].sum(axis=1)
    result["diagnostic__female_race_residual_share"] = 1.0 - result["diagnostic__female_race_declared_share_sum"]
    return result


def main() -> None:
    out = Path("results/stage5/tables")
    out.mkdir(parents=True, exist_ok=True)

    content = download_csv()
    text = decode_csv(content)
    raw = read_raw(text)
    result = parse_export(raw).sort_values("municipality_code").reset_index(drop=True)
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
        "operational_route": "official SIDRA geratabela CSV export",
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
        "request_url": SIDRA_CSV_URL,
        "replacement_decision": "Use female-specific table 9606 composition for Stage 5 SOM instead of total-population table 9605. Preserve 9605 only as an earlier audit artifact.",
        "interpretation_warning": "Race/color composition is a descriptive municipal profile block, not a violence-risk score or normative hierarchy.",
    }
    (out / "stage5_female_race_color_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
