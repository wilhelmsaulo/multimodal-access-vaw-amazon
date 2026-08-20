from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.network.od_matrix import ready_destinations, ready_origins

DEFAULT_ORIGINS = Path("data/processed/ibge/pa_cnefe_sector_origins_2022.csv")
DEFAULT_SERVICES = Path("artifacts/service_inventory/services_readiness.csv")
DEFAULT_OUTPUT_DIR = Path("artifacts/routing_inputs")
SCENARIOS = ("flood_season", "dry_season")


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize validated origin and destination inputs for multimodal routing.")
    parser.add_argument("--origins", type=Path, default=DEFAULT_ORIGINS)
    parser.add_argument("--services", type=Path, default=DEFAULT_SERVICES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    origins_all = pd.read_csv(args.origins, dtype={"origin_id": "string", "municipality_code": "string"}, low_memory=False)
    services_all = pd.read_csv(args.services, dtype={"service_id": "string", "municipality_code": "string"}, low_memory=False)

    origins = ready_origins(origins_all)
    destinations = ready_destinations(services_all, require_capacity=False)
    if origins.empty or destinations.empty:
        raise ValueError("Routing inputs cannot be empty")
    if origins["origin_id"].duplicated().any() or destinations["service_id"].duplicated().any():
        raise ValueError("Routing IDs must be unique")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    origins.to_csv(args.output_dir / "origins_for_routing.csv", index=False)
    destinations.to_csv(args.output_dir / "destinations_for_routing.csv", index=False)

    rows = []
    by_type = destinations.groupby("service_type", dropna=False)["service_id"].nunique()
    for service_type, n_dest in by_type.items():
        for scenario in SCENARIOS:
            rows.append({
                "service_type": service_type,
                "scenario": scenario,
                "origins_ready": int(len(origins)),
                "destinations_ready": int(n_dest),
                "candidate_pairs": int(len(origins) * int(n_dest)),
                "travel_time_status": "not_yet_solved_by_multimodal_router",
            })
    pd.DataFrame(rows).to_csv(args.output_dir / "od_candidate_manifest.csv", index=False)

    female = pd.to_numeric(origins["female_population"], errors="coerce")
    all_female = pd.to_numeric(origins_all["female_population"], errors="coerce")
    all_lat = pd.to_numeric(origins_all["latitude"], errors="coerce")
    all_lon = pd.to_numeric(origins_all["longitude"], errors="coerce")
    audit = {
        "origins_total": int(len(origins_all)),
        "origins_ready": int(len(origins)),
        "origins_excluded_missing_female_population": int(all_female.isna().sum()),
        "origins_excluded_missing_location_with_observed_female_population": int((all_female.notna() & (all_lat.isna() | all_lon.isna())).sum()),
        "female_population_ready": float(female.sum()),
        "destinations_total": int(len(services_all)),
        "destinations_ready": int(len(destinations)),
        "destinations_by_service_type": {str(k): int(v) for k, v in destinations["service_type"].astype("string").value_counts(dropna=False).to_dict().items()},
        "scenarios": list(SCENARIOS),
        "candidate_pairs_per_scenario": int(len(origins) * len(destinations)),
        "candidate_pairs_all_scenarios": int(len(origins) * len(destinations) * len(SCENARIOS)),
        "pair_materialization_policy": "Full Cartesian pairs are not written yet; routing should solve pairs in chunks by service type and scenario.",
        "travel_time_policy": "No straight-line or assumed-speed travel time is created here.",
        "primary_supply_rule": "one_validated_service_unit_equals_one_supply_opportunity_within_service_type",
    }
    (args.output_dir / "routing_inputs_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
