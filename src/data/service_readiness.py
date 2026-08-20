from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ServiceReadinessAudit:
    total_services: int
    ready_for_routing: int
    ready_for_e2sfca_primary: int
    missing_coordinates: int
    missing_capacity: int
    needs_function_validation: int


def audit_service_readiness(inventory: pd.DataFrame) -> tuple[pd.DataFrame, ServiceReadinessAudit]:
    required = {
        "service_id", "service_name", "service_type", "provider_source",
        "municipality_name", "address_public", "latitude", "longitude",
        "capacity", "capacity_type", "validation_status",
    }
    missing = required.difference(inventory.columns)
    if missing:
        raise ValueError(f"Service inventory missing readiness columns: {sorted(missing)}")

    out = inventory.copy()
    lat = pd.to_numeric(out["latitude"], errors="coerce")
    lon = pd.to_numeric(out["longitude"], errors="coerce")
    capacity = pd.to_numeric(out["capacity"], errors="coerce")
    valid_coords = lat.between(-90, 90) & lon.between(-180, 180)

    status = out["validation_status"].astype("string").fillna("")
    # Only function-related uncertainty blocks functional readiness. Generic
    # location/routing qualifiers (for example, CREAS "requires_routing_validation")
    # must not be misclassified as missing functional validation.
    needs_validation = status.str.contains(
        r"candidate|needs[_ -]?function|requires[_ -]?function|pending[_ -]?function|screened_unresolved",
        case=False, regex=True, na=False,
    )
    explicitly_excluded = status.str.contains(
        r"excluded|not_primary|invalid|rejected",
        case=False, regex=True, na=False,
    )

    out["has_valid_coordinates"] = valid_coords
    out["has_observed_or_documented_capacity"] = capacity.notna() & (capacity >= 0)
    out["needs_function_validation"] = needs_validation
    out["is_functionally_excluded"] = explicitly_excluded
    out["ready_for_routing"] = valid_coords & ~needs_validation & ~explicitly_excluded

    out["primary_supply_weight"] = 1.0
    out["primary_supply_assumption"] = "one_validated_service_unit_equals_one_supply_opportunity"
    out["ready_for_e2sfca_primary"] = out["ready_for_routing"]

    def blocker(row: pd.Series) -> str:
        reasons: list[str] = []
        if not bool(row["has_valid_coordinates"]):
            reasons.append("coordinates")
        if bool(row["needs_function_validation"]):
            reasons.append("function_validation")
        if bool(row["is_functionally_excluded"]):
            reasons.append("function_excluded")
        return ";".join(reasons) if reasons else "none"

    out["readiness_blockers"] = out.apply(blocker, axis=1)
    audit = ServiceReadinessAudit(
        total_services=int(len(out)),
        ready_for_routing=int(out["ready_for_routing"].sum()),
        ready_for_e2sfca_primary=int(out["ready_for_e2sfca_primary"].sum()),
        missing_coordinates=int((~out["has_valid_coordinates"]).sum()),
        missing_capacity=int((~out["has_observed_or_documented_capacity"]).sum()),
        needs_function_validation=int(out["needs_function_validation"].sum()),
    )
    return out, audit


def build_geocoding_queue(readiness: pd.DataFrame) -> pd.DataFrame:
    """Return every unresolved service location without inventing approximate coordinates."""
    required = {"service_id", "service_name", "municipality_name", "address_public", "has_valid_coordinates"}
    missing = required.difference(readiness.columns)
    if missing:
        raise ValueError(f"Readiness table missing columns: {sorted(missing)}")
    queue = readiness.loc[
        ~readiness["has_valid_coordinates"] & ~readiness.get("is_functionally_excluded", False),
        ["service_id", "service_name", "service_type", "provider_source", "municipality_name", "address_public"],
    ].copy()
    has_address = queue["address_public"].astype("string").str.strip().notna()
    queue["geocoding_status"] = has_address.map(
        {True: "pending_coordinate_validation", False: "needs_official_address_resolution"}
    )
    queue["latitude_candidate"] = pd.NA
    queue["longitude_candidate"] = pd.NA
    queue["geocoding_source"] = pd.NA
    queue["geocoding_quality"] = pd.NA
    return queue
