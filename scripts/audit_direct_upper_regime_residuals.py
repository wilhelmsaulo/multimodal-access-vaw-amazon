from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def qstats(s: pd.Series) -> dict:
    x = pd.to_numeric(s, errors="coerce").dropna().to_numpy(dtype=float)
    return {
        "n": int(len(x)),
        "min": float(np.min(x)) if len(x) else None,
        "p25": float(np.quantile(x, 0.25)) if len(x) else None,
        "median": float(np.median(x)) if len(x) else None,
        "p75": float(np.quantile(x, 0.75)) if len(x) else None,
        "p90": float(np.quantile(x, 0.90)) if len(x) else None,
        "p95": float(np.quantile(x, 0.95)) if len(x) else None,
        "p99": float(np.quantile(x, 0.99)) if len(x) else None,
        "max": float(np.max(x)) if len(x) else None,
    }


def main() -> None:
    regimes = pd.read_csv("artifacts/direct_primary_origin_distance_regimes/direct_primary_origin_distance_regimes.csv.gz", low_memory=False)
    evidence = pd.read_csv("artifacts/direct_origin_attachment_transferability/direct_origin_attachment_transferability.csv.gz", low_memory=False)

    if len(regimes) != 14306 or len(evidence) != 14306:
        raise RuntimeError(f"Unexpected direct-primary counts: regimes={len(regimes)}, evidence={len(evidence)}")

    cols = [
        "origin_id", "municipality_code", "municipality_name", "female_population",
        "distance_to_road_m", "distance_to_waterway_m", "attachment_evidence_group",
    ]
    df = regimes.merge(evidence[cols], on="origin_id", how="left", validate="one_to_one", suffixes=("", "_evidence"))
    upper = df[~df["empirical_lower_distance_regime"]].copy()
    if len(upper) != 1765:
        raise RuntimeError(f"Expected 1765 upper-regime direct-primary origins, found {len(upper)}")

    upper["hydro_closer_than_road"] = (
        pd.to_numeric(upper["distance_to_waterway_m"], errors="coerce")
        < pd.to_numeric(upper["distance_to_road_m"], errors="coerce")
    )
    upper["residual_priority_class"] = np.where(
        upper["hydro_closer_than_road"],
        "upper_regime_hydro_proximity_priority_only",
        "upper_regime_road_proximity_priority_only",
    )
    upper["connector_promoted"] = False
    upper["travel_time_assigned"] = False

    outdir = Path("artifacts/direct_upper_regime_residuals")
    outdir.mkdir(parents=True, exist_ok=True)
    upper.to_csv(outdir / "direct_upper_regime_residuals.csv.gz", index=False, compression="gzip")

    muni = (
        upper.groupby(["municipality_code", "municipality_name"], dropna=False)
        .agg(
            origin_count=("origin_id", "size"),
            female_population=("female_population", "sum"),
            hydro_closer_count=("hydro_closer_than_road", "sum"),
        )
        .reset_index()
        .sort_values(["origin_count", "female_population"], ascending=[False, False])
    )
    muni.to_csv(outdir / "direct_upper_regime_residuals_by_municipality.csv", index=False)

    hydro = upper[upper["hydro_closer_than_road"]].copy()
    audit = {
        "direct_upper_regime_origin_count": int(len(upper)),
        "direct_upper_regime_female_population": float(pd.to_numeric(upper["female_population"], errors="coerce").fillna(0).sum()),
        "hydro_closer_priority_count": int(len(hydro)),
        "hydro_closer_priority_female_population": float(pd.to_numeric(hydro["female_population"], errors="coerce").fillna(0).sum()),
        "road_closer_priority_count": int(len(upper) - len(hydro)),
        "road_distance_m": qstats(upper["distance_to_road_m"]),
        "waterway_distance_m": qstats(upper["distance_to_waterway_m"]),
        "attachment_evidence_groups": {str(k): int(v) for k, v in upper["attachment_evidence_group"].value_counts(dropna=False).to_dict().items()},
        "top_hydro_priority_municipalities": [
            {"municipality_name": str(r.municipality_name), "origin_count": int(r.origin_count), "female_population": float(r.female_population)}
            for r in (
                hydro.groupby("municipality_name", dropna=False)
                .agg(origin_count=("origin_id", "size"), female_population=("female_population", "sum"))
                .reset_index().sort_values(["origin_count", "female_population"], ascending=[False, False]).head(20)
                .itertuples(index=False)
            )
        ],
        "proximity_used_for_connector_promotion": False,
        "connector_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "Direct-primary origins outside the empirically local cartographic regime are retained as unresolved primary-analysis attachment residuals. "
            "Road-versus-waterway proximity is used only to prioritize subsequent evidence review; it does not classify transport mode, authorize a connector, or assign travel time."
        ),
    }
    (outdir / "direct_upper_regime_residuals_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
