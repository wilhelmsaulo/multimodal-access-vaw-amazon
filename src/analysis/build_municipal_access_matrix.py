from __future__ import annotations

"""Build a municipal accessibility matrix from frozen Stage 2 artifacts.

The builder joins frozen routing-ready origins (which contain municipality and
female-population metadata) to the frozen reference-network OD matrix. It first
computes origin-level accessibility summaries, then aggregates them to the
municipality level using female-population weights whenever those weights are
positive and available. No unreachable OD time is imputed.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return float(values.mean()) if values.notna().any() else float("nan")
    return float(np.average(values.loc[mask].astype(float), weights=weights.loc[mask].astype(float)))


def build(od_path: Path, origins_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    origins = pd.read_csv(origins_path, dtype={"origin_id": str, "municipality_code": str})
    required_origin = {"origin_id", "municipality_code", "municipality_name", "female_population"}
    missing = required_origin - set(origins.columns)
    if missing:
        raise RuntimeError(f"Frozen origin endpoints missing required columns: {sorted(missing)}")
    if len(origins) != 12673:
        raise RuntimeError(f"Expected 12673 routing-ready origins, got {len(origins)}")
    if origins["origin_id"].duplicated().any():
        raise RuntimeError("Duplicate origin_id in frozen routing endpoints")

    origins["female_population"] = pd.to_numeric(origins["female_population"], errors="coerce")
    origins["municipality_code"] = origins["municipality_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)

    usecols = ["origin_id", "service_id", "total_travel_time_min", "reachable"]
    chunks = []
    for c in pd.read_csv(od_path, usecols=usecols, dtype={"origin_id": str, "service_id": str}, chunksize=350_000):
        c["reachable"] = c["reachable"].astype(str).str.lower().eq("true")
        c["total_travel_time_min"] = pd.to_numeric(c["total_travel_time_min"], errors="coerce")
        chunks.append(c)
    od = pd.concat(chunks, ignore_index=True)
    del chunks

    expected_rows = 12673 * 225
    if len(od) != expected_rows:
        raise RuntimeError(f"Unexpected OD row count: {len(od)} != {expected_rows}")
    if od[["origin_id", "service_id"]].duplicated().any():
        raise RuntimeError("Duplicate origin-service pairs in frozen OD")

    service_count = int(od["service_id"].nunique())
    if service_count != 225:
        raise RuntimeError(f"Expected 225 services, got {service_count}")

    od["within_60"] = od["reachable"] & od["total_travel_time_min"].le(60)
    od["within_120"] = od["reachable"] & od["total_travel_time_min"].le(120)
    od["within_180"] = od["reachable"] & od["total_travel_time_min"].le(180)

    def q50(s: pd.Series) -> float:
        x = s.dropna()
        return float(x.quantile(0.50)) if len(x) else float("nan")

    def q90(s: pd.Series) -> float:
        x = s.dropna()
        return float(x.quantile(0.90)) if len(x) else float("nan")

    grouped = od.groupby("origin_id", sort=False)
    origin_metrics = grouped.agg(
        reachable_services=("reachable", "sum"),
        services_within_60=("within_60", "sum"),
        services_within_120=("within_120", "sum"),
        services_within_180=("within_180", "sum"),
        nearest_reachable_service_time_min=("total_travel_time_min", "min"),
        median_reachable_service_time_min=("total_travel_time_min", q50),
        p90_reachable_service_time_min=("total_travel_time_min", q90),
    ).reset_index()

    for col in ["reachable_services", "services_within_60", "services_within_120", "services_within_180"]:
        origin_metrics[col] = pd.to_numeric(origin_metrics[col], errors="raise")

    origin_metrics["reachable_service_fraction"] = origin_metrics["reachable_services"] / service_count
    origin_metrics["services_within_60_fraction"] = origin_metrics["services_within_60"] / service_count
    origin_metrics["services_within_120_fraction"] = origin_metrics["services_within_120"] / service_count
    origin_metrics["services_within_180_fraction"] = origin_metrics["services_within_180"] / service_count
    origin_metrics["unreachable_service_fraction"] = 1.0 - origin_metrics["reachable_service_fraction"]

    joined = origins.merge(origin_metrics, on="origin_id", how="left", validate="one_to_one")
    if joined["reachable_services"].isna().any():
        raise RuntimeError("At least one frozen routing-ready origin is absent from the OD matrix")

    metrics = [
        "reachable_service_fraction",
        "unreachable_service_fraction",
        "services_within_60_fraction",
        "services_within_120_fraction",
        "services_within_180_fraction",
        "nearest_reachable_service_time_min",
        "median_reachable_service_time_min",
        "p90_reachable_service_time_min",
    ]

    rows = []
    for (code, name), g in joined.groupby(["municipality_code", "municipality_name"], sort=True, dropna=False):
        weights = g["female_population"]
        row = {
            "municipality_code": str(code),
            "municipality_name": str(name),
            "reference_year": 2022,
            "reference_date": "2026-08-26",
            "source": "IBGE Census 2022 female population + frozen Stage 2 reference-network OD",
            "routing_ready_origin_count": int(len(g)),
            "female_population_routing_ready": float(weights.fillna(0).sum()),
            "female_population_missing_origin_count": int(weights.isna().sum()),
            "population_weighted": bool(weights.notna().any() and (weights.fillna(0) > 0).any()),
        }
        for m in metrics:
            row[m] = weighted_mean(g[m], weights)
        rows.append(row)

    municipal = pd.DataFrame(rows).sort_values("municipality_code").reset_index(drop=True)
    municipal.to_csv(out_dir / "municipal_accessibility_matrix.csv", index=False)
    origin_metrics_out = joined[[
        "origin_id", "municipality_code", "municipality_name", "female_population",
        *metrics,
    ]]
    origin_metrics_out.to_csv(out_dir / "origin_accessibility_metrics.csv.gz", index=False, compression="gzip")

    n_municipalities = int(municipal["municipality_code"].nunique())
    audit = {
        "stage": "Stage 3 input construction - municipal accessibility matrix",
        "od_rows": int(len(od)),
        "routing_ready_origins": int(len(origins)),
        "service_count": service_count,
        "municipalities_represented": n_municipalities,
        "expected_para_municipalities": 144,
        "all_144_municipalities_represented": bool(n_municipalities == 144),
        "female_population_weighting_used": True,
        "municipalities_with_population_weight": int(municipal["population_weighted"].sum()),
        "origins_missing_female_population": int(origins["female_population"].isna().sum()),
        "unreachable_times_imputed": False,
        "reference_network_only": True,
        "waiting_time_included": False,
        "air_temporal_routing_included": False,
        "matrix_path": str(out_dir / "municipal_accessibility_matrix.csv"),
        "matrix_is_complete_mcdm_input": False,
        "scientific_note": (
            "This matrix is the municipal accessibility component derived from the frozen Stage 2 OD. "
            "It is suitable for pre-MCDM diagnostics of transport/accessibility indicators, but it is not yet the complete MCDM decision matrix until the audited non-transport indicators are joined."
        ),
    }
    (out_dir / "municipal_accessibility_matrix_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return audit


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--od", type=Path, required=True)
    p.add_argument("--origins", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("artifacts/stage3_input"))
    args = p.parse_args()
    build(args.od, args.origins, args.out)


if __name__ == "__main__":
    main()
