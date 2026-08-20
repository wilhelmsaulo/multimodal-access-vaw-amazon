import pandas as pd

from scripts.materialize_routing_inputs import collapse_ready_destinations_to_physical_sites


def _row(service_id: str, service_type: str, lat: float, lon: float, name: str) -> dict:
    return {
        "service_id": service_id,
        "service_name": name,
        "service_type": service_type,
        "municipality_code": "1501402",
        "municipality_name": "Belém",
        "address_public": "Rua Teste, 100",
        "latitude": lat,
        "longitude": lon,
        "capacity": pd.NA,
        "capacity_type": pd.NA,
        "validation_status": "function_validated_from_official_source",
    }


def test_same_category_colocated_units_collapse_to_one_primary_site():
    services = pd.DataFrame([
        _row("J1", "specialized_justice", -1.45, -48.50, "1ª Vara"),
        _row("J2", "specialized_justice", -1.45, -48.50, "2ª Vara"),
    ])
    ready = services[[
        "service_id", "service_type", "municipality_code", "municipality_name",
        "latitude", "longitude", "capacity", "capacity_type", "validation_status",
    ]].copy()

    sites = collapse_ready_destinations_to_physical_sites(ready, services)

    assert len(sites) == 1
    assert sites.iloc[0]["administrative_unit_count"] == 2
    assert set(sites.iloc[0]["member_service_ids"].split("|")) == {"J1", "J2"}
    assert sites.iloc[0]["primary_supply_weight"] == 1.0


def test_cross_category_colocation_remains_separate():
    services = pd.DataFrame([
        _row("J1", "specialized_justice", -1.36, -48.38, "Vara VAW"),
        _row("D1", "specialized_security", -1.36, -48.38, "DEAM"),
    ])
    ready = services[[
        "service_id", "service_type", "municipality_code", "municipality_name",
        "latitude", "longitude", "capacity", "capacity_type", "validation_status",
    ]].copy()

    sites = collapse_ready_destinations_to_physical_sites(ready, services)

    assert len(sites) == 2
    assert sites["service_type"].nunique() == 2
    assert (sites["administrative_unit_count"] == 1).all()
