from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PARENT_CLASS_SPEEDS_KMH = {
    "secondary_link": 60.0,
    "tertiary_link": 60.0,
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--edges", type=Path, default=Path("artifacts/primary_motor_road_times/primary_motor_edges_with_times.csv.gz"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/primary_motor_road_times_complete"))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.edges, low_memory=False)
    for col in ["length_m", "speed_kmh", "travel_time_min"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "speed_source" not in df.columns:
        df["speed_source"] = None

    unresolved_before = int(df["travel_time_min"].isna().sum())
    imputed_counts: dict[str, int] = {}

    for highway, speed in PARENT_CLASS_SPEEDS_KMH.items():
        mask = df["travel_time_min"].isna() & (df["highway"].astype(str) == highway)
        imputed_counts[highway] = int(mask.sum())
        df.loc[mask, "speed_kmh"] = speed
        df.loc[mask, "travel_time_min"] = (df.loc[mask, "length_m"] / 1000.0) / speed * 60.0
        df.loc[mask, "speed_source"] = "parent_class_median_imputation"

    unresolved_after = int(df["travel_time_min"].isna().sum())
    total_length_km = float(df["length_m"].fillna(0).sum() / 1000.0)
    resolved_length_km = float(df.loc[df["travel_time_min"].notna(), "length_m"].fillna(0).sum() / 1000.0)

    out = args.output_dir / "primary_motor_edges_with_complete_times.csv.gz"
    df.to_csv(out, index=False, compression="gzip")

    audit = {
        "edges_total": int(len(df)),
        "unresolved_before": unresolved_before,
        "parent_class_imputation_counts": imputed_counts,
        "unresolved_after": unresolved_after,
        "edge_time_coverage_fraction": float(df["travel_time_min"].notna().mean()),
        "length_time_coverage_fraction": resolved_length_km / total_length_km if total_length_km else None,
        "parent_class_policy": {
            "secondary_link": "inherits median candidate of secondary (60 km/h)",
            "tertiary_link": "inherits median candidate of tertiary (60 km/h)",
        },
        "policy": (
            "Only previously unresolved link edges are completed by inheriting the empirically supported median of their parent highway class. "
            "This is recorded separately as parent_class_median_imputation. No global fallback is used. Travel times remain free-flow impedance proxies."
        ),
        "terrestrial_temporal_graph_complete": unresolved_after == 0,
        "hydro_temporal_model_resolved": False,
    }
    (args.output_dir / "primary_motor_road_time_completion_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
