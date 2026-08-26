import pandas as pd

from scripts.audit_origin_routing_coverage_recovery import build_recovery_audit


def test_recovery_audit_does_not_promote_unresolved_connectors():
    evidence = pd.DataFrame(
        {
            "origin_id": ["ready", "direct", "local", "hydro", "gap"],
            "municipality_code": [1, 2, 2, 2, 2],
            "municipality_name": ["Other", "Afuá", "Afuá", "Afuá", "Afuá"],
            "female_population": [100, 40, 30, 20, 10],
            "origin_access_evidence_class": [
                "nearest_local_osm_node_in_primary_motor_graph",
                "nearest_local_osm_node_in_primary_motor_graph",
                "local_osm_topology_connects_to_primary_motor",
                "residual_hydro_priority_candidate",
                "residual_unresolved_network_gap",
            ],
        }
    )
    endpoints = pd.DataFrame({"origin_id": ["ready"]})
    proximity = pd.DataFrame(
        {
            "origin_id": evidence["origin_id"],
            "latitude": 0.0,
            "longitude": 0.0,
            "distance_to_port_m": 1.0,
            "nearest_geometry_signal": "road_closer_or_equal",
        }
    )

    full, municipality, audit = build_recovery_audit(evidence, endpoints, proximity)

    assert full["routing_ready"].sum() == 1
    assert audit["afua"]["routing_ready_origin_count"] == 0
    assert len(audit["non_routing_ready_recovery_classes"]) == 4
    assert audit["safeguards"]["nearest_network_snap_promoted"] is False
    assert audit["safeguards"]["primary_e2sfca_publication_authorized"] is False
    assert municipality.loc[
        municipality["municipality_name"].eq("Afuá"),
        "female_population_coverage_fraction",
    ].item() == 0
