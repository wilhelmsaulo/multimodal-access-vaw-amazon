from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


PRIMARY_PATH_CLASSES = {"footway", "path", "service"}


def build_connector_ceiling_audit(
    evidence: pd.DataFrame,
    endpoints: pd.DataFrame,
    paths: pd.DataFrame,
    *,
    coverage_threshold: float = 0.5,
    proximity_boundary_m: float = 173.996907,
) -> tuple[pd.DataFrame, dict]:
    ready_ids = set(endpoints["origin_id"].astype("string"))
    x = evidence.copy()
    x["routing_ready"] = x["origin_id"].astype("string").isin(ready_ids)
    female = pd.to_numeric(x["female_population"], errors="coerce").fillna(0)
    x["routing_ready_female_population"] = female * x["routing_ready"].astype(int)

    municipality = (
        x.groupby(["municipality_code", "municipality_name"], dropna=False)
        .agg(
            total_origins=("origin_id", "size"),
            routing_ready_origins=("routing_ready", "sum"),
            total_female_population=("female_population", "sum"),
            routing_ready_female_population=("routing_ready_female_population", "sum"),
        )
        .reset_index()
    )
    municipality["primary_female_population_coverage_fraction"] = (
        municipality["routing_ready_female_population"]
        / municipality["total_female_population"]
    )
    low_codes = set(
        municipality.loc[
            municipality["primary_female_population_coverage_fraction"] < coverage_threshold,
            "municipality_code",
        ]
    )

    residual = x.loc[(~x["routing_ready"]) & x["municipality_code"].isin(low_codes)].copy()
    path_cols = [
        "origin_id",
        "path_highway_classes",
        "local_osm_path_distance_to_primary_motor_m",
    ]
    residual = residual.merge(
        paths[path_cols], on="origin_id", how="left", validate="one_to_one"
    )
    observed_path = residual["origin_access_evidence_class"].eq(
        "local_osm_topology_connects_to_primary_motor"
    )
    eligible_semantics = residual["path_highway_classes"].isin(PRIMARY_PATH_CLASSES)
    near_observed_node = (
        pd.to_numeric(residual["distance_to_nearest_osm_node_m"], errors="coerce")
        <= proximity_boundary_m
    )
    residual["existing_evidence_sensitivity_candidate"] = (
        observed_path & eligible_semantics & near_observed_node
    )
    residual["candidate_female_population"] = (
        pd.to_numeric(residual["female_population"], errors="coerce").fillna(0)
        * residual["existing_evidence_sensitivity_candidate"].astype(int)
    )

    candidate = (
        residual.groupby(["municipality_code", "municipality_name"], dropna=False)
        .agg(
            excluded_origins=("origin_id", "size"),
            sensitivity_candidate_origins=("existing_evidence_sensitivity_candidate", "sum"),
            sensitivity_candidate_female_population=("candidate_female_population", "sum"),
        )
        .reset_index()
    )
    out = municipality[municipality["municipality_code"].isin(low_codes)].merge(
        candidate,
        on=["municipality_code", "municipality_name"],
        how="left",
        validate="one_to_one",
    )
    out["existing_evidence_ceiling_female_population"] = (
        out["routing_ready_female_population"]
        + out["sensitivity_candidate_female_population"]
    )
    out["existing_evidence_ceiling_coverage_fraction"] = (
        out["existing_evidence_ceiling_female_population"]
        / out["total_female_population"]
    )
    out = out.sort_values(
        ["existing_evidence_ceiling_coverage_fraction", "municipality_name"]
    )

    candidates = residual.loc[residual["existing_evidence_sensitivity_candidate"]]
    audit = {
        "status": "EXISTING_EVIDENCE_RECOVERY_CEILING_QUANTIFIED",
        "coverage_threshold": coverage_threshold,
        "proximity_boundary_m": proximity_boundary_m,
        "low_coverage_municipality_count": int(len(low_codes)),
        "low_coverage_excluded_origin_count": int(len(residual)),
        "low_coverage_excluded_female_population": float(
            pd.to_numeric(residual["female_population"], errors="coerce").fillna(0).sum()
        ),
        "existing_evidence_sensitivity_candidate_origin_count": int(len(candidates)),
        "existing_evidence_sensitivity_candidate_female_population": float(
            pd.to_numeric(candidates["female_population"], errors="coerce").fillna(0).sum()
        ),
        "candidate_municipalities": sorted(candidates["municipality_name"].unique().tolist()),
        "afua_existing_evidence_ceiling_coverage_fraction": float(
            out.loc[out["municipality_name"].eq("Afuá"), "existing_evidence_ceiling_coverage_fraction"].item()
        ),
        "safeguards": {
            "candidates_promoted_to_primary_routing": False,
            "walking_or_motor_speed_assigned": False,
            "track_or_proposed_paths_accepted": False,
            "nearest_node_snap_accepted": False,
            "hydro_route_inferred": False,
        },
        "interpretation": (
            "This is an optimistic screening ceiling using only already observed OSM local paths, "
            "eligible path semantics, and the locked empirical proximity boundary. It is not a routing "
            "result and does not authorize connector promotion or travel-time assignment."
        ),
    }
    return out, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--endpoints", type=Path, required=True)
    parser.add_argument("--paths", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--coverage-threshold", type=float, default=0.5)
    parser.add_argument("--proximity-boundary-m", type=float, default=173.996907)
    args = parser.parse_args()

    evidence = pd.read_csv(args.evidence, dtype={"origin_id": "string"}, low_memory=False)
    endpoints = pd.read_csv(args.endpoints, dtype={"origin_id": "string"}, low_memory=False)
    paths = pd.read_csv(args.paths, dtype={"origin_id": "string"}, low_memory=False)
    municipality, audit = build_connector_ceiling_audit(
        evidence,
        endpoints,
        paths,
        coverage_threshold=args.coverage_threshold,
        proximity_boundary_m=args.proximity_boundary_m,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    municipality.to_csv(args.output_dir / "low_coverage_existing_evidence_ceiling.csv", index=False)
    (args.output_dir / "low_coverage_connector_ceiling_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
