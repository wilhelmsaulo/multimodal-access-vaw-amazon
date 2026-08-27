from __future__ import annotations

"""Build the Stage 3 municipal non-transport institutional component.

Institutional presence is based on all 236 upstream functionally validated physical
response opportunities, independent of whether each opportunity was routable in
Stage 2. Raw counts are diagnostics; four binary absence indicators are pre-MCDM
candidates only and are not a final criterion-selection decision.
"""

import argparse
import json
import unicodedata
from pathlib import Path

import pandas as pd

SERVICE_TYPES = {
    "health": "health_specialized",
    "creas": "creas",
    "specialized_security": "specialized_security",
    "specialized_justice": "specialized_justice",
}

SOURCE_META = {
    "health": ("CNES service/classification snapshot; specialized service 165", "2026-08-19", "Versioned 2026 health-response snapshot; service 165 is the specialized sexual-violence-response core in the project evidence model."),
    "creas": ("MDS/SAGI CREAS snapshot", "2026-08-19", "Versioned 2026 social-assistance unit snapshot."),
    "specialized_security": ("Official state specialized-security/DEAM sources", "2026-08-20", "Versioned 2026 specialized-security physical-unit snapshot."),
    "specialized_justice": ("TJPA specialized VAW unit directory", "2026-08-20", "Versioned 2026 specialized-justice physical-unit snapshot."),
}


def one(root: Path, filename: str) -> Path:
    hits = list(root.rglob(filename))
    if len(hits) != 1:
        raise RuntimeError(f"Expected exactly one {filename} below {root}, got {hits}")
    return hits[0]


def norm_code(s: pd.Series) -> pd.Series:
    out = s.astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    return out.where(out.notna() & out.ne(""))


