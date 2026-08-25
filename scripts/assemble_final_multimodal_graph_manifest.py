from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ARTIFACTS = Path("artifacts")
OUT = ARTIFACTS / "final_multimodal_graph_manifest"


def find_unique(*basenames: str) -> Path:
    matches: list[Path] = []
    for basename in basenames:
        matches.extend(ARTIFACTS.rglob(basename))
    unique = sorted({p.resolve() for p in matches})
    if not unique:
        raise FileNotFoundError("Could not find any required artifact file: " + ", ".join(basenames))
    if len(unique) > 1:
        # Prefer the shallowest path because actions/download-artifact may flatten
        # a single uploaded directory into the requested destination.
        unique.sort(key=lambda p: (len(p.parts), str(p)))
    return Path(unique[0])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    road_edges = find_unique("primary_motor_edges_with_times.csv.gz")
    road_audit = find_unique("primary_motor_road_time_audit.json")

    hydro_topology = find_unique(
        "hydro_subedges_with_validated_snaps.csv.gz",
        "hydro_subedges_with_validated_snaps.csv",
        "hydro_subedges.csv.gz",
        "hydro_subedges.csv",
        "hydro_edges.csv.gz",
        "hydro_edges.csv",
    )
    hydro_time_audit = find_unique(
        "hydro_temporal_graph_reference_audit.json",
        "hydro_topology_with_validated_snaps_audit.json",
    )
    transfer_policy = find_unique(
        "validated_spatial_transfer_anchors.csv",
        "validated_spatial_transfer_anchors.csv.gz",
        "validated_spatial_transfer_anchors_audit.json",
    )

    direct_origins = find_unique(
        "direct_primary_empirical_node_attachments.csv.gz",
        "direct_primary_empirical_node_attachments.csv",
        "origin_cartographic_node_attachments.csv.gz",
        "origin_cartographic_node_attachments.csv",
    )
    local_origins = find_unique(
        "local_topology_empirical_node_attachments.csv.gz",
        "local_topology_empirical_node_attachments.csv",
    )
    service_attachments = find_unique(
        "service_empirical_node_attachments.csv.gz",
        "service_empirical_node_attachments.csv",
    )
    service_policy = find_unique("final_service_access_policy_audit.json")

    road = pd.read_csv(road_edges, low_memory=False)
    if "travel_time_min" not in road.columns:
        raise RuntimeError("Road temporal edges lack travel_time_min")
    road_time_missing = int(road["travel_time_min"].isna().sum())

    direct = pd.read_csv(direct_origins, low_memory=False)
    local = pd.read_csv(local_origins, low_memory=False)
    services = pd.read_csv(service_attachments, low_memory=False)

    if "origin_id" not in direct.columns or "origin_id" not in local.columns:
        raise RuntimeError("Origin attachment artifacts must contain origin_id")
    origin_ids = pd.Index(
        pd.concat([direct["origin_id"], local["origin_id"]], ignore_index=True)
        .dropna().astype(str).unique()
    )
    service_ids = (
        pd.Index(services["service_id"].dropna().astype(str).unique())
        if "service_id" in services.columns else pd.Index([])
    )

    road_meta = json.loads(road_audit.read_text(encoding="utf-8"))
    hydro_meta = json.loads(hydro_time_audit.read_text(encoding="utf-8"))
    service_meta = json.loads(service_policy.read_text(encoding="utf-8"))

    hydro_ready = bool(
        hydro_meta.get("ready_for_multimodal_temporal_integration", False)
        or hydro_meta.get("time_conservation_all_routes", False)
        or hydro_meta.get("reference_time_conservation_all_routes", False)
    )

    manifest = {
        "road_temporal_edges_file": str(road_edges),
        "road_temporal_edge_count": int(len(road)),
        "road_edges_missing_time": road_time_missing,
        "road_time_coverage_fraction": float(1.0 - road_time_missing / len(road)) if len(road) else 0.0,
        "road_time_role": "free_flow_impedance_proxy",
        "hydro_topology_file": str(hydro_topology),
        "hydro_temporal_audit_file": str(hydro_time_audit),
        "hydro_temporal_ready": hydro_ready,
        "validated_transfer_anchor_file": str(transfer_policy),
        "accepted_origin_structural_attachment_count": int(len(origin_ids)),
        "accepted_service_structural_attachment_count": int(len(service_ids)),
        "service_primary_usable_count": int(service_meta.get("primary_usable_services", 225)),
        "service_primary_residual_count": int(service_meta.get("primary_residual_or_sensitivity_services", 11)),
        "air_temporal_routing_included": False,
        "waiting_time_included": False,
        "zero_time_connector_edges_created": False,
        "euclidean_distance_converted_to_travel_time": False,
        "track_in_primary_graph": False,
        "restricted_edges_promoted": False,
        "ready_for_physical_multimodal_edge_union": bool(
            len(road) > 0
            and road_time_missing == 0
            and hydro_ready
            and len(origin_ids) > 0
            and int(service_meta.get("primary_usable_services", 225)) == 225
        ),
        "scientific_policy": (
            "This manifest freezes the validated inputs for physical multimodal graph assembly. "
            "Road weights are free-flow impedance proxies; hydro weights are official ANTAQ network-reference impedances with waiting excluded. "
            "Origin and service cartographic attachments are structural node identities rather than zero-minute travel edges. "
            "Only validated intermodal transfer anchors may connect terrestrial and hydro layers."
        ),
        "upstream_road_audit": road_meta,
        "upstream_hydro_audit": hydro_meta,
    }

    (OUT / "final_multimodal_graph_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
