from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def main() -> None:
    local = pd.read_csv(
        "artifacts/service_local_access_primary_motor_audit/service_local_access_to_primary_motor.csv.gz",
        low_memory=False,
    )
    direct = pd.read_csv(
        "artifacts/service_direct_primary_distance_regimes/service_direct_primary_distance_regimes.csv.gz",
        low_memory=False,
    )
    attachments = pd.read_csv(
        "artifacts/service_empirical_node_attachments/service_empirical_node_attachments.csv.gz",
        low_memory=False,
    )
    ped = pd.read_csv(
        "artifacts/service_pedestrian_local_access_times/service_pedestrian_local_access_times.csv.gz",
        low_memory=False,
    )
    restricted = pd.read_csv(
        "artifacts/nonprimary_motorlike_exclusion_reasons/service_motorlike_exclusion_reasons.csv.gz",
        low_memory=False,
    )
    modal = pd.read_csv(
        "artifacts/service_local_path_modal_composition/service_local_path_modal_composition.csv.gz",
        low_memory=False,
    )

    if len(local) != 236:
        raise RuntimeError(f"Expected 236 physical service opportunities, found {len(local)}")
    if len(direct) != 227:
        raise RuntimeError(f"Expected 227 direct-primary services, found {len(direct)}")
    if len(attachments) != 220:
        raise RuntimeError(f"Expected 220 empirical direct-primary attachments, found {len(attachments)}")
    if len(ped) != 5:
        raise RuntimeError(f"Expected 5 validated pedestrian service paths, found {len(ped)}")
    if len(restricted) != 2:
        raise RuntimeError(f"Expected 2 restricted motor-like service paths, found {len(restricted)}")

    attachment_ids = set(attachments["service_id"])
    ped_ids = set(ped["service_id"])
    restricted_ids = set(restricted["service_id"])
    direct_nonlocal_ids = set(direct.loc[~direct["empirical_local_service_regime"], "service_id"])

    modal_map = modal.set_index("service_id")["service_local_path_evidence_class"].to_dict()
    ped_time = ped.set_index("service_id")["pedestrian_access_time_min"].to_dict()

    rows = []
    for r in local.itertuples(index=False):
        sid = r.service_id
        if sid in attachment_ids:
            cls = "resolved_structural_direct_primary_identity"
            usable = True
            access_time = 0.0
            temporal_role = "non_temporal_structural_identity"
        elif sid in ped_ids:
            cls = "resolved_physical_osm_pedestrian_path"
            usable = True
            access_time = float(ped_time[sid])
            temporal_role = "physical_pedestrian_access_time"
        elif sid in direct_nonlocal_ids:
            cls = "unresolved_direct_primary_nonlocal_regime"
            usable = False
            access_time = None
            temporal_role = "none"
        elif sid in restricted_ids:
            cls = "excluded_explicit_access_or_motor_vehicle_restriction"
            usable = False
            access_time = None
            temporal_role = "none"
        elif modal_map.get(sid) == "track_involved_sensitivity_only":
            cls = "sensitivity_only_track_involved_path"
            usable = False
            access_time = None
            temporal_role = "none"
        elif not bool(r.local_osm_topologically_connected_to_primary_motor):
            cls = "unresolved_disconnected_local_osm_topology"
            usable = False
            access_time = None
            temporal_role = "none"
        else:
            raise RuntimeError(f"Unclassified service residual: {sid}")

        rows.append({
            "service_id": sid,
            "physical_site_id": r.physical_site_id,
            "service_type": r.service_type,
            "municipality_code": r.municipality_code,
            "municipality_name": r.municipality_name,
            "address_public": r.address_public,
            "validation_status": r.validation_status,
            "service_access_policy_class": cls,
            "primary_analysis_usable": usable,
            "access_time_min": access_time,
            "temporal_role": temporal_role,
            "creates_zero_time_edge": False,
            "distance_used_as_travel_length": False,
        })

    out = pd.DataFrame(rows)
    counts = {str(k): int(v) for k, v in out["service_access_policy_class"].value_counts().to_dict().items()}
    expected = {
        "resolved_structural_direct_primary_identity": 220,
        "resolved_physical_osm_pedestrian_path": 5,
        "unresolved_direct_primary_nonlocal_regime": 7,
        "excluded_explicit_access_or_motor_vehicle_restriction": 2,
        "sensitivity_only_track_involved_path": 1,
        "unresolved_disconnected_local_osm_topology": 1,
    }
    if counts != expected:
        raise RuntimeError(f"Unexpected final service partition: {counts}")

    outdir = Path("artifacts/final_service_access_policy")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "final_service_access_policy.csv.gz", index=False, compression="gzip")

    audit = {
        "physical_service_opportunities": int(len(out)),
        "primary_analysis_usable_services": int(out["primary_analysis_usable"].sum()),
        "primary_analysis_unusable_or_sensitivity_services": int((~out["primary_analysis_usable"]).sum()),
        "policy_class_counts": counts,
        "structural_direct_primary_attachments": 220,
        "physical_pedestrian_access_paths": 5,
        "residual_or_excluded_services": 11,
        "zero_time_edges_created": False,
        "euclidean_distance_converted_to_time": False,
        "restricted_edges_promoted": False,
        "track_promoted_to_primary": False,
        "scientific_policy": (
            "The primary service-access policy resolves 220 services by non-temporal structural node identity and five services by observed OSM pedestrian paths temporalized at the pre-specified 1 m/s walking assumption. "
            "Seven direct-primary services outside the empirical local regime, two explicitly restricted local motor-like paths, one track-involved path, and one disconnected local OSM case remain excluded or sensitivity-only. "
            "No Euclidean snap is converted to travel time, no zero-minute edge is created, and unresolved services are reported transparently rather than silently imputed."
        ),
    }
    (outdir / "final_service_access_policy_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
