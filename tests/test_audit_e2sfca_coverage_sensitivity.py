import pandas as pd

from scripts.audit_e2sfca_coverage_sensitivity import audit_envelopes


def test_audit_keeps_parameter_stability_separate_from_coverage_uncertainty():
    rows = []
    for municipality in range(144):
        for scenario, multiplier in [("s1", 1.0), ("s2", 2.0)]:
            rows.append(
                {
                    "municipality_code": municipality,
                    "municipality_name": "Afuá" if municipality == 0 else f"M{municipality}",
                    "service_type": "health",
                    "scenario": scenario,
                    "female_population_coverage_fraction": 0.0 if municipality == 0 else 1.0,
                    "observed_population_weighted_mean": None if municipality == 0 else municipality * multiplier,
                    "lower_sensitivity_envelope": 0.0 if municipality == 0 else municipality * multiplier,
                    "upper_sensitivity_envelope": 10.0 * multiplier if municipality == 0 else municipality * multiplier,
                    "sensitivity_envelope_width": 10.0 * multiplier if municipality == 0 else 0.0,
                }
            )
    stability, audit = audit_envelopes(pd.DataFrame(rows))

    assert stability["spearman_min"].min() == 1.0
    assert audit["afua"]["relative_envelope_width_always_one"] is True
    assert audit["coverage_uncertainty_resolved"] is False
    assert audit["authorized_for_single_point_mcdm_or_som"] is False
