from __future__ import annotations

import json
import zipfile
from pathlib import Path

import geopandas as gpd

ZIP = Path("data/raw/transport/antaq_ports/Linhasdetravessias06052025.zip")
OUT = Path("artifacts/antaq_crossing_lines_pa")
TOKENS = (
    "tempo", "dur", "hora", "freq", "interval", "viagem", "oper", "funcion",
    "orig", "dest", "municip", "cidade", "estado", "uf", "linha", "rota", "embarc", "frota",
)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not ZIP.exists():
        raise FileNotFoundError(ZIP)

    with zipfile.ZipFile(ZIP) as z:
        shp = [n for n in z.namelist() if n.lower().endswith(".shp")]
        if not shp:
            raise RuntimeError("No shapefile found in ANTAQ crossing-lines ZIP")
        layer = shp[0]

    g = gpd.read_file(f"zip://{ZIP}!{layer}")
    cols = [str(c) for c in g.columns if c != "geometry"]
    candidate_cols = [c for c in cols if any(t in c.lower() for t in TOKENS)]

    evidence = {}
    for c in candidate_cols:
        s = g[c]
        vals = s.dropna().astype(str)
        evidence[c] = {
            "nonnull": int(s.notna().sum()),
            "coverage_fraction": float(s.notna().mean()) if len(g) else 0.0,
            "unique_values": int(vals.nunique()),
            "sample_values": vals.drop_duplicates().head(20).tolist(),
        }

    # Pará detection uses any textual field containing PA or Pará. This is deliberately
    # permissive for audit only; it is not yet a routing rule.
    pa_mask = None
    pa_hits_by_column = {}
    for c in cols:
        s = g[c].astype("string")
        hit = s.str.contains(r"(^|\W)(PA|Par[aá])($|\W)", case=False, na=False, regex=True)
        if hit.any():
            pa_hits_by_column[c] = int(hit.sum())
            pa_mask = hit if pa_mask is None else (pa_mask | hit)
    if pa_mask is None:
        pa_mask = g.index.to_series().map(lambda _: False)

    pa = g.loc[pa_mask].copy()
    pa.drop(columns="geometry", errors="ignore").to_csv(OUT / "crossing_lines_pa_candidate_rows.csv", index=False)

    audit = {
        "source": str(ZIP),
        "layer": layer,
        "rows_total": int(len(g)),
        "columns": cols,
        "operational_candidate_columns": evidence,
        "pa_candidate_rows": int(len(pa)),
        "pa_detection_columns": pa_hits_by_column,
        "has_time_or_duration_field": any(any(t in c.lower() for t in ("tempo", "dur")) for c in cols),
        "has_frequency_or_interval_field": any(any(t in c.lower() for t in ("freq", "interval")) for c in cols),
        "has_schedule_or_hour_field": any("hora" in c.lower() for c in cols),
        "scientific_policy": (
            "This audit inventories ANTAQ crossing-line attributes and candidate Pará records. "
            "It does not convert frequency to waiting time, does not infer missing schedules, and does not promote a crossing line into the multimodal graph."
        ),
        "ready_for_wait_time_model_decision": True,
        "wait_time_assigned": False,
    }
    (OUT / "crossing_lines_pa_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
