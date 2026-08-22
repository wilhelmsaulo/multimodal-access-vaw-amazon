from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED_OVERRIDE_COLUMNS = {
    "service_id",
    "latitude_override",
    "longitude_override",
    "coordinate_source",
    "adoption_status",
    "adoption_date",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply explicitly accepted manual coordinates to otherwise unresolved services."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("artifacts/service_inventory/services_consolidated.csv"),
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=Path("data/candidates/manual_service_coordinate_overrides_2026-08-21.csv"),
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("artifacts/service_inventory/manual_coordinate_overrides_audit.json"),
    )
    args = parser.parse_args()

    inventory = pd.read_csv(args.inventory)
    overrides = pd.read_csv(args.overrides)

    missing_columns = REQUIRED_OVERRIDE_COLUMNS - set(overrides.columns)
    if missing_columns:
        raise ValueError(f"Override file missing required columns: {sorted(missing_columns)}")
    if overrides["service_id"].duplicated().any():
        duplicate_ids = overrides.loc[overrides["service_id"].duplicated(), "service_id"].tolist()
        raise ValueError(f"Duplicate service_id values in override file: {duplicate_ids}")

    inventory_ids = set(inventory["service_id"].astype(str))
    override_ids = set(overrides["service_id"].astype(str))
    unknown_ids = sorted(override_ids - inventory_ids)
    if unknown_ids:
        raise ValueError(f"Override service_id values not present in inventory: {unknown_ids}")

    lat = pd.to_numeric(overrides["latitude_override"], errors="coerce")
    lon = pd.to_numeric(overrides["longitude_override"], errors="coerce")
    invalid = lat.isna() | lon.isna() | ~lat.between(-90, 90) | ~lon.between(-180, 180)
    if invalid.any():
        bad = overrides.loc[invalid, "service_id"].tolist()
        raise ValueError(f"Invalid coordinate overrides: {bad}")

    indexed = inventory.set_index("service_id", drop=False)
    overwritten_existing = []
    applied = []

    for row in overrides.itertuples(index=False):
        service_id = str(row.service_id)
        current_lat = indexed.at[service_id, "latitude"]
        current_lon = indexed.at[service_id, "longitude"]
        if pd.notna(current_lat) or pd.notna(current_lon):
            overwritten_existing.append(service_id)

        indexed.at[service_id, "latitude"] = float(row.latitude_override)
        indexed.at[service_id, "longitude"] = float(row.longitude_override)

        current_status = indexed.at[service_id, "validation_status"]
        marker = "manual_operational_coordinates_accepted_2026-08-21"
        if pd.isna(current_status) or str(current_status).strip() == "":
            indexed.at[service_id, "validation_status"] = marker
        elif marker not in str(current_status):
            indexed.at[service_id, "validation_status"] = f"{current_status}|{marker}"
        applied.append(service_id)

    updated = indexed.reset_index(drop=True)
    args.inventory.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(args.inventory, index=False)

    audit = {
        "override_file": str(args.overrides),
        "rows_in_override_file": int(len(overrides)),
        "rows_applied": int(len(applied)),
        "service_ids_applied": applied,
        "preexisting_coordinates_overwritten": overwritten_existing,
        "coordinate_source_values": sorted(overrides["coordinate_source"].dropna().astype(str).unique().tolist()),
        "adoption_status_values": sorted(overrides["adoption_status"].dropna().astype(str).unique().tolist()),
        "adoption_dates": sorted(overrides["adoption_date"].dropna().astype(str).unique().tolist()),
        "policy_note": (
            "Coordinates are operational locations explicitly accepted for routing by project decision. "
            "They remain traceable as manual overrides and can be replaced by stronger evidence later."
        ),
    }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
