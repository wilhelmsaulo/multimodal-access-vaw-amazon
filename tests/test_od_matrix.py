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

    # Capacity remains available for category-specific sensitivity analyses only.
    assert len(ready_destinations(services, require_capacity=True)) == 1
    sensitivity_pairs = build_candidate_pairs(
        origins, ready_destinations(services, require_capacity=True)
    )
    assert len(sensitivity_pairs) == 4  # 2 origins x 1 capacity-observed service x 2 seasons

    # Primary accessibility uses one validated physical unit = one opportunity (S_j = 1),
    # so both services are eligible even when harmonized capacity is unavailable.
    primary_pairs = build_candidate_pairs(
        origins, ready_destinations(services, require_capacity=False)
    )
    assert len(primary_pairs) == 8  # 2 origins x 2 services x 2 seasons
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
