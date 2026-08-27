from __future__ import annotations

"""Build an auditable sociodemographic candidate layer from frozen Census 2022 sectors.

Policy:
- municipal population totals are diagnostics/aggregation supports, not MCDM criteria;
- rural female share is exposed as a *candidate* for redundancy/theory review because
  territorial rurality can shape service access independently of municipal averages;
- female age structure is retained for diagnostics/SOM exploration, not promoted to
  MCDM in this step because age-band data have non-trivial sector-level suppression;
- suppressed/unavailable Census values are never inferred.
"""

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

AGE_COLS = [f"V{x:05d}" for x in range(1020, 1031)]
AGE_15_29 = ["V01023", "V01024", "V01025"]
AGE_30_59 = ["V01026", "V01027", "V01028"]
AGE_60_PLUS = ["V01029", "V01030"]


def read_sector_attributes(gpkg: Path) -> pd.DataFrame:
    with sqlite3.connect(gpkg) as con:
        cols = [
            "CD_SETOR", "CD_MUN", "NM_MUN", "SITUACAO", "CD_SIT", "CD_TIPO",
            "v0001", "V01008", *AGE_COLS, "population_data_status"
        ]
        query = "SELECT " + ",".join(cols) + " FROM pa_census_sectors_2022"
        return pd.read_sql_query(query, con)


