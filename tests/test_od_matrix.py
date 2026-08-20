import pandas as pd
import pytest

from src.network.od_matrix import (
    audit_od_inputs,
    build_candidate_pairs,
    ready_destinations,
    ready_origins,
)


def _origins():
    return pd.DataFrame(
        {
            "origin_id": ["s1", "s2"],
            "municipality_code": ["1501402", "1505106"],
            "municipality_name": ["Belém", "Óbidos"],
            "female_population": [100.0, 50.0],
            "latitude": [-1.45, -1.90],
            "longitude": [-48.49, -55.52],
            "origin_method": ["urban representative point", "official locality"],
            "origin_validation_status": ["urban_representative_point", "official_locality"],
        }
    )


def _services():
    return pd.DataFrame(
        {
            "service_id": ["CNES-1", "TJPA-1"],
            "service_type": ["health", "specialized_justice"],
            "municipality_code": ["1501402", "1506807"],
            "municipality_name": ["Belém", "Santarém"],
            "latitude": [-1.46, -2.44],
            "longitude": [-48.50, -54.71],
            "capacity": [20.0, pd.NA],
            "capacity_type": ["registered_beds", pd.NA],
            "validation_status": ["validated", "official_directory_validated"],
        }
    )


def test_ready_and_candidate_pairs():
    origins = _origins()
    services = _services()
    assert len(ready_origins(origins)) == 2
    assert len(ready_destinations(services, require_capacity=False)) == 2

    assert len(ready_destinations(services, require_capacity=True)) == 1
    sensitivity_pairs = build_candidate_pairs(origins, ready_destinations(services, require_capacity=True))
    assert len(sensitivity_pairs) == 4

    primary_pairs = build_candidate_pairs(origins, ready_destinations(services, require_capacity=False))
    assert len(primary_pairs) == 8
    assert primary_pairs["travel_time_min"].isna().all()

    audit = audit_od_inputs(origins, services)
    assert audit.destinations_ready_e2sfca == 2
    assert audit.candidate_pairs_e2sfca == 8


def test_unvalidated_rural_centroid_is_rejected():
    origins = _origins().iloc[[0]].copy()
    origins["origin_method"] = "rural centroid"
    origins["origin_validation_status"] = "unvalidated"
    with pytest.raises(ValueError, match="rural centroids"):
        ready_origins(origins)


def test_missing_female_population_is_not_analytically_ready():
    origins = _origins()
    origins.loc[1, "female_population"] = pd.NA
    ready = ready_origins(origins)
    assert ready["origin_id"].tolist() == ["s1"]


def test_accepted_cnefe_level3_fallback_is_ready_when_demand_observed():
    origins = _origins().iloc[[0]].copy()
    origins["origin_id"] = "fallback-sector"
    origins["origin_method"] = "cnefe_level3_estimated_address_fallback"
    origins["origin_validation_status"] = "accepted_estimated_address_fallback"
    ready = ready_origins(origins)
    assert ready["origin_id"].tolist() == ["fallback-sector"]
