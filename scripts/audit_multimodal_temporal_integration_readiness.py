from __future__ import annotations

import json
from pathlib import Path

ROAD = Path("artifacts/primary_motor_road_times_complete/primary_motor_road_time_completion_audit.json")
HYDRO = Path("artifacts/hydro_temporal_graph_reference/hydro_temporal_graph_reference_audit.json")
TOPO = Path("artifacts/transport_topology/topology_audit.json")
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
    all_connectors_promoted = bool(connector_status) and all(
        x.get("status") == "validated_promoted" for x in connector_status.values()
    )

    audit = {
        "terrestrial_temporal_ready": terrestrial_ready,
        "terrestrial_edge_time_coverage_fraction": road.get("edge_time_coverage_fraction"),
        "hydro_temporal_ready": hydro_ready,
        "hydro_segment_time_coverage_fraction": hydro.get("coverage_fraction"),
        "hydro_time_source": hydro.get("time_source"),
        "waiting_time_included": False,
        "connector_candidates": connector_status,
        "intermodal_connector_rule_resolved": all_connectors_promoted,
        "ready_for_final_multimodal_od": bool(terrestrial_ready and hydro_ready and all_connectors_promoted),
        "blocking_issue": None if all_connectors_promoted else "Intermodal connector candidates have not been scientifically validated/promoted; nearest geometry alone is not accepted as a connector rule.",
        "scientific_policy": "Final multimodal OD routing is prohibited until terrestrial and hydro temporal impedances are complete and intermodal connectors are validated by an explicit defensible rule. Extreme nearest-snap distances must not create artificial road-water transfers.",
    }
    (OUT / "multimodal_temporal_integration_readiness_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