def build(pre_matrix: Path, gpkg: Path, provenance_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(pre_matrix, dtype={"municipality_code": str}, low_memory=False)
    if len(base) != 144 or base["municipality_code"].nunique() != 144:
        raise RuntimeError("Expected 144 municipalities in pre-sociodemographic matrix")
    base["municipality_code"] = base["municipality_code"].astype(str).str.zfill(7)

    sec = read_sector_attributes(gpkg)
    sec["CD_MUN"] = sec["CD_MUN"].astype(str).str.zfill(7)
    if len(sec) != 16714 or sec["CD_MUN"].nunique() != 144:
        raise RuntimeError("Frozen Census artifact does not match audited 16,714-sector / 144-municipality universe")

    # SITUACAO-missing sectors must not carry population if rural share is to be
    # interpreted without reclassification assumptions.
    unknown_sit = sec["SITUACAO"].isna()
    unknown_sit_pop = pd.to_numeric(sec.loc[unknown_sit, "V01008"], errors="coerce").fillna(0).sum()
    if unknown_sit_pop != 0:
        raise RuntimeError("Sectors without SITUACAO contain female population; rural share would require an explicit classification rule")

    sec["female_observed"] = pd.to_numeric(sec["V01008"], errors="coerce")
    sec["female_rural_observed"] = np.where(sec["SITUACAO"].eq("Rural"), sec["female_observed"], 0.0)
    sec["female_urban_observed"] = np.where(sec["SITUACAO"].eq("Urbana"), sec["female_observed"], 0.0)
    sec["female_unavailable_sector"] = sec["female_observed"].isna().astype(int)

    for c in AGE_COLS:
        sec[c] = pd.to_numeric(sec[c], errors="coerce")
    sec["age_complete"] = sec[AGE_COLS].notna().all(axis=1)
    complete = sec["age_complete"]
    sec["female_age_covered"] = np.where(complete, sec["female_observed"], 0.0)
    sec["female_15_29"] = np.where(complete, sec[AGE_15_29].sum(axis=1), 0.0)
    sec["female_30_59"] = np.where(complete, sec[AGE_30_59].sum(axis=1), 0.0)
    sec["female_60_plus"] = np.where(complete, sec[AGE_60_PLUS].sum(axis=1), 0.0)

    grouped = sec.groupby(["CD_MUN", "NM_MUN"], as_index=False).agg(
        diagnostic__census_sector_count=("CD_SETOR", "size"),
        diagnostic__female_population_observed=("female_observed", "sum"),
        diagnostic__female_rural_observed=("female_rural_observed", "sum"),
        diagnostic__female_urban_observed=("female_urban_observed", "sum"),
        diagnostic__female_population_unavailable_sector_count=("female_unavailable_sector", "sum"),
        diagnostic__female_age_covered=("female_age_covered", "sum"),
        diagnostic__female_15_29=("female_15_29", "sum"),
        diagnostic__female_30_59=("female_30_59", "sum"),
        diagnostic__female_60_plus=("female_60_plus", "sum"),
        diagnostic__age_complete_sector_count=("age_complete", "sum"),
    ).rename(columns={"CD_MUN": "municipality_code", "NM_MUN": "census_municipality_name"})

    denom = grouped["diagnostic__female_population_observed"].replace(0, np.nan)
    grouped["criterion__rural_female_share"] = grouped["diagnostic__female_rural_observed"] / denom
    grouped["diagnostic__age_female_coverage_fraction"] = grouped["diagnostic__female_age_covered"] / denom
    age_denom = grouped["diagnostic__female_age_covered"].replace(0, np.nan)
    grouped["diagnostic__female_15_29_share_age_covered"] = grouped["diagnostic__female_15_29"] / age_denom
    grouped["diagnostic__female_30_59_share_age_covered"] = grouped["diagnostic__female_30_59"] / age_denom
    grouped["diagnostic__female_60_plus_share_age_covered"] = grouped["diagnostic__female_60_plus"] / age_denom

    if grouped["municipality_code"].nunique() != 144 or grouped["criterion__rural_female_share"].isna().any():
        raise RuntimeError("Rural female share must be available for all 144 municipalities")

    grouped.to_csv(out_dir / "municipal_sociodemographic_diagnostics.csv", index=False)
    joined = base.merge(grouped.drop(columns=["census_municipality_name"]), on="municipality_code", how="left", validate="one_to_one")
    joined.to_csv(out_dir / "municipal_analytical_matrix_with_sociospatial_candidate.csv", index=False)

    inventory = pd.DataFrame([
        {
            "variable": "rural_female_share",
            "matrix_column": "criterion__rural_female_share",
            "source": "IBGE Census 2022 aggregated census sectors",
            "reference_period": "2022",
            "spatial_basis": "sector SITUACAO weighted by observed female population V01008, aggregated to municipality",
            "proposed_role": "candidate_pre_mcdm",
            "theoretical_role": "territorial/rural exposure context that may constrain practical service access beyond municipality-average network metrics",
            "risk_of_double_counting": "moderate; expected relationship with multimodal accessibility, therefore correlation/VIF and conceptual review required",
            "missingness_policy": "do not infer unavailable female counts; SITUACAO-null sectors have zero population in frozen artifact",
            "decision_now": "retain for statistical/theoretical audit; not yet final MCDM criterion",
        },
        {
            "variable": "female_age_structure",
            "matrix_column": "diagnostic__female_15_29_share_age_covered; diagnostic__female_30_59_share_age_covered; diagnostic__female_60_plus_share_age_covered",
            "source": "IBGE Census 2022 aggregated census sectors V01020-V01030",
            "reference_period": "2022",
            "spatial_basis": "age-complete sectors aggregated to municipality",
            "proposed_role": "diagnostic_and_SOM_candidate",
            "theoretical_role": "describes composition of the female population without interpreting age itself as violence risk",
            "risk_of_double_counting": "low conceptually, but age-band suppression creates uneven coverage",
            "missingness_policy": "no inference of suppressed bands; report municipal female-population coverage explicitly",
            "decision_now": "do not promote to MCDM until coverage/sensitivity strategy is justified",
        },
        {
            "variable": "female_population_total",
            "matrix_column": "diagnostic__female_population_observed",
            "source": "IBGE Census 2022 V01008",
            "reference_period": "2022",
            "spatial_basis": "sector totals aggregated to municipality",
            "proposed_role": "diagnostic_weighting_support",
            "theoretical_role": "population magnitude / aggregation weight",
            "risk_of_double_counting": "high if used as MCDM criterion because female population already weights accessibility aggregation",
            "missingness_policy": "preserve unavailable sector values without inference",
            "decision_now": "exclude from core MCDM criteria",
        },
        {
            "variable": "income_literacy_race_ethnicity",
            "matrix_column": "not_materialized_in_current_frozen_artifact",
            "source": "additional official Census 2022 aggregates required",
            "reference_period": "2022",
            "spatial_basis": "to be audited",
            "proposed_role": "defer",
            "theoretical_role": "possible socioeconomic vulnerability/context variables",
            "risk_of_double_counting": "unknown until definitions and correlations are audited",
            "missingness_policy": "must use official denominators/suppression rules; no synthetic fill",
            "decision_now": "do not add blindly; source and audit separately before any inclusion decision",
        },
    ])
    inventory.to_csv(out_dir / "sociodemographic_candidate_inventory.csv", index=False)

    # Extend provenance without overwriting the prior table.
    prov = pd.read_csv(provenance_path)
    rural_prov = pd.DataFrame([{
        "indicator": "criterion__rural_female_share",
        "dimension": "sociodemographic_territorial_context",
        "source": "IBGE Census 2022 aggregated census sectors",
        "reference_year_or_date": "2022",
        "collection_window": "Census 2022",
        "spatial_unit": "census sector aggregated to municipality",
        "transformation": "observed rural female population / observed female population",
        "role": "candidate_pre_mcdm",
        "temporal_compatibility_class": "aligned_with_population_weights_2022; lagged_vs_2026_service_network",
        "rationale": "Rurality may capture territorial context not fully represented by municipality-average network accessibility, but overlap must be tested.",
        "action_required": "audit correlation/VIF and conceptual double counting before final criterion selection",
    }])
    pd.concat([prov, rural_prov], ignore_index=True).to_csv(out_dir / "indicator_temporal_provenance_with_sociodemographic.csv", index=False)

    age_cov = grouped["diagnostic__age_female_coverage_fraction"]
    summary = {
        "stage": "Stage 3 sociodemographic candidate audit",
        "municipalities": 144,
        "census_sectors": int(len(sec)),
        "rural_candidate_complete_municipalities": int(grouped["criterion__rural_female_share"].notna().sum()),
        "female_population_observed_total": float(grouped["diagnostic__female_population_observed"].sum()),
        "female_population_unavailable_sector_count": int(sec["female_unavailable_sector"].sum()),
        "situation_null_sectors": int(unknown_sit.sum()),
        "situation_null_female_population_observed": float(unknown_sit_pop),
        "age_complete_sectors": int(sec["age_complete"].sum()),
        "age_incomplete_sectors": int((~sec["age_complete"]).sum()),
        "municipal_age_population_coverage_fraction": {
            "min": float(age_cov.min()), "median": float(age_cov.median()), "mean": float(age_cov.mean()), "max": float(age_cov.max())
        },
        "mcdm_candidate_added_for_audit": ["criterion__rural_female_share"],
        "socio_features_reserved_for_diagnostic_or_SOM": [
            "diagnostic__female_15_29_share_age_covered",
            "diagnostic__female_30_59_share_age_covered",
            "diagnostic__female_60_plus_share_age_covered",
        ],
        "population_size_core_mcdm_candidate": False,
        "age_structure_core_mcdm_candidate": False,
        "additional_socioeconomic_variables_added": False,
        "scientific_note": "This step tests a restrained, already-versioned sociodemographic specification. It does not assume that demographic composition is a proxy for violence incidence or reporting demand.",
    }
    (out_dir / "sociodemographic_candidate_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pre-matrix", type=Path, required=True)
    p.add_argument("--census-gpkg", type=Path, required=True)
    p.add_argument("--provenance", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("artifacts/stage3_sociodemographic"))
    args = p.parse_args()
    build(args.pre_matrix, args.census_gpkg, args.provenance, args.out)


if __name__ == "__main__":
    main()
