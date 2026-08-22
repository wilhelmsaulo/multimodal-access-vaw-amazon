from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

RAW = Path("data/raw/transport/antaq_waterways")
OUT = Path("artifacts/antaq_hydro_temporal_observations_pa")
DATASETS = (
    "SHPTKUinterior2023.zip",
    "SHP_VEN2022completo.zip",
    "SHPTKU2023cabotagem.zip",
)
TIME_RE = re.compile(r"^\s*(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)min\s*)?$", re.I)


def _first_shp(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as z:
        shps = [n for n in z.namelist() if n.lower().endswith(".shp")]
    if not shps:
        raise RuntimeError(f"No shapefile found in {zip_path}")
    return shps[0]


def _find_col(cols: list[str], candidates: tuple[str, ...]) -> str | None:
    low = {c.lower(): c for c in cols}
    for candidate in candidates:
        if candidate.lower() in low:
            return low[candidate.lower()]
    return None


def _parse_minutes(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    m = TIME_RE.fullmatch(text)
    if not m:
        return None
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    total = days * 1440 + hours * 60 + minutes
    return float(total) if total > 0 else None


def _pa_mask(g: gpd.GeoDataFrame, est_o: str | None, est_d: str | None) -> pd.Series:
    mask = pd.Series(False, index=g.index)
    for col in (est_o, est_d):
        if col:
            mask |= g[col].astype("string").str.upper().str.strip().eq("PA").fillna(False)
    # Fallback only when state fields are absent: geometry intersects broad Pará extent.
    if not mask.any() and g.crs is not None:
        gg = g.to_crs("EPSG:4674")
        bounds = gg.geometry.bounds
        mask = (
            (bounds.maxx >= -58.95) & (bounds.minx <= -46.0) &
            (bounds.maxy >= -9.95) & (bounds.miny <= 2.8)
        )
    return mask


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[pd.DataFrame] = []
    source_audits: list[dict[str, object]] = []

    for name in DATASETS:
        zip_path = RAW / name
        if not zip_path.exists():
            raise FileNotFoundError(zip_path)
        layer = _first_shp(zip_path)
        g = gpd.read_file(f"zip://{zip_path}!{layer}")
        cols = [str(c) for c in g.columns if c != "geometry"]
        time_col = _find_col(cols, ("TEMPO", "tempo"))
        length_col = _find_col(cols, ("EXTENSAO", "extensao"))
        est_o = _find_col(cols, ("EST_ORIGEM", "est_origem"))
        est_d = _find_col(cols, ("EST_ESTINO", "est_estino"))
        mun_o = _find_col(cols, ("MUN_ORIGEM", "mun_origem"))
        mun_d = _find_col(cols, ("MUN_ESTINO", "mun_estino"))
        rio = _find_col(cols, ("NOME_RIO", "nome_rio"))
        tipo = _find_col(cols, ("TIPO", "tipo"))
        navegacao = _find_col(cols, ("NAVEGACAO", "navegacao"))
        hid = _find_col(cols, ("IDHIDROVIA", "idhidrovia", "IDANTAQ", "idantaq"))
        if not time_col or not length_col:
            raise RuntimeError(f"{name} lacks TEMPO/EXTENSAO")

        pa = g.loc[_pa_mask(g, est_o, est_d)].copy()
        time_min = pa[time_col].map(_parse_minutes)
        length_km = pd.to_numeric(pa[length_col], errors="coerce")
        valid = time_min.notna() & length_km.notna() & (length_km > 0)
        speed = np.where(valid, length_km / (time_min / 60.0), np.nan)

        frame = pd.DataFrame({
            "source_dataset": name,
            "source_layer": layer,
            "source_row": pa.index.astype(str),
            "hydro_id": pa[hid].astype(str).values if hid else pd.NA,
            "origin_municipality": pa[mun_o].astype("string").values if mun_o else pd.NA,
            "origin_state": pa[est_o].astype("string").values if est_o else pd.NA,
            "destination_municipality": pa[mun_d].astype("string").values if mun_d else pd.NA,
            "destination_state": pa[est_d].astype("string").values if est_d else pd.NA,
            "river_name": pa[rio].astype("string").values if rio else pd.NA,
            "navigation_type": pa[navegacao].astype("string").values if navegacao else pd.NA,
            "segment_type": pa[tipo].astype("string").values if tipo else pd.NA,
            "length_km_reported": length_km.values,
            "travel_time_raw": pa[time_col].astype("string").values,
            "travel_time_min_observed": time_min.values,
            "implicit_speed_kmh_observed": speed,
            "time_source": "antaq_observed_segment_time",
            "wait_time_included": False,
        })
        rows.append(frame)
        source_audits.append({
            "dataset": name,
            "rows_total": int(len(g)),
            "rows_pa_candidate": int(len(pa)),
            "rows_pa_with_parsed_time_and_length": int(valid.sum()),
            "time_coverage_pa_fraction": float(valid.mean()) if len(pa) else None,
            "time_column": time_col,
            "length_column": length_col,
        })

    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    parsed = out.loc[
        pd.to_numeric(out.get("travel_time_min_observed"), errors="coerce").notna() &
        pd.to_numeric(out.get("implicit_speed_kmh_observed"), errors="coerce").notna()
    ].copy()
    speeds = pd.to_numeric(parsed["implicit_speed_kmh_observed"], errors="coerce")
    times = pd.to_numeric(parsed["travel_time_min_observed"], errors="coerce")

    out.to_csv(OUT / "antaq_hydro_temporal_observations_pa.csv.gz", index=False, compression="gzip")
    audit = {
        "source_datasets": source_audits,
        "pa_observation_rows": int(len(out)),
        "pa_rows_with_observed_time_and_length": int(len(parsed)),
        "observed_time_coverage_fraction": float(len(parsed) / len(out)) if len(out) else None,
        "travel_time_minutes_summary": {
            "min": float(times.min()) if len(times) else None,
            "median": float(times.median()) if len(times) else None,
            "p25": float(times.quantile(0.25)) if len(times) else None,
            "p75": float(times.quantile(0.75)) if len(times) else None,
            "p95": float(times.quantile(0.95)) if len(times) else None,
            "max": float(times.max()) if len(times) else None,
        },
        "implicit_speed_kmh_summary_for_audit_only": {
            "min": float(speeds.min()) if len(speeds) else None,
            "median": float(speeds.median()) if len(speeds) else None,
            "p25": float(speeds.quantile(0.25)) if len(speeds) else None,
            "p75": float(speeds.quantile(0.75)) if len(speeds) else None,
            "p95": float(speeds.quantile(0.95)) if len(speeds) else None,
            "max": float(speeds.max()) if len(speeds) else None,
        },
        "scientific_policy": (
            "Observed ANTAQ segment travel time is the preferred hydro temporal evidence. Implicit speed is derived only for audit/calibration diagnostics. "
            "No waiting time is included, no single hydro speed is assigned statewide, and no missing hydro segment is imputed in this stage."
        ),
        "wait_time_model": "excluded_from_primary_model_and_reserved_for_discussion",
        "hydro_missing_time_imputation_applied": False,
        "ready_for_hydro_temporal_matching_audit": bool(len(parsed)),
    }
    (OUT / "antaq_hydro_temporal_observations_pa_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
