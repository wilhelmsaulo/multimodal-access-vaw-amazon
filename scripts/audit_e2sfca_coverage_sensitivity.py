from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd


BOUNDS = (
    "observed_population_weighted_mean",
    "lower_sensitivity_envelope",
    "upper_sensitivity_envelope",
)


def audit_envelopes(envelopes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    required = {
        "municipality_code",
        "municipality_name",
        "service_type",
        "scenario",
        "female_population_coverage_fraction",
        "sensitivity_envelope_width",
        *BOUNDS,
    }
    if missing := required - set(envelopes.columns):
        raise ValueError(f"Envelope table missing columns: {sorted(missing)}")

    coverage = envelopes[
        ["municipality_code", "municipality_name", "female_population_coverage_fraction"]
    ].drop_duplicates()
    if len(coverage) != 144:
        raise ValueError(f"Expected 144 municipalities, found {len(coverage)}")

    rows: list[dict] = []
    for service_type, group in envelopes.groupby("service_type", sort=True):
        for value_col in BOUNDS:
            wide = group.pivot(
                index="municipality_code", columns="scenario", values=value_col
            )
            corr = wide.corr(method="spearman")
            values = [
                float(corr.loc[a, b])
                for a, b in combinations(corr.columns, 2)
                if pd.notna(corr.loc[a, b])
            ]
            rows.append(
                {
                    "service_type": service_type,
                    "value_variant": value_col,
                    "pairwise_comparison_count": len(values),
                    "spearman_min": min(values),
                    "spearman_median": float(np.median(values)),
                    "spearman_max": max(values),
                }
            )
    stability = pd.DataFrame(rows)

    width = envelopes.copy()
    width["relative_envelope_width"] = np.where(
        width["upper_sensitivity_envelope"] > 0,
        width["sensitivity_envelope_width"] / width["upper_sensitivity_envelope"],
        np.nan,
    )
    width_quantiles = {}
    for service_type, group in width.groupby("service_type", sort=True):
        q = group["relative_envelope_width"].quantile([0.25, 0.5, 0.75, 0.9]).to_dict()
        width_quantiles[str(service_type)] = {
            "p25": float(q[0.25]),
            "median": float(q[0.5]),
            "p75": float(q[0.75]),
            "p90": float(q[0.9]),
        }

    afua = width.loc[width["municipality_name"].eq("Afuá")]
    audit = {
        "status": "PARAMETER_STABILITY_HIGH_COVERAGE_UNCERTAINTY_MATERIAL",
        "municipality_count": 144,
        "service_type_count": int(envelopes["service_type"].nunique()),
        "specification_count": int(envelopes["scenario"].nunique()),
        "coverage": {
            "female_population_fraction_min": float(
                coverage["female_population_coverage_fraction"].min()
            ),
            "female_population_fraction_median": float(
                coverage["female_population_coverage_fraction"].median()
            ),
            "municipalities_below_50_percent": int(
                (coverage["female_population_coverage_fraction"] < 0.5).sum()
            ),
            "municipalities_below_80_percent": int(
                (coverage["female_population_coverage_fraction"] < 0.8).sum()
            ),
            "municipalities_below_90_percent": int(
                (coverage["female_population_coverage_fraction"] < 0.9).sum()
            ),
            "fully_observed_municipality_count": int(
                coverage["female_population_coverage_fraction"].eq(1.0).sum()
            ),
            "fully_observed_municipalities": sorted(
                coverage.loc[
                    coverage["female_population_coverage_fraction"].eq(1.0),
                    "municipality_name",
                ].tolist()
            ),
        },
        "relative_envelope_width_quantiles_by_service": width_quantiles,
        "afua": {
            "coverage_fraction": float(
                afua["female_population_coverage_fraction"].drop_duplicates().item()
            ),
            "lower_envelope_always_zero": bool(
                afua["lower_sensitivity_envelope"].eq(0).all()
            ),
            "relative_envelope_width_always_one": bool(
                afua["relative_envelope_width"].eq(1).all()
            ),
        },
        "is_confidence_interval": False,
        "coverage_uncertainty_resolved": False,
        "authorized_for_single_point_mcdm_or_som": False,
        "interpretation": (
            "Agreement across threshold/decay specifications does not remove uncertainty caused "
            "by unobserved origin connectors. Parameter stability and routing-coverage uncertainty "
            "must be reported as separate properties."
        ),
    }
    return stability, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelopes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    envelopes = pd.read_csv(args.envelopes)
    stability, audit = audit_envelopes(envelopes)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stability.to_csv(args.output_dir / "e2sfca_specification_rank_stability.csv", index=False)
    (args.output_dir / "e2sfca_coverage_sensitivity_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
