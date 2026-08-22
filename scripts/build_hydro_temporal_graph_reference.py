from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

WATERWAYS = Path("artifacts/multimodal_graph_inputs/waterways.gpkg")
OUT = Path("artifacts/hydro_temporal_graph_reference")
TIME_RE = re.compile(r"^\s*(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)min\s*)?$", re.I)


def parse_minutes(v: object) -> float | None:
    if v is None or pd.isna(v):
        return None
    m = TIME_RE.fullmatch(str(v).strip())
    if not m:
        return None
    total = int(m.group(1) or 0) * 1440 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
    return float(total) if total > 0 else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    w = gpd.read_file(WATERWAYS, layer="waterways").reset_index(drop=True)
    if "reported_time" not in w.columns:
        raise RuntimeError("Canonical waterways lack reported_time")
    w["travel_time_min"] = w["reported_time"].map(parse_minutes)
    if w["travel_time_min"].isna().any():
        raise RuntimeError("All canonical waterway segments must have parseable reported_time")
    w["time_source"] = "antaq_official_network_reference_time"
    w["passenger_realized_time"] = False
    w["waiting_time_included"] = False
    w["time_role"] = "hydro_network_reference_impedance"
    out_path = OUT / "waterways_with_reference_time.gpkg"
    w.to_file(out_path, layer="waterways_reference_time", driver="GPKG")
    audit = {
        "segments_total": int(len(w)),
        "segments_with_reference_time": int(w["travel_time_min"].notna().sum()),
        "coverage_fraction": float(w["travel_time_min"].notna().mean()),
        "time_source": "antaq_official_network_reference_time",
        "time_role": "hydro_network_reference_impedance",
        "passenger_realized_time_claimed": False,
        "waiting_time_included": False,
        "time_imputation_applied": False,
        "ready_for_multimodal_temporal_integration": bool(len(w) and w["travel_time_min"].notna().all()),
        "policy": "ANTLR reported_time is used as an official hydro-network reference impedance. It is not labeled as realized passenger travel time. Waiting time is excluded and no missing-time imputation is applied."
    }
    (OUT / "hydro_temporal_graph_reference_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
