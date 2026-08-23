from __future__ import annotations

import json
from pathlib import Path

SNAP = Path("artifacts/spatial_transfer_snap_rule/spatial_transfer_snap_rule_audit.json")
SENS = Path("artifacts/spatial_snap_sensitivity/spatial_snap_sensitivity_audit.json")
OUT = Path("artifacts/non_temporal_cartographic_snap_rule")


def load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    snap = load(SNAP)
    sens = load(SENS)

    spatial_ready = bool(
        snap.get("spatial_snap_rule_adopted") is True
        and snap.get("spatial_snap_eligible_count") == 3
        and snap.get("universal_distance_cutoff_used") is False
        and snap.get("snap_distance_interpreted_as_travel_distance") is False
        and sens.get("spatial_snap_sensitivity_complete") is True
        and sens.get("spatial_snap_rule_retained_after_sensitivity") is True
    )
    if not spatial_ready:
        raise RuntimeError("Spatial snap evidence is not complete enough to finalize temporal treatment")

    audit = {
        "validated_anchor_count": 3,
        "anchor_names": snap.get("anchor_names", []),
        "spatial_rule_prerequisites_satisfied": True,
        "connector_representation": "non_temporal_cartographic_topology_alignment",
        "connector_is_temporal_edge": False,
        "connector_travel_time_minutes": None,
        "zero_time_transfer_adopted": False,
        "snap_distance_interpreted_as_travel_distance": False,
        "distance_to_time_conversion_used": False,
        "waiting_time_included": False,
        "temporal_connector_impedance_resolved": True,
        "temporal_connector_rule": (
            "Validated port-to-hydro snaps are graph-topology alignment operations only and are not represented as temporal travel edges. "
            "They contribute no separately modeled movement impedance because the measured port-to-route offset is treated as cartographic representation mismatch rather than observed physical displacement. "
            "This is distinct from assigning a zero-minute transfer edge. Movement time is accumulated only on explicitly modeled terrestrial and hydro network segments. Waiting/departure frequency remains excluded and is reported as a limitation."
        ),
        "primary_route_time_definition": (
            "T_route = T_access_connector + T_navigation + T_transfer_connector + T_terrestrial, "
            "where cartographic topology-alignment snaps are structural graph operations rather than T_transfer_connector travel segments; "
            "only evidence-backed physical movement connectors contribute temporal impedance."
        ),
        "routing_enablement_recommended": True,
        "scientific_policy": (
            "Do not interpret a non-temporal snap as an instantaneous real-world transfer. It corrects topology between validated official representations. "
            "No snap distance is converted to time, no universal distance threshold is introduced, and no waiting/frequency penalty is imputed."
        ),
    }
    (OUT / "non_temporal_cartographic_snap_rule_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
