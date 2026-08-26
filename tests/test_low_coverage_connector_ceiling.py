import pandas as pd

from scripts.audit_low_coverage_connector_ceiling import build_connector_ceiling_audit


def test_ceiling_is_screening_only_and_rejects_track_and_distant_paths():
    evidence = pd.DataFrame(
        {
            "origin_id": ["ready", "near", "track", "distant"],
            "municipality_code": [1, 1, 1, 1],
            "municipality_name": ["Afuá"] * 4,
            "female_population": [20, 30, 40, 10],
            "origin_access_evidence_class": [
                "nearest_local_osm_node_in_primary_motor_graph",
                "local_osm_topology_connects_to_primary_motor",
                "local_osm_topology_connects_to_primary_motor",
                "local_osm_topology_connects_to_primary_motor",
            ],
            "distance_to_nearest_osm_node_m": [0, 50, 50, 500],
        }
    )
    endpoints = pd.DataFrame({"origin_id": ["ready"]})
    paths = pd.DataFrame(
        {
            "origin_id": ["near", "track", "distant"],
            "path_highway_classes": ["service", "track", "footway"],
            "local_osm_path_distance_to_primary_motor_m": [100, 100, 100],
        }
    )

    municipality, audit = build_connector_ceiling_audit(evidence, endpoints, paths)

    assert audit["existing_evidence_sensitivity_candidate_origin_count"] == 1
    assert audit["existing_evidence_sensitivity_candidate_female_population"] == 30
    assert audit["safeguards"]["candidates_promoted_to_primary_routing"] is False
    assert municipality["existing_evidence_ceiling_coverage_fraction"].item() == 0.5