def norm_name_value(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().casefold()
    if not text:
        return None
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return " ".join(text.split())


def build(access_path: Path, service_root: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    access = pd.read_csv(access_path, dtype={"municipality_code": str}, low_memory=False)
    if not {"municipality_code", "municipality_name"}.issubset(access.columns):
        raise ValueError("Access matrix must include municipality_code and municipality_name")
    access["municipality_code"] = norm_code(access["municipality_code"]).str.zfill(7)
    if len(access) != 144 or access["municipality_code"].nunique() != 144:
        raise RuntimeError("Expected a 144-municipality access universe")

    universe = access[["municipality_code", "municipality_name"]].drop_duplicates().copy()
    universe["prefix6"] = universe["municipality_code"].str[:6]
    universe["name_key"] = universe["municipality_name"].map(norm_name_value)
    if universe["prefix6"].duplicated().any() or universe["name_key"].duplicated().any():
        raise RuntimeError("Municipality prefix/name mapping is not one-to-one")
    prefix_to_code = dict(zip(universe["prefix6"], universe["municipality_code"]))
    name_to_code = dict(zip(universe["name_key"], universe["municipality_code"]))

    services = pd.read_csv(one(service_root, "final_service_access_policy.csv.gz"), dtype={"municipality_code": str}, low_memory=False)
    required = {"physical_site_id", "service_type", "municipality_code", "municipality_name", "validation_status"}
    missing = required.difference(services.columns)
    if missing:
        raise ValueError(f"Service policy missing required columns: {sorted(missing)}")
    if services["physical_site_id"].duplicated().any():
        raise RuntimeError("Duplicate physical_site_id in final service policy")

    raw_code = norm_code(services["municipality_code"])
    services["municipality_code7"] = raw_code.str[:6].map(prefix_to_code)
    services["municipality_name_key"] = services["municipality_name"].map(norm_name_value)
    fallback = services["municipality_name_key"].map(name_to_code)
    used_name_fallback = services["municipality_code7"].isna() & fallback.notna()
    services.loc[used_name_fallback, "municipality_code7"] = fallback[used_name_fallback]

    unmapped = services[services["municipality_code7"].isna()].copy()
    if not unmapped.empty:
        sample = unmapped[["physical_site_id", "service_type", "municipality_code", "municipality_name"]].head(20).to_dict("records")
        raise RuntimeError(f"Service municipalities still unmapped after code/name resolution: {sample}")

    unknown_types = sorted(set(services["service_type"].dropna()) - set(SERVICE_TYPES))
    if unknown_types:
        raise RuntimeError(f"Unexpected service types: {unknown_types}")

    counts = (
        services.groupby(["municipality_code7", "service_type"])["physical_site_id"]
        .nunique().unstack(fill_value=0).reindex(columns=list(SERVICE_TYPES), fill_value=0)
    )
    counts.columns = [f"diagnostic__{SERVICE_TYPES[c]}_unit_count" for c in counts.columns]
    counts = counts.reset_index().rename(columns={"municipality_code7": "municipality_code"})

    institutional = universe[["municipality_code", "municipality_name"]].merge(counts, on="municipality_code", how="left", validate="one_to_one")
    count_cols = [c for c in institutional if c.startswith("diagnostic__") and c.endswith("_unit_count")]
    institutional[count_cols] = institutional[count_cols].fillna(0).astype(int)

    candidates = []
    for _, label in SERVICE_TYPES.items():
        count_col = f"diagnostic__{label}_unit_count"
        present_col = f"diagnostic__{label}_present"
        criterion_col = f"criterion__{label}_absence"
        institutional[present_col] = (institutional[count_col] > 0).astype(int)
        institutional[criterion_col] = (institutional[count_col] == 0).astype(int)
        candidates.append(criterion_col)

    present_cols = [f"diagnostic__{label}_present" for label in SERVICE_TYPES.values()]
    institutional["diagnostic__institutional_pillars_present"] = institutional[present_cols].sum(axis=1).astype(int)
    institutional["diagnostic__institutional_pillar_deficit_fraction"] = 1.0 - institutional["diagnostic__institutional_pillars_present"] / 4.0
    institutional["institutional_reference_window"] = "2026-08-19/2026-08-20"
    institutional["institutional_source_role"] = "non_transport_response_system_presence"
    institutional.to_csv(out_dir / "municipal_nontransport_institutional_matrix.csv", index=False)

    joined = access.merge(institutional.drop(columns=["municipality_name"]), on="municipality_code", how="left", validate="one_to_one")
    joined.to_csv(out_dir / "municipal_analytical_matrix_pre_sociodemographic.csv", index=False)

    provenance_rows = []
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
            "rationale": "Current 2026 response/network representation uses Census 2022 female population as demographic weights; the lag must remain explicit.",
            "action_required": "review sociodemographic harmonization and temporal sensitivity before final MCDM",
        })
    for source_type, label in SERVICE_TYPES.items():
        source, date, rationale = SOURCE_META[source_type]
        provenance_rows.append({
            "indicator": f"criterion__{label}_absence",
            "dimension": "institutional_response_presence",
            "source": source,
            "reference_year_or_date": date,
            "collection_window": "2026 snapshot",
            "spatial_unit": "physical service opportunity aggregated to municipality",
            "transformation": "binary deficit: 1 when no validated physical opportunity of the type is present; 0 otherwise",
            "role": "candidate_pre_mcdm",
            "temporal_compatibility_class": "live_snapshot",
            "rationale": rationale,
            "action_required": "audit redundancy/distribution and theoretical role before final MCDM",
        })
    pd.DataFrame(provenance_rows).to_csv(out_dir / "indicator_temporal_provenance.csv", index=False)

    municipality_presence = {}
    for _, label in SERVICE_TYPES.items():
        present = int((institutional[f"diagnostic__{label}_unit_count"] > 0).sum())
        municipality_presence[label] = {"municipalities_present": present, "municipalities_absent": 144 - present}

    summary = {
        "stage": "Stage 3 non-transport institutional integration",
        "municipalities": 144,
        "physical_service_opportunities": int(len(services)),
        "physical_site_ids_unique": int(services["physical_site_id"].nunique()),
        "service_type_counts": {str(k): int(v) for k, v in services["service_type"].value_counts().items()},
        "municipality_presence": municipality_presence,
        "municipality_resolution": {
            "resolved_by_code": int((~used_name_fallback).sum()),
            "resolved_by_official_name_fallback": int(used_name_fallback.sum()),
            "unmapped": int(services["municipality_code7"].isna().sum()),
        },
        "candidate_nontransport_criteria": candidates,
        "diagnostic_counts_are_mcdm_candidates": False,
        "routing_usability_used_to_define_institutional_presence": False,
        "institutional_presence_policy": "Count all upstream functionally validated physical opportunities regardless of Stage 2 graph-attachment/routing usability.",
        "complete_mcdm_matrix": False,
        "why_not_complete": "Sociodemographic-variable decision and full joined-matrix scientific review remain required.",
    }
    (out_dir / "nontransport_integration_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
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
