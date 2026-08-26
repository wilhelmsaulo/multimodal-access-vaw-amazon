import pandas as pd

from scripts.geocode_service_locations import build_audit, geocode_queue


def test_empty_geocoding_queue_preserves_schema_and_builds_zero_audit() -> None:
    queue = pd.DataFrame(columns=["service_id", "address_public", "municipality_name"])

    result = geocode_queue(queue)
    audit = build_audit(result)

    assert result.empty
    assert "latitude_candidate" in result.columns
    assert "candidate_accepted_for_manual_validation" in result.columns
    assert audit["rows_queue"] == 0
    assert audit["rows_with_public_address"] == 0
    assert audit["rows_with_candidate_coordinates"] == 0
    assert audit["rows_accepted_for_manual_validation"] == 0
    assert audit["quality_counts"] == {}
    assert audit["query_strategy_counts"] == {}
