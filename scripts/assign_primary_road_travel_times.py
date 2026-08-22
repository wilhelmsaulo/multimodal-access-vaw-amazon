from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

# Classes with enough empirical support for class-wise median imputation in the
# conservative primary motor graph. Explicit unambiguous maxspeed values always
# take precedence. Sparse link classes are intentionally left unresolved unless
# they carry an explicit observed maxspeed.
IMPUTABLE_CLASS_MEDIANS_KMH = {
    "trunk": 80.0,
    "primary": 80.0,
    "secondary": 60.0,
    "tertiary": 60.0,
    "unclassified": 60.0,
    "residential": 40.0,
    "service": 40.0,
    "living_street": 40.0,
    "trunk_link": 60.0,
    "primary_link": 60.0,
}


def parse_numeric_maxspeed(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        kmh = float(text)
    elif re.fullmatch(r"\d+(?:\.\d+)?\s*(?:km/?h|kph|kmh)", text):
        kmh = float(re.search(r"\d+(?:\.\d+)?", text).group())
    elif re.fullmatch(r"\d+(?:\.\d+)?\s*mph", text):
        mph = float(re.search(r"\d+(?:\.\d+)?", text).group())
        kmh = mph * 1.609344
    else:
        return None
    return kmh if 0 < kmh <= 160 else None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--edges", type=Path, default=Path("artifacts/primary_motor_road_graph/primary_motor_edges.csv.gz"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/primary_motor_road_times"))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.edges, low_memory=False)
    df["length_m"] = pd.to_numeric(df["length_m"], errors="coerce")
    df["highway_norm"] = df["highway"].astype("string").str.strip().str.lower()
    df["observed_maxspeed_kmh"] = df["maxspeed_raw"].map(parse_numeric_maxspeed)

    df["speed_kmh"] = df["observed_maxspeed_kmh"]
    df["speed_source"] = np.where(df["observed_maxspeed_kmh"].notna(), "observed_osm_maxspeed", "unresolved")

    missing = df["speed_kmh"].isna()
    imputable = missing & df["highway_norm"].isin(IMPUTABLE_CLASS_MEDIANS_KMH)
    df.loc[imputable, "speed_kmh"] = df.loc[imputable, "highway_norm"].map(IMPUTABLE_CLASS_MEDIANS_KMH)
    df.loc[imputable, "speed_source"] = "class_median_from_observed_osm_maxspeed"

    valid = df["speed_kmh"].notna() & df["length_m"].notna() & (df["length_m"] >= 0)
    df["travel_time_min"] = np.nan
    df.loc[valid, "travel_time_min"] = (df.loc[valid, "length_m"] / 1000.0) / df.loc[valid, "speed_kmh"] * 60.0

    out_cols = [c for c in df.columns if c != "highway_norm"]
    df[out_cols].to_csv(args.output_dir / "primary_motor_edges_with_times.csv.gz", index=False, compression="gzip")

    by_source = df["speed_source"].value_counts(dropna=False).to_dict()
    unresolved = df.loc[df["travel_time_min"].isna(), "highway_norm"].fillna("<missing>").value_counts().to_dict()
    total_len = float(df["length_m"].fillna(0).sum())
    resolved_len = float(df.loc[df["travel_time_min"].notna(), "length_m"].fillna(0).sum())

    audit = {
        "edges_total": int(len(df)),
        "edges_with_travel_time": int(df["travel_time_min"].notna().sum()),
        "edge_time_coverage_fraction": float(df["travel_time_min"].notna().mean()),
        "length_total_km": total_len / 1000.0,
        "length_with_travel_time_km": resolved_len / 1000.0,
        "length_time_coverage_fraction": float(resolved_len / total_len) if total_len else 0.0,
        "speed_source_counts": {str(k): int(v) for k, v in by_source.items()},
        "unresolved_highway_counts": {str(k): int(v) for k, v in unresolved.items()},
        "imputable_class_medians_kmh": IMPUTABLE_CLASS_MEDIANS_KMH,
        "policy": (
            "Travel time is assigned only on the conservative primary motor graph. Explicit unambiguous OSM maxspeed values take precedence. "
            "For missing speeds, class medians are used only for primary motor classes with empirically supported class-wise candidates from the prior audit. "
            "Sparse classes such as secondary_link and tertiary_link remain unresolved unless an explicit maxspeed exists. These weights are free-flow impedance proxies, not realized observed travel times."
        ),
        "ready_for_terrestrial_routing_prototype": bool(df["travel_time_min"].notna().mean() >= 0.99),
        "hydro_temporal_model_resolved": False,
    }
    (args.output_dir / "primary_motor_road_time_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
