from __future__ import annotations

"""Build the municipal non-transport institutional component for Stage 3.

The input service-policy artifact represents 236 distinct physical response
opportunities assembled and functionally validated upstream. This script uses all
physical opportunities, not only the subset that was routable in Stage 2, because
institutional presence must not depend on graph-attachment success.

Four binary deficit indicators are exposed as pre-MCDM candidates:
- absence of specialized health response (CNES service 165),
- absence of CREAS,
- absence of specialized security (DEAM/state sources),
- absence of specialized justice (TJPA).

Raw counts/presence and pillar diversity are retained as diagnostics only. This
script does not decide final MCDM criteria or weights.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

SERVICE_TYPES = {
    "health": "health_specialized",
    "creas": "creas",
    "specialized_security": "specialized_security",
    "specialized_justice": "specialized_justice",
}

SOURCE_META = {
    "health": {
        "source": "CNES service/classification snapshot; specialized service 165",
        "reference_date": "2026-08-19",
        "temporal_compatibility_class": "live_snapshot",
        "rationale": "Versioned 2026 health-response snapshot; service 165 is the specialized sexual-violence-response core in the project evidence model.",
    },
    "creas": {
        "source": "MDS/SAGI CREAS snapshot",
        "reference_date": "2026-08-19",
        "temporal_compatibility_class": "live_snapshot",
        "rationale": "Versioned 2026 social-assistance unit snapshot.",
    },
    "specialized_security": {
        "source": "Official state specialized-security/DEAM sources",
        "reference_date": "2026-08-20",
        "temporal_compatibility_class": "live_snapshot",
        "rationale": "Versioned 2026 specialized-security physical-unit snapshot.",
    },
    "specialized_justice": {
        "source": "TJPA specialized VAW unit directory",
        "reference_date": "2026-08-20",
        "temporal_compatibility_class": "live_snapshot",
        "rationale": "Versioned 2026 specialized-justice physical-unit snapshot.",
    },
}


def one(root: Path, filename: str) -> Path:
    hits = list(root.rglob(filename))
    if len(hits) != 1:
        raise RuntimeError(f"Expected exactly one {filename} below {root}, got {hits}")
    return hits[0]


def normalize_municipality_code(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()


def build(access_path: Path, service_root: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    access = pd.read_csv(access_path, dtype={"municipality_code": str}, low_memory=False)
    required_access = {"municipality_code", "municipality_name"}
    missing = required_access.difference(access.columns)
    if missing:
        raise ValueError(f"Access matrix missing required columns: {sorted(missing)}")
    access["municipality_code"] = normalize_municipality_code(access["municipality_code"]).str.zfill(7)
    if len(access) != 144 or access["municipality_code"].nunique() != 144:
        raise RuntimeError("Expected a 144-municipality access universe")

    universe = access[["municipality_code", "municipality_name"]].drop_duplicates().copy()
    universe["municipality_prefix6"] = universe["municipality_code"].str[:6]
    if universe["municipality_prefix6"].duplicated().any():
        raise RuntimeError("Six-digit municipality prefixes are not unique in the 144-municipality universe")
    prefix_to_code = dict(zip(universe["municipality_prefix6"], universe["municipality_code"]))

    policy_path = one(service_root, "final_service_access_policy.csv.gz")
    services = pd.read_csv(policy_path, dtype={"municipality_code": str}, low_memory=False)
    required_services = {"physical_site_id", "service_type", "municipality_code", "validation_status"}
    missing = required_services.difference(services.columns)
    if missing:
        raise ValueError(f"Service policy missing required columns: {sorted(missing)}")

    # A physical opportunity must be counted once. The upstream policy currently
    # contains one row per distinct physical_site_id; fail loudly if that changes.
    if services["physical_site_id"].duplicated().any():
        dup = services.loc[services["physical_site_id"].duplicated(False), "physical_site_id"].head(20).tolist()
        raise RuntimeError(f"Duplicate physical sites in final policy: {dup}")

    raw_code = normalize_municipality_code(services["municipality_code"])
    services["municipality_prefix6"] = raw_code.str[:6].str.zfill(6)
    services["municipality_code7"] = services["municipality_prefix6"].map(prefix_to_code)
    unmapped = services[services["municipality_code7"].isna()].copy()
    if not unmapped.empty:
        sample = unmapped[["physical_site_id", "service_type", "municipality_code"]].head(20).to_dict("records")
        raise RuntimeError(f"Service municipality codes do not map to Pará universe: {sample}")

    unknown_types = sorted(set(services["service_type"].dropna()) - set(SERVICE_TYPES))
    if unknown_types:
        raise RuntimeError(f"Unexpected service types in final policy: {unknown_types}")

    # Preserve all validated physical opportunities independent of Stage 2 routing
    # usability; graph attachment is not an institutional-presence criterion.
    counts = (
        services.groupby(["municipality_code7", "service_type"])["physical_site_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=list(SERVICE_TYPES), fill_value=0)
    )
    counts.columns = [f"diagnostic__{SERVICE_TYPES[c]}_unit_count" for c in counts.columns]
    counts = counts.reset_index().rename(columns={"municipality_code7": "municipality_code"})

    institutional = universe[["municipality_code", "municipality_name"]].merge(
        counts, on="municipality_code", how="left", validate="one_to_one"
    )
    count_cols = [c for c in institutional.columns if c.startswith("diagnostic__") and c.endswith("_unit_count")]
    institutional[count_cols] = institutional[count_cols].fillna(0).astype(int)

    candidate_columns = []
    for source_type, label in SERVICE_TYPES.items():
        count_col = f"diagnostic__{label}_unit_count"
        presence_col = f"diagnostic__{label}_present"
        criterion_col = f"criterion__{label}_absence"
        institutional[presence_col] = (institutional[count_col] > 0).astype(int)
        institutional[criterion_col] = (institutional[count_col] == 0).astype(int)
        candidate_columns.append(criterion_col)

    presence_cols = [f"diagnostic__{label}_present" for label in SERVICE_TYPES.values()]
    institutional["diagnostic__institutional_pillars_present"] = institutional[presence_cols].sum(axis=1).astype(int)
    institutional["diagnostic__institutional_pillar_deficit_fraction"] = (
        1.0 - institutional["diagnostic__institutional_pillars_present"] / float(len(SERVICE_TYPES))
    )
    institutional["institutional_reference_window"] = "2026-08-19/2026-08-20"
    institutional["institutional_source_role"] = "non_transport_response_system_presence"

    institutional.to_csv(out_dir / "municipal_nontransport_institutional_matrix.csv", index=False)

    joined = access.merge(
        institutional.drop(columns=["municipality_name"]),
        on="municipality_code", how="left", validate="one_to_one"
    )
    joined.to_csv(out_dir / "municipal_analytical_matrix_pre_sociodemographic.csv", index=False)

    provenance_rows = []
    # Access criteria are a mixed-reference composite because population weighting is
    # Census 2022 while routing/service network evidence is the frozen 2026 snapshot.
    for criterion in [c for c in access.columns if c.startswith("criterion__")]:
        provenance_rows.append({
            "indicator": criterion,
            "dimension": "multimodal_access",
            "source": "IBGE Census 2022 female population + frozen Stage 2 2026 reference-network OD",
            "reference_year_or_date": "2022 population weights; 2026-08-26 frozen network/reference OD",
            "collection_window": "mixed",
            "spatial_unit": "census-sector origins aggregated to municipality",
            "transformation": "female-population-weighted municipal aggregation where routing-ready origins exist",
            "role": "candidate_pre_mcdm",
            "temporal_compatibility_class": "mixed_reference",
            "rationale": "The response-system/network representation is current to 2026, while Census 2022 female population supplies stable demographic weights; lag must be disclosed and tested/sensitivity-reviewed before final MCDM.",
            "action_required": "retain explicit temporal caveat; review sociodemographic harmonization before final matrix",
        })

    for source_type, label in SERVICE_TYPES.items():
        meta = SOURCE_META[source_type]
        provenance_rows.append({
            "indicator": f"criterion__{label}_absence",
            "dimension": "institutional_response_presence",
            "source": meta["source"],
            "reference_year_or_date": meta["reference_date"],
            "collection_window": "2026 snapshot",
            "spatial_unit": "physical service opportunity aggregated to municipality",
            "transformation": "binary deficit: 1 when no validated physical opportunity of the type is present; 0 otherwise",
            "role": "candidate_pre_mcdm",
            "temporal_compatibility_class": meta["temporal_compatibility_class"],
            "rationale": meta["rationale"],
            "action_required": "audit redundancy/distribution and theoretical role before final MCDM",
        })

    provenance = pd.DataFrame(provenance_rows)
    provenance.to_csv(out_dir / "indicator_temporal_provenance.csv", index=False)

    type_counts = {str(k): int(v) for k, v in services["service_type"].value_counts().items()}
    municipality_presence = {}
    for source_type, label in SERVICE_TYPES.items():
        present = int((institutional[f"diagnostic__{label}_unit_count"] > 0).sum())
        municipality_presence[label] = {
            "municipalities_present": present,
            "municipalities_absent": 144 - present,
        }

    summary = {
        "stage": "Stage 3 non-transport institutional integration",
        "municipalities": int(len(institutional)),
        "physical_service_opportunities": int(len(services)),
        "physical_site_ids_unique": int(services["physical_site_id"].nunique()),
        "service_type_counts": type_counts,
        "municipality_presence": municipality_presence,
        "candidate_nontransport_criteria": candidate_columns,
        "diagnostic_counts_are_mcdm_candidates": False,
        "routing_usability_used_to_define_institutional_presence": False,
        "institutional_presence_policy": "All upstream functionally validated physical opportunities in the final service policy are counted regardless of Stage 2 graph-attachment/routing usability.",
        "complete_mcdm_matrix": False,
        "why_not_complete": "Sociodemographic-variable decision and full joined-matrix scientific review are still required before final MCDM specification.",
        "outputs": {
            "institutional_matrix": str(out_dir / "municipal_nontransport_institutional_matrix.csv"),
            "pre_sociodemographic_matrix": str(out_dir / "municipal_analytical_matrix_pre_sociodemographic.csv"),
            "temporal_provenance": str(out_dir / "indicator_temporal_provenance.csv"),
        },
    }
    (out_dir / "nontransport_integration_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--access", type=Path, required=True)
    p.add_argument("--service-root", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("artifacts/stage3_nontransport"))
    args = p.parse_args()
    build(args.access, args.service_root, args.out)


if __name__ == "__main__":
    main()
