import pandas as pd
import pytest

from src.accessibility.coverage_uncertainty import municipal_accessibility_envelope


def test_partial_envelope_preserves_total_population_and_flags_limitations():
    origins = pd.DataFrame(
        {
            "origin_id": ["a", "b", "c"],
            "municipality_code": [1, 1, 2],
            "municipality_name": ["A", "A", "B"],
            "female_population": [100.0, 300.0, 200.0],
        }
    )
    scores = pd.DataFrame(
        {
            "origin_id": ["a", "c"],
            "service_type": ["health", "health"],
            "scenario": ["reference", "reference"],
            "e2sfca_score": [1.0, 4.0],
        }
    )

    out = municipal_accessibility_envelope(scores, origins)
    a = out.loc[out["municipality_name"].eq("A")].iloc[0]
    b = out.loc[out["municipality_name"].eq("B")].iloc[0]

    assert a["female_population_coverage_fraction"] == 0.25
    assert a["observed_population_weighted_mean"] == 1.0
    assert a["lower_sensitivity_envelope"] == 0.25
    assert a["upper_sensitivity_envelope"] == 3.25
    assert a["coverage_status"] == "partially_identified"
    assert b["lower_sensitivity_envelope"] == b["upper_sensitivity_envelope"] == 4.0
    assert bool(a["is_confidence_interval"]) is False
    assert bool(a["corrects_unknown_connector_competition"]) is False
    assert bool(a["authorized_as_final_e2sfca"]) is False


def test_envelope_rejects_negative_accessibility():
    origins = pd.DataFrame(
        {
            "origin_id": ["a"],
            "municipality_code": [1],
            "municipality_name": ["A"],
            "female_population": [100.0],
        }
    )
    scores = pd.DataFrame(
        {
            "origin_id": ["a"],
            "service_type": ["health"],
            "scenario": ["reference"],
            "e2sfca_score": [-1.0],
        }
    )
    with pytest.raises(ValueError, match="non-negative"):
        municipal_accessibility_envelope(scores, origins)
