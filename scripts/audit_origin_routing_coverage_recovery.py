from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

import pandas as pd


def _ascii_key(value: object) -> str:
    return unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().casefold()


def _summary(frame: pd.DataFrame) -> dict[str, float | int]:
    return {
        "origin_count": int(len(frame)),
        "female_population": float(
            pd.to_numeric(frame["female_population"], errors="coerce").fillna(0).sum()
        ),
        "municipality_count": int(frame["municipality_code"].nunique()),
    }


def build_recovery_audit(
    evidence: pd.DataFrame,
    endpoints: pd.DataFrame,
    proximity: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    for name, frame in {"evidence": evidence, "endpoints": endpoints, "proximity": proximity}.items():
        if frame["origin_id"].duplicated().any():
            raise ValueError(f"Duplicate origin_id in {name}")

    proximity_cols = [
        "origin_id", "latitude", "longitude", "distance_to_port_m", "nearest_geometry_signal"
    ]
    full = evidence.merge(
        proximity[proximity_cols], on="origin_id", how="left", validate="one_to_one"
    )
    full["routing_ready"] = full["origin_id"].isin(set(endpoints["origin_id"]))

    evidence_class = full["origin_access_evidence_class"].astype("string")
    full["recovery_class"] = "routing_ready_primary"
    missing = ~full["routing_ready"]
    full.loc[
        missing & evidence_class.eq("nearest_local_osm_node_in_primary_motor_graph"),
        "recovery_class",
    ] = "direct_upper_regime_requires_empirical_validation"
    full.loc[
        missing & evidence_class.eq("local_osm_topology_connects_to_primary_motor"),
        "recovery_class",
    ] = "local_osm_path_requires_modal_and_alignment_validation"
    full.loc[
        missing & evidence_class.eq("residual_hydro_priority_candidate"),
        "recovery_class",
    ] = "hydro_residual_requires_route_evidence"
    full.loc[
        missing & evidence_class.eq("residual_unresolved_network_gap"),
        "recovery_class",
    ] = "unresolved_network_gap_requires_route_evidence"
    if full.loc[missing, "recovery_class"].eq("routing_ready_primary").any():
        raise ValueError("Unclassified non-routing-ready origins remain")

    full["routing_ready_female_population"] = (
        pd.to_numeric(full["female_population"], errors="coerce").fillna(0)
        * full["routing_ready"].astype(int)
    )
    municipality = (
        full.groupby(["municipality_code", "municipality_name"], dropna=False)
        .agg(
            total_origins=("origin_id", "size"),
            routing_ready_origins=("routing_ready", "sum"),
            total_female_population=("female_population", "sum"),
            routing_ready_female_population=("routing_ready_female_population", "sum"),
        )
        .reset_index()
    )
    municipality["origin_coverage_fraction"] = (
        municipality["routing_ready_origins"] / municipality["total_origins"]
    )
    municipality["female_population_coverage_fraction"] = (
        municipality["routing_ready_female_population"]
        / municipality["total_female_population"]
    )
    municipality = municipality.sort_values(
        ["female_population_coverage_fraction", "municipality_name"]
    )

    excluded = full.loc[missing].copy()
    classes = {
        key: _summary(group) for key, group in excluded.groupby("recovery_class", sort=True)
    }
    afua = full.loc[full["municipality_name"].map(_ascii_key).eq("afua")].copy()
    afua_classes = {
        key: _summary(group) for key, group in afua.groupby("recovery_class", sort=True)
    }
    audit = {
        "status": "RECOVERY_EVIDENCE_AUDITED_PRIMARY_E2SFCA_STILL_GATED",
        "all_audited_origins": _summary(full),
        "routing_ready_origins": _summary(full.loc[full["routing_ready"]]),
        "non_routing_ready_origins": _summary(excluded),
        "non_routing_ready_recovery_classes": classes,
        "afua": {
            **_summary(afua),
            "routing_ready_origin_count": int(afua["routing_ready"].sum()),
            "recovery_classes": afua_classes,
        },
        "municipalities_below_50_percent_female_population_coverage": int(
            (municipality["female_population_coverage_fraction"] < 0.5).sum()
        ),
        "safeguards": {
            "unresolved_origins_reclassified_as_truly_unreachable": False,
            "nearest_network_snap_promoted": False,
            "euclidean_distance_converted_to_time": False,
            "osm_service_path_speed_assigned": False,
            "hydro_proximity_converted_to_route": False,
            "primary_e2sfca_publication_authorized": False,
        },
        "next_decision": (
            "Construct explicit sensitivity bounds for unresolved origin connectors, starting "
            "with municipalities below 50% female-population coverage; do not alter the frozen "
            "primary OD matrix until connector evidence and modal-time assumptions are separately documented."
        ),
    }
    return full, municipality, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--endpoints", type=Path, required=True)
    parser.add_argument("--proximity", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    evidence = pd.read_csv(args.evidence, dtype={"origin_id": "string"}, low_memory=False)
    endpoints = pd.read_csv(args.endpoints, dtype={"origin_id": "string"}, low_memory=False)
    proximity = pd.read_csv(args.proximity, dtype={"origin_id": "string"}, low_memory=False)
    full, municipality, audit = build_recovery_audit(evidence, endpoints, proximity)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    full.loc[~full["routing_ready"]].to_csv(
        args.output_dir / "non_routing_ready_origins_recovery_audit.csv.gz",
        index=False,
        compression="gzip",
    )
    municipality.to_csv(
        args.output_dir / "routing_population_coverage_by_municipality.csv", index=False
    )
    (args.output_dir / "origin_routing_coverage_recovery_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
