from __future__ import annotations

"""Trace Afuá through the upstream origin-access evidence used to build routing endpoints.

This is a forensic audit only. It does not promote excluded origins, invent access
speeds, or modify the frozen Stage 2 routing graph. It reports which upstream
attachment classes contain Afuá origins and why they were or were not eligible for
primary routing.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

AFUA_CODE = "1500305"
AFUA_NAME = "Afuá"


def norm_code(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)


def one(root: Path, name: str) -> Path:
    hits = list(root.rglob(name))
    if len(hits) != 1:
        raise RuntimeError(f"Expected exactly one {name} below {root}, got {hits}")
    return hits[0]


def read_csv(root: Path, name: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(one(root, name), low_memory=False, **kwargs)


def filter_afua_by_ids(df: pd.DataFrame, ids: set[str]) -> pd.DataFrame:
    if "origin_id" not in df.columns:
        return df.iloc[0:0].copy()
    out = df.copy()
    out["origin_id"] = out["origin_id"].astype(str)
    return out[out["origin_id"].isin(ids)].copy()


def audit(nominal_dir: Path, empirical_dir: Path, endpoints_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    evidence = read_csv(nominal_dir, "origin_network_access_evidence.csv.gz", dtype={"origin_id": str, "municipality_code": str})
    evidence["municipality_code"] = norm_code(evidence["municipality_code"])
    afua_evidence = evidence[evidence["municipality_code"] == AFUA_CODE].copy()
    afua_ids = set(afua_evidence["origin_id"].astype(str))
    if not afua_ids:
        raise RuntimeError("Afuá has no origins in upstream origin_network_access_evidence.csv.gz")

    datasets = {
        "nominal_cartographic": read_csv(nominal_dir, "origin_cartographic_node_attachments.csv.gz", dtype={"origin_id": str}),
        "direct_primary_empirical": read_csv(empirical_dir, "direct_primary_empirical_node_attachments.csv.gz", dtype={"origin_id": str}),
        "local_topology_empirical": read_csv(empirical_dir, "local_topology_empirical_node_attachments.csv.gz", dtype={"origin_id": str}),
        "gated_pedestrian": read_csv(empirical_dir, "gated_local_pedestrian_access_times.csv.gz", dtype={"origin_id": str}),
        "local_access_to_primary_motor": read_csv(empirical_dir, "origin_local_access_to_primary_motor.csv.gz", dtype={"origin_id": str}),
    }

    endpoints = read_csv(endpoints_dir, "origin_routing_endpoints.csv.gz", dtype={"origin_id": str, "municipality_code": str})
    endpoints["municipality_code"] = norm_code(endpoints["municipality_code"])
    afua_endpoints = endpoints[endpoints["municipality_code"] == AFUA_CODE].copy()

    detail_rows = []
    dataset_summary = {}
    per_origin = pd.DataFrame({"origin_id": sorted(afua_ids)})

    for label, df in datasets.items():
        sub = filter_afua_by_ids(df, afua_ids)
        dataset_summary[label] = {
            "rows": int(len(sub)),
            "unique_origins": int(sub["origin_id"].nunique()) if "origin_id" in sub.columns else 0,
            "columns": list(sub.columns),
        }
        present = set(sub["origin_id"].astype(str)) if "origin_id" in sub.columns else set()
        per_origin[f"in_{label}"] = per_origin["origin_id"].isin(present)
        if not sub.empty:
            for _, r in sub.iterrows():
                row = {"dataset": label, "origin_id": str(r.get("origin_id", ""))}
                for c in sub.columns:
                    if c == "origin_id":
                        continue
                    v = r[c]
                    if pd.isna(v):
                        row[c] = None
                    elif isinstance(v, (str, int, float, bool)):
                        row[c] = v
                    else:
                        row[c] = str(v)
                detail_rows.append(row)

    per_origin["primary_routing_ready"] = per_origin["origin_id"].isin(set(afua_endpoints["origin_id"].astype(str)))

    # Infer conservative exclusion categories using only membership in frozen evidence classes.
    per_origin["in_any_structural_attachment"] = per_origin[[
        "in_nominal_cartographic", "in_direct_primary_empirical", "in_local_topology_empirical"
    ]].any(axis=1)
    per_origin["has_physical_pedestrian_path"] = per_origin["in_gated_pedestrian"]

    def classify(row: pd.Series) -> str:
        if row["primary_routing_ready"]:
            return "primary_routing_ready"
        if row["has_physical_pedestrian_path"]:
            return "pedestrian_evidence_present_but_not_promoted_unexpected"
        if row["in_direct_primary_empirical"] or row["in_nominal_cartographic"]:
            return "direct_identity_evidence_present_but_not_promoted_unexpected"
        if row["in_local_topology_empirical"] or row["in_local_access_to_primary_motor"]:
            return "local_structural_or_nonprimary_access_only"
        return "no_validated_attachment_in_consumed_upstream_classes"

    per_origin["forensic_class"] = per_origin.apply(classify, axis=1)

    # Summarize categorical/policy columns for Afuá without assuming their names.
    likely_policy_tokens = ("class", "status", "policy", "road", "highway", "path", "track", "mode", "usable", "primary", "reason", "access")
    value_profiles = {}
    for label, df in datasets.items():
        sub = filter_afua_by_ids(df, afua_ids)
        profiles = {}
        for c in sub.columns:
            if c == "origin_id":
                continue
            lc = c.lower()
            if any(tok in lc for tok in likely_policy_tokens):
                vals = sub[c].dropna().astype(str).value_counts().head(30)
                if len(vals):
                    profiles[c] = {str(k): int(v) for k, v in vals.items()}
        value_profiles[label] = profiles

    class_counts = {str(k): int(v) for k, v in per_origin["forensic_class"].value_counts().items()}

    # Determine whether current frozen evidence supports automatic repair.
    unexpected = per_origin[per_origin["forensic_class"].str.contains("unexpected", na=False)]
    if len(unexpected):
        repair_recommendation = (
            "Do not auto-repair. Some Afuá origins appear in evidence classes normally consumed for primary routing but were not promoted; inspect exact rows and endpoint assembly logic before changing the frozen graph."
        )
        repair_supported = False
    elif per_origin["in_local_topology_empirical"].any() or per_origin["in_local_access_to_primary_motor"].any():
        repair_recommendation = (
            "No automatic primary promotion is scientifically justified from the consumed frozen evidence. Afuá is represented only by local/nonprimary structural evidence; retain the coverage-limitation flag unless an independently validated primary or physical pedestrian/hydro connection is established."
        )
        repair_supported = False
    else:
        repair_recommendation = (
            "No validated attachment evidence consumed by the endpoint builder is available for Afuá. Retain the coverage-limitation flag and do not impute accessibility."
        )
        repair_supported = False

    per_origin.to_csv(out_dir / "afua_origin_trace.csv", index=False)
    pd.DataFrame(detail_rows).to_csv(out_dir / "afua_upstream_rows.csv", index=False)

    summary = {
        "stage": "Stage 3 Afua upstream forensic audit",
        "municipality_code": AFUA_CODE,
        "municipality_name": AFUA_NAME,
        "origins_in_network_access_evidence": int(len(afua_ids)),
        "female_population_sum_in_evidence": float(pd.to_numeric(afua_evidence.get("female_population"), errors="coerce").fillna(0).sum()) if "female_population" in afua_evidence.columns else None,
        "primary_routing_ready_origins": int(len(afua_endpoints)),
        "dataset_summary": dataset_summary,
        "forensic_class_counts": class_counts,
        "afua_policy_value_profiles": value_profiles,
        "automatic_repair_supported_by_current_frozen_evidence": repair_supported,
        "repair_recommendation": repair_recommendation,
        "scientific_guardrails": [
            "Do not convert cartographic distance into travel time.",
            "Do not promote track/restricted/nonoperational evidence into primary routing without independent validation.",
            "Do not infer hydro travel time from hypothetical speeds.",
            "Do not assign zero accessibility merely because no primary routing-ready origin exists."
        ],
    }
    (out_dir / "afua_upstream_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Afuá upstream routing-origin audit", "",
        f"- Origins in upstream access evidence: {summary['origins_in_network_access_evidence']}",
        f"- Primary routing-ready origins: {summary['primary_routing_ready_origins']}",
        f"- Automatic repair supported: {summary['automatic_repair_supported_by_current_frozen_evidence']}",
        f"- Recommendation: {summary['repair_recommendation']}", "",
        "## Forensic classes", ""
    ]
    for k, v in class_counts.items():
        md.append(f"- `{k}`: {v}")
    md += ["", "## Guardrails", ""] + [f"- {x}" for x in summary["scientific_guardrails"]]
    (out_dir / "afua_upstream_audit.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--nominal-dir", type=Path, required=True)
    p.add_argument("--empirical-dir", type=Path, required=True)
    p.add_argument("--endpoints-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("artifacts/afua_upstream_audit"))
    args = p.parse_args()
    audit(args.nominal_dir, args.empirical_dir, args.endpoints_dir, args.out)


if __name__ == "__main__":
    main()
