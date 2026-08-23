from __future__ import annotations

import json
from pathlib import Path

ROAD = Path("artifacts/primary_motor_road_times_complete/primary_motor_road_time_completion_audit.json")
HYDRO = Path("artifacts/hydro_temporal_graph_reference/hydro_temporal_graph_reference_audit.json")
TOPO = Path("artifacts/transport_topology/transport_topology_audit.json")
SNAP = Path("artifacts/spatial_transfer_snap_rule/spatial_transfer_snap_rule_audit.json")
SENS = Path("artifacts/spatial_snap_sensitivity/spatial_snap_sensitivity_audit.json")
OUT = Path("artifacts/multimodal_temporal_integration_readiness")


def load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    road = load(ROAD)
    hydro = load(HYDRO)
    topo = load(TOPO)
    snap = load(SNAP)
    sens = load(SENS)

    terrestrial_ready = bool(
        road.get("terrestrial_temporal_graph_complete") is True
        and road.get("edge_time_coverage_fraction") == 1.0
    )
    hydro_ready = bool(
        hydro.get("ready_for_multimodal_temporal_integration") is True
        and hydro.get("coverage_fraction") == 1.0
    )

    connector_candidates = topo.get("connector_candidates", {})
    connector_status = {
        name: {
            "rows": int(info.get("rows", 0)),
            "resolved": int(info.get("resolved", 0)),
            "median_snap_distance_m": info.get("median_snap_distance_m"),
            "p95_snap_distance_m": info.get("p95_snap_distance_m"),
            "max_snap_distance_m": info.get("max_snap_distance_m"),
            "status": info.get("status"),
        }
        for name, info in connector_candidates.items()
    }

    spatial_rule_resolved = bool(
        snap.get("spatial_snap_rule_adopted") is True
        and snap.get("spatial_snap_eligible_count") == 3
        and snap.get("universal_distance_cutoff_used") is False
        and snap.get("snap_distance_interpreted_as_travel_distance") is False
        and sens.get("spatial_snap_sensitivity_complete") is True
        and sens.get("spatial_snap_rule_retained_after_sensitivity") is True
    )
    temporal_connector_resolved = bool(
        snap.get("temporal_connector_impedance_resolved") is True
        or sens.get("temporal_connector_impedance_resolved") is True
    )
    ready_final_od = bool(
        terrestrial_ready and hydro_ready and spatial_rule_resolved and temporal_connector_resolved
    )

    if not spatial_rule_resolved:
        blocking_issue = (
            "Intermodal spatial connector rule is not yet resolved by validated ANTAQ anchors, official crossing positive controls, and sensitivity audit."
        )
    elif not temporal_connector_resolved:
        blocking_issue = (
            "Spatial intermodal topology is scientifically resolved, but the temporal treatment of the cartographic snap remains unresolved. "
            "Snap distance must not be converted to travel time; waiting remains excluded."
        )
    else:
        blocking_issue = None

    audit = {
        "terrestrial_temporal_ready": terrestrial_ready,
        "terrestrial_edge_time_coverage_fraction": road.get("edge_time_coverage_fraction"),
        "hydro_temporal_ready": hydro_ready,
        "hydro_segment_time_coverage_fraction": hydro.get("coverage_fraction"),
        "hydro_time_source": hydro.get("time_source"),
        "waiting_time_included": False,
        "connector_candidates": connector_status,
        "validated_spatial_snap_anchor_count": int(snap.get("spatial_snap_eligible_count", 0)),
        "intermodal_spatial_connector_rule_resolved": spatial_rule_resolved,
        "spatial_snap_sensitivity_complete": bool(sens.get("spatial_snap_sensitivity_complete") is True),
        "intermodal_temporal_connector_rule_resolved": temporal_connector_resolved,
        "intermodal_connector_rule_resolved": bool(spatial_rule_resolved and temporal_connector_resolved),
        "ready_for_final_multimodal_od": ready_final_od,
        "universal_distance_cutoff_used": False,
        "snap_distance_interpreted_as_travel_distance": False,
        "distance_to_time_conversion_used": False,
        "blocking_issue": blocking_issue,
        "scientific_policy": (
            "Terrestrial and hydro temporal impedances must be complete. Spatial road-water alignment may only use individually validated ANTAQ port anchors supported by official route-endpoint provenance, reproducible canonical geometry, official crossing positive controls, and structural sensitivity. "
            "Cartographic snap distance is not a travel distance and is never converted to time. Final multimodal OD remains disabled until the temporal connector treatment is explicitly resolved; waiting time is excluded and reported as a limitation."
        ),
    }
    (OUT / "multimodal_temporal_integration_readiness_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
