from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

from src.network.od_matrix import ready_destinations, ready_origins

DEFAULT_ORIGINS = Path("data/processed/ibge/pa_cnefe_sector_origins_2022.csv")
DEFAULT_SERVICES = Path("artifacts/service_inventory/services_readiness.csv")
DEFAULT_OUTPUT_DIR = Path("artifacts/routing_inputs")
SCENARIOS = ("flood_season", "dry_season")


def _norm(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower()).strip()
    return " ".join(text.split())


def _site_key(row: pd.Series) -> str:
    service_type = _norm(row.get("service_type"))
    lat = pd.to_numeric(pd.Series([row.get("latitude")]), errors="coerce").iloc[0]
    lon = pd.to_numeric(pd.Series([row.get("longitude")]), errors="coerce").iloc[0]
    if pd.notna(lat) and pd.notna(lon):
        locator = f"coord:{float(lat):.6f}:{float(lon):.6f}"
    else:
        municipality = _norm(row.get("municipality_name"))
        address = _norm(row.get("address_public"))
        if address:
            locator = f"address:{municipality}:{address}"
        else:
            locator = f"record:{_norm(row.get('service_id'))}"
    return f"{service_type}|{locator}"


def _site_id(site_key: str) -> str:
    digest = hashlib.sha1(site_key.encode("utf-8")).hexdigest()[:14]
    return f"SITE-{digest}"


def _physical_site_keys(services: pd.DataFrame) -> pd.Series:
    return services.apply(_site_key, axis=1).astype("string")


