from __future__ import annotations

"""Targeted audit for municipalities with structurally incomplete Stage 3 accessibility.

This audit does not impute travel times. It distinguishes:
- no primary routing-ready origin (coverage limitation of the routing representation),
- primary origins present but zero reachable services in the frozen reference network,
- routed municipalities with at least one reachable service.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

TARGETS = {
    "1500305": "Afuá",
    "1502608": "Colares",
    "1506401": "Santa Cruz do Arari",
}


def norm_code(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)


def audit(endpoints_dir: Path, od_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    origins_path = endpoints_dir / "origin_routing_endpoints.csv.gz"
    if not origins_path.exists():
        raise FileNotFoundError(origins_path)

    origins = pd.read_csv(origins_path, dtype={"origin_id": str, "municipality_code": str})
    origins["municipality_code"] = norm_code(origins["municipality_code"])
    origin_subset = origins[origins["municipality_code"].isin(TARGETS)].copy()
    target_origin_ids = set(origin_subset["origin_id"].astype(str))

    od_parts = []
    usecols = ["origin_id", "service_id", "reachable", "total_travel_time_min"]
    for chunk in pd.read_csv(od_path, usecols=usecols, dtype={"origin_id": str, "service_id": str}, chunksize=350_000):
        part = chunk[chunk["origin_id"].isin(target_origin_ids)].copy()
        if not part.empty:
            part["reachable"] = part["reachable"].astype(str).str.lower().eq("true")
            part["total_travel_time_min"] = pd.to_numeric(part["total_travel_time_min"], errors="coerce")
            od_parts.append(part)
    target_od = pd.concat(od_parts, ignore_index=True) if od_parts else pd.DataFrame(columns=usecols)

    rows = []
    for code, official_name in TARGETS.items():
        g = origin_subset[origin_subset["municipality_code"] == code]
        ids = set(g["origin_id"].astype(str))
        odg = target_od[target_od["origin_id"].isin(ids)] if ids else target_od.iloc[0:0]
        n_origins = int(len(g))
        reachable_rows = odg[odg["reachable"] == True] if not odg.empty else odg
        n_reachable_pairs = int(len(reachable_rows))
        n_reachable_services = int(reachable_rows["service_id"].nunique()) if n_reachable_pairs else 0
        min_time = None
        if n_reachable_pairs:
            val = pd.to_numeric(reachable_rows["total_travel_time_min"], errors="coerce").min()
            min_time = None if pd.isna(val) else float(val)

        if n_origins == 0:
            classification = "network_coverage_limitation"
            interpretation = (
                "No primary routing-ready origin exists in the frozen Stage 2 endpoint artifact. "
                "The reference network therefore cannot establish accessibility or inaccessibility for this municipality."
            )
            coverage_value = None
            time_rule = "NA; do not impute or penalize as if a route had been tested."
        elif n_reachable_pairs == 0:
            classification = "true_unreachable_in_reference_network"
            interpretation = (
                "Primary routing-ready origins exist and were tested against the frozen service set, "
                "but no origin-service pair is reachable in the reference network."
            )
            coverage_value = 0.0
            time_rule = "NA; no finite route exists in the frozen reference network."
        else:
            classification = "routed_reachable"
            interpretation = "At least one primary origin-service pair is reachable in the frozen reference network."
            coverage_value = n_reachable_services / 225.0
            time_rule = "Use observed finite travel-time summaries."

        rows.append({
            "municipality_code": code,
            "municipality_name": official_name,
            "primary_routing_ready_origins": n_origins,
            "od_pairs_tested": int(len(odg)),
            "reachable_od_pairs": n_reachable_pairs,
            "reachable_unique_services": n_reachable_services,
            "reachable_service_fraction_unweighted_diagnostic": coverage_value,
            "minimum_observed_travel_time_min": min_time,
            "classification": classification,
            "interpretation": interpretation,
            "mcdm_coverage_rule": "preserve as missing due to coverage limitation" if n_origins == 0 else ("0 is an observed network-accessibility result" if n_reachable_pairs == 0 else "use computed value"),
            "mcdm_time_rule": time_rule,
        })

    detail = pd.DataFrame(rows)
    detail.to_csv(out_dir / "special_municipality_audit.csv", index=False)

    endpoint_audit_path = endpoints_dir / "frozen_routing_endpoints_audit.json"
    endpoint_audit = None
    if endpoint_audit_path.exists():
        endpoint_audit = json.loads(endpoint_audit_path.read_text(encoding="utf-8"))

    summary = {
        "stage": "Stage 3 targeted municipality audit",
        "targets": rows,
        "frozen_endpoint_audit_available": endpoint_audit is not None,
        "frozen_endpoint_audit": endpoint_audit,
        "scientific_rule": {
            "no_primary_origin": "Treat as routing/network coverage limitation, not proven inaccessibility; do not invent zero coverage or finite/infinite travel time for MCDM.",
            "primary_origin_zero_reachability": "Treat zero reachability as an observed reference-network accessibility result; keep travel-time summaries missing because no finite path exists.",
            "exclusion_policy": "Do not remove the municipality from the study universe solely because routing information is structurally missing."
        }
    }
    (out_dir / "special_municipality_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# Targeted accessibility audit: Afuá, Colares, Santa Cruz do Arari", "", "No travel time is imputed in this audit.", ""]
    for r in rows:
        md += [f"## {r['municipality_name']} ({r['municipality_code']})", f"- Classification: `{r['classification']}`", f"- Primary routing-ready origins: {r['primary_routing_ready_origins']}", f"- OD pairs tested: {r['od_pairs_tested']}", f"- Reachable OD pairs: {r['reachable_od_pairs']}", f"- Reachable unique services: {r['reachable_unique_services']}", f"- Interpretation: {r['interpretation']}", f"- MCDM coverage rule: {r['mcdm_coverage_rule']}", f"- MCDM time rule: {r['mcdm_time_rule']}", ""]
    (out_dir / "special_municipality_audit.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoints-dir", type=Path, required=True)
    p.add_argument("--od", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("artifacts/special_municipality_audit"))
    args = p.parse_args()
    audit(args.endpoints_dir, args.od, args.out)


if __name__ == "__main__":
    main()
