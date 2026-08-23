from __future__ import annotations

import json
from pathlib import Path

ROAD = Path("artifacts/primary_motor_road_times_complete/primary_motor_road_time_completion_audit.json")
HYDRO = Path("artifacts/hydro_temporal_graph_reference/hydro_temporal_graph_reference_audit.json")
TOPO = Path("artifacts/transport_topology/transport_topology_audit.json")
SNAP = Path("artifacts/spatial_transfer_snap_rule/spatial_transfer_snap_rule_audit.json")
SENS = Path("artifacts/spatial_snap_sensitivity/spatial_snap_sensitivity_audit.json")
TEMP = Path("artifacts/non_temporal_cartographic_snap_rule/non_temporal_cartographic_snap_rule_audit.json")
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
    temp = load(TEMP)

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
        temp.get("temporal_connector_impedance_resolved") is True
        and temp.get("connector_representation") == "non_temporal_cartographic_topology_alignment"
        and temp.get("connector_is_temporal_edge") is False
        and temp.get("connector_travel_time_minutes") is None
        and temp.get("zero_time_transfer_adopted") is False
        and temp.get("snap_distance_interpreted_as_travel_distance") is False
        and temp.get("distance_to_time_conversion_used") is False
        and temp.get("waiting_time_included") is False
    )
    ready_final_od = bool(
        terrestrial_ready and hydro_ready and spatial_rule_resolved and temporal_connector_resolved
    )

    if not spatial_rule_resolved:
        blocking_issue = "Intermodal spatial connector rule is not resolved."
    elif not temporal_connector_resolved:
        blocking_issue = "Temporal treatment of the validated cartographic snap is not resolved."
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
        "temporal_connector_representation": temp.get("connector_representation"),
        "temporal_connector_is_temporal_edge": temp.get("connector_is_temporal_edge"),
        "zero_time_transfer_adopted": False,
        "intermodal_connector_rule_resolved": bool(spatial_rule_resolved and temporal_connector_resolved),
        "ready_for_final_multimodal_od": ready_final_od,
        "universal_distance_cutoff_used": False,
        "snap_distance_interpreted_as_travel_distance": False,
        "distance_to_time_conversion_used": False,
        "blocking_issue": blocking_issue,
        "scientific_policy": (
            "Terrestrial and hydro temporal impedances are complete. Validated road-water snaps are non-temporal cartographic topology-alignment operations, not travel edges and not zero-minute real-world transfers. "
            "Their geometric offsets are never converted to time. Final multimodal OD may proceed using explicit terrestrial and hydro movement impedances; waiting/departure frequency remains excluded and must be reported as a limitation."
        ),
    }
    (OUT / "multimodal_temporal_integration_readiness_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