def collapse_ready_destinations_to_physical_sites(
    destinations: pd.DataFrame,
    services_all: pd.DataFrame,
) -> pd.DataFrame:
    """Collapse co-located administrative units within a service category.

    The primary spatial-access analysis treats one validated physical access site as
    one supply opportunity within each service category. Multiple administrative
    units at the same validated coordinates therefore remain documented but do not
    multiply primary supply. Cross-category co-location is intentionally retained,
    because categories are analysed separately and are not substitutes.
    """
    if destinations.empty:
        return destinations.copy()

    metadata_cols = [
        "service_id",
        "service_name",
        "service_type",
        "municipality_code",
        "municipality_name",
        "address_public",
        "latitude",
        "longitude",
        "capacity",
        "capacity_type",
        "validation_status",
    ]
    available = [c for c in metadata_cols if c in services_all.columns]
    metadata = services_all[available].drop_duplicates(subset=["service_id"]).copy()
    d = destinations.merge(
        metadata.drop(columns=[c for c in ["service_type", "municipality_code", "municipality_name", "latitude", "longitude", "capacity", "capacity_type", "validation_status"] if c in metadata.columns]),
        on="service_id",
        how="left",
    )
    d["physical_site_key"] = _physical_site_keys(d)
    d["physical_site_id"] = d["physical_site_key"].map(_site_id)

    rows: list[dict] = []
    for (_, _), group in d.groupby(["service_type", "physical_site_id"], dropna=False, sort=False):
        first = group.iloc[0]
        member_ids = sorted(group["service_id"].astype(str).tolist())
        names = sorted(set(group.get("service_name", pd.Series(dtype="string")).dropna().astype(str).tolist()))
        count = len(member_ids)
        capacity = first.get("capacity") if count == 1 else pd.NA
        capacity_type = first.get("capacity_type") if count == 1 else "not_used_primary_colocated_units"
        rows.append({
            "service_id": first["physical_site_id"],
            "physical_site_id": first["physical_site_id"],
            "service_type": first["service_type"],
            "municipality_code": first.get("municipality_code"),
            "municipality_name": first.get("municipality_name"),
            "latitude": first["latitude"],
            "longitude": first["longitude"],
            "capacity": capacity,
            "capacity_type": capacity_type,
            "validation_status": first.get("validation_status"),
            "address_public": first.get("address_public"),
            "administrative_unit_count": int(count),
            "member_service_ids": "|".join(member_ids),
            "member_service_names": " | ".join(names),
            "primary_supply_weight": 1.0,
            "primary_supply_assumption": "one_validated_physical_site_equals_one_supply_opportunity_within_service_type",
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize validated origin and destination inputs for multimodal routing.")
    parser.add_argument("--origins", type=Path, default=DEFAULT_ORIGINS)
    parser.add_argument("--services", type=Path, default=DEFAULT_SERVICES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    origins_all = pd.read_csv(args.origins, dtype={"origin_id": "string", "municipality_code": "string"}, low_memory=False)
    services_all = pd.read_csv(args.services, dtype={"service_id": "string", "municipality_code": "string"}, low_memory=False)
    origins = ready_origins(origins_all)
    ready_units = ready_destinations(services_all, require_capacity=False)
    destinations = collapse_ready_destinations_to_physical_sites(ready_units, services_all)
    if origins.empty or destinations.empty:
        raise ValueError("Routing inputs cannot be empty")
    if origins["origin_id"].duplicated().any() or destinations["service_id"].duplicated().any():
        raise ValueError("Routing IDs must be unique")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    origins.to_csv(args.output_dir / "origins_for_routing.csv", index=False)
    destinations.to_csv(args.output_dir / "destinations_for_routing.csv", index=False)

    all_with_sites = services_all.copy()
    all_with_sites["physical_site_key"] = _physical_site_keys(all_with_sites)
    all_with_sites["physical_site_id"] = all_with_sites["physical_site_key"].map(_site_id)
    admin_total_by_type = services_all.groupby("service_type", dropna=False)["service_id"].nunique()
    site_total_by_type = all_with_sites.groupby("service_type", dropna=False)["physical_site_id"].nunique()
    ready_admin_by_type = ready_units.groupby("service_type", dropna=False)["service_id"].nunique()
    ready_site_by_type = destinations.groupby("service_type", dropna=False)["physical_site_id"].nunique()

    colocation = (
        all_with_sites.groupby(["service_type", "physical_site_id"], dropna=False)
        .agg(
            administrative_unit_count=("service_id", "nunique"),
            member_service_ids=("service_id", lambda s: "|".join(sorted(s.astype(str).unique()))),
            municipality_name=("municipality_name", "first"),
            address_public=("address_public", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
        )
        .reset_index()
    )
    colocation.to_csv(args.output_dir / "physical_site_colocation_audit.csv", index=False)

    coverage_rows = []
    pair_rows = []
    for service_type, total_sites in site_total_by_type.items():
        ready_sites = int(ready_site_by_type.get(service_type, 0))
        unresolved_sites = int(total_sites) - ready_sites
        coverage_rows.append({
            "service_type": service_type,
            "administrative_units_total": int(admin_total_by_type.get(service_type, 0)),
            "administrative_units_ready": int(ready_admin_by_type.get(service_type, 0)),
            "physical_sites_total": int(total_sites),
            "physical_sites_ready": ready_sites,
            "physical_sites_unresolved_location": unresolved_sites,
            "location_coverage_fraction": ready_sites / int(total_sites) if int(total_sites) else 0.0,
            "inventory_complete_for_primary_analysis": unresolved_sites == 0,
        })
        for scenario in SCENARIOS:
            pair_rows.append({
                "service_type": service_type,
                "scenario": scenario,
                "origins_ready": int(len(origins)),
                "destinations_ready_physical_sites": ready_sites,
                "candidate_pairs": int(len(origins) * ready_sites),
                "travel_time_status": "not_yet_solved_by_multimodal_router",
            })
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(args.output_dir / "destination_coverage_by_type.csv", index=False)
    pd.DataFrame(pair_rows).to_csv(args.output_dir / "od_candidate_manifest.csv", index=False)

    female = pd.to_numeric(origins["female_population"], errors="coerce")
    all_female = pd.to_numeric(origins_all["female_population"], errors="coerce")
    all_lat = pd.to_numeric(origins_all["latitude"], errors="coerce")
    all_lon = pd.to_numeric(origins_all["longitude"], errors="coerce")
    unresolved_origin = all_female.notna() & (all_lat.isna() | all_lon.isna())
    colocated_groups = colocation.loc[colocation["administrative_unit_count"] > 1]
    audit = {
        "origins_total": int(len(origins_all)),
        "origins_ready": int(len(origins)),
        "origins_excluded_missing_female_population": int(all_female.isna().sum()),
        "origins_excluded_missing_location_with_observed_female_population": int(unresolved_origin.sum()),
        "female_population_ready": float(female.sum()),
        "female_population_observed_but_unresolved_location": float(all_female[unresolved_origin].sum()),
        "administrative_service_records_total": int(len(services_all)),
        "administrative_service_records_ready": int(len(ready_units)),
        "physical_service_sites_total": int(all_with_sites["physical_site_id"].nunique()),
        "physical_service_sites_ready": int(len(destinations)),
        "colocated_same_category_site_groups": int(len(colocated_groups)),
        "administrative_records_in_colocated_groups": int(colocated_groups["administrative_unit_count"].sum()) if len(colocated_groups) else 0,
        "destinations_by_service_type": {str(k): int(v) for k, v in ready_site_by_type.to_dict().items()},
        "incomplete_service_types_for_primary_analysis": coverage.loc[~coverage["inventory_complete_for_primary_analysis"], "service_type"].astype(str).tolist(),
        "scenarios": list(SCENARIOS),
        "candidate_pairs_per_scenario": int(len(origins) * len(destinations)),
        "candidate_pairs_all_scenarios": int(len(origins) * len(destinations) * len(SCENARIOS)),
        "pair_materialization_policy": "Full Cartesian pairs are not written yet; routing should solve pairs in chunks by service type and scenario.",
        "travel_time_policy": "No straight-line or assumed-speed travel time is created here.",
        "primary_supply_rule": "one_validated_physical_site_equals_one_supply_opportunity_within_service_type",
        "colocation_policy": "Administrative units sharing one physical site within the same service type do not multiply primary supply; their count and IDs are retained as metadata.",
        "cross_category_colocation_policy": "The same physical address may remain once in each distinct service type because categories are analysed separately and are not substitutes.",
        "analysis_gate": "A service type is not treated as a complete primary layer while known physical service sites still lack defensible coordinates.",
    }
    (args.output_dir / "routing_inputs_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
