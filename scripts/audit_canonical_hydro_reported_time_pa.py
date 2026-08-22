from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

WATERWAYS = Path("artifacts/multimodal_graph_inputs/waterways.gpkg")
OUT = Path("artifacts/canonical_hydro_reported_time_pa")
TIME_RE = re.compile(r"^\s*(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)min\s*)?$", re.I)


def parse_minutes(value: object) -> float | None:
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    w = gpd.read_file(WATERWAYS, layer="waterways").reset_index(drop=True)
    if "reported_time" not in w.columns:
        raise RuntimeError("Canonical waterways layer lacks reported_time")

    parsed = w["reported_time"].map(parse_minutes)
    length = pd.to_numeric(w.get("reported_length_km"), errors="coerce")
    valid_time = parsed.notna()
    valid_both = valid_time & length.notna() & (length > 0)
    implicit_speed = pd.Series(pd.NA, index=w.index, dtype="Float64")
    implicit_speed.loc[valid_both] = length.loc[valid_both] / (parsed.loc[valid_both] / 60.0)

    out = pd.DataFrame({
        "waterway_index": w.index.astype(int),
        "hydro_id": w.get("hydro_id"),
        "river_name": w.get("river_name"),
        "origin_municipality": w.get("origin_municipality"),
        "destination_municipality": w.get("destination_municipality"),
        "reported_time_raw": w["reported_time"],
        "travel_time_min_observed_direct": parsed,
        "reported_length_km": length,
        "implicit_speed_kmh_observed_direct": implicit_speed,
        "time_source": "antaq_canonical_reported_time",
        "wait_time_included": False,
    })
    out.to_csv(OUT / "canonical_hydro_reported_time_audit.csv.gz", index=False, compression="gzip")

    t = parsed.dropna()
    s = pd.to_numeric(implicit_speed, errors="coerce").dropna()
    audit = {
        "canonical_waterway_segments": int(len(w)),
        "segments_with_reported_time_raw": int(w["reported_time"].notna().sum()),
        "segments_with_parsed_direct_observed_time": int(valid_time.sum()),
        "direct_observed_time_coverage_fraction": float(valid_time.mean()) if len(w) else None,
        "segments_with_time_and_length": int(valid_both.sum()),
        "travel_time_minutes_summary": {
            "min": float(t.min()) if len(t) else None,
            "median": float(t.median()) if len(t) else None,
            "p25": float(t.quantile(0.25)) if len(t) else None,
            "p75": float(t.quantile(0.75)) if len(t) else None,
            "p95": float(t.quantile(0.95)) if len(t) else None,
            "max": float(t.max()) if len(t) else None,
        },
        "implicit_speed_kmh_summary_for_audit_only": {
            "min": float(s.min()) if len(s) else None,
            "median": float(s.median()) if len(s) else None,
            "p25": float(s.quantile(0.25)) if len(s) else None,
            "p75": float(s.quantile(0.75)) if len(s) else None,
            "p95": float(s.quantile(0.95)) if len(s) else None,
            "max": float(s.max()) if len(s) else None,
        },
        "policy": (
            "Direct reported_time from the canonical ANTAQ waterway feature is treated as observed evidence. "
            "No waiting time, statewide speed, fuzzy transfer, or missing-time imputation is applied."
        ),
        "time_imputation_applied": False,
        "ready_for_hydro_temporal_graph_decision": True,
    }
    (OUT / "canonical_hydro_reported_time_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
