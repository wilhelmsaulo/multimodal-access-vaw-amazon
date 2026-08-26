import pandas as pd

from scripts.build_municipal_accessibility_analysis_table import build_analysis_table


def test_build_analysis_table_preserves_interval_endpoints() -> None:
    rows = []
    for municipality in range(144):
        code = str(municipality)
        name = f"Municipality {municipality}"
        for service in ("creas", "health"):
            rows.append(
                {
                    "municipality_code": code,
                    "municipality_name": name,
                    "female_population": 100.0,
                    "female_population_coverage_fraction": 0.8,
                    "service_type": service,
                    "scenario": "reference_network__t120__exponential",
                    "lower_sensitivity_envelope": 0.1,
                    "upper_sensitivity_envelope": 0.3,
                }
            )

    table, audit = build_analysis_table(pd.DataFrame(rows))

    assert len(table) == 144
    assert audit["accessibility_feature_count"] == 4
    assert audit["all_endpoints_paired"] is True
