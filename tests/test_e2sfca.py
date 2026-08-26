import numpy as np
import pandas as pd

from src.accessibility.e2sfca import e2sfca, exponential_decay
from src.accessibility.spatial_stats import global_moran, local_moran_lisa


def test_e2sfca_separates_service_types_and_scenarios():
    origins = pd.DataFrame(
        {"origin_id": ["s1", "s2"], "female_population": [100.0, 100.0]}
    )
    services = pd.DataFrame(
        {
            "service_id": ["h1", "c1"],
            "service_type": ["health", "reference_center"],
            "capacity": [10.0, 5.0],
        }
    )
    rows = []
    for scenario in ["flood_season", "dry_season"]:
        for origin in ["s1", "s2"]:
            for service, minutes in [("h1", 30), ("c1", 60)]:
                rows.append(
                    {
                        "origin_id": origin,
                        "service_id": service,
                        "scenario": scenario,
                        "travel_time_min": minutes,
                    }
                )
    travel = pd.DataFrame(rows)
    result = e2sfca(
        travel,
        origins,
        services,
        threshold_minutes=120,
        decay=exponential_decay(0.01),
    )
    assert set(result.sector_scores["service_type"]) == {"health", "reference_center"}
    assert set(result.sector_scores["scenario"]) == {"flood_season", "dry_season"}
    assert (result.sector_scores["e2sfca_score"] > 0).all()


def test_presence_model_creates_unit_supply_and_preserves_zero_access_origins():
    origins = pd.DataFrame(
        {"origin_id": ["near", "far"], "female_population": [100.0, 50.0]}
    )
    services = pd.DataFrame({"service_id": ["c1"], "service_type": ["creas"]})
    travel = pd.DataFrame(
        {
            "origin_id": ["near", "far"],
            "service_id": ["c1", "c1"],
            "scenario": ["reference_network", "reference_network"],
            "travel_time_min": [30.0, np.nan],
        }
    )
    result = e2sfca(travel, origins, services, supply_mode="unit_presence")
    assert result.service_ratios["capacity"].tolist() == [1.0]
    assert result.service_ratios["supply_mode"].tolist() == ["unit_presence"]
    scores = result.sector_scores.set_index("origin_id")["e2sfca_score"]
    assert scores["near"] > 0
    assert scores["far"] == 0
    assert len(scores) == len(origins)


def test_presence_model_does_not_silently_use_observed_capacity():
    origins = pd.DataFrame({"origin_id": ["o1"], "female_population": [100.0]})
    services = pd.DataFrame(
        {"service_id": ["s1"], "service_type": ["health"], "capacity": [999.0]}
    )
    travel = pd.DataFrame(
        {
            "origin_id": ["o1"],
            "service_id": ["s1"],
            "scenario": ["reference_network"],
            "travel_time_min": [10.0],
        }
    )
    result = e2sfca(travel, origins, services, supply_mode="unit_presence")
    assert result.service_ratios.loc[0, "capacity"] == 1.0


def test_moran_and_lisa_return_finite_statistics():
    values = pd.DataFrame({"id": ["1", "2", "3", "4"], "value": [1.0, 1.2, 4.0, 4.2]})
    edges = pd.DataFrame(
        {"source_id": ["1", "2", "3"], "target_id": ["2", "3", "4"]}
    )
    moran = global_moran(values, edges, id_col="id", value_col="value", permutations=99)
    assert np.isfinite(moran.moran_i)
    lisa = local_moran_lisa(values, edges, id_col="id", value_col="value", permutations=99)
    assert len(lisa) == 4
    assert "lisa_cluster" in lisa.columns
