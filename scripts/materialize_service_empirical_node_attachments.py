from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def main() -> None:
    audit_path = Path("artifacts/service_direct_primary_distance_regimes/service_direct_primary_distance_regimes_audit.json")
    rows_path = Path("artifacts/service_direct_primary_distance_regimes/service_direct_primary_distance_regimes.csv.gz")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    df = pd.read_csv(rows_path, low_memory=False)

    if audit["direct_primary_service_count"] != 227:
        raise RuntimeError("Unexpected direct-primary service count")
    if audit["nominal_positive_control_count"] != 13:
        raise RuntimeError("Unexpected service positive-control count")
    if audit["nominal_positive_control_local_fraction"] != 1.0:
        raise RuntimeError("Positive controls do not fully validate the empirical local service regime")
    if audit["three_component_bic_gain_over_one"] <= 0 or audit["three_component_bic_gain_over_two"] <= 0:
        raise RuntimeError("Three-component service distance model is not BIC-supported")
    if audit["bootstrap_valid"] < 190:
        raise RuntimeError("Insufficient valid bootstrap service-regime fits")

    local = df[df["empirical_local_service_regime"]].copy()
    expected = int(audit["empirical_local_service_count"])
    if len(local) != expected:
        raise RuntimeError(f"Expected {expected} local services, found {len(local)}")

    out = local[["service_id", "physical_site_id", "service_type", "municipality_code",
                 "nearest_osm_node_id", "distance_to_nearest_primary_motor_node_m",
                 "local_service_regime_posterior"]].copy()
    out["attachment_role"] = "non_temporal_empirical_cartographic_node_identity"
    out["creates_temporal_edge"] = False
    out["travel_time_assigned"] = False
    out["zero_time_edge_created"] = False
    out["distance_used_as_travel_length"] = False

    outdir = Path("artifacts/service_empirical_node_attachments")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "service_empirical_node_attachments.csv.gz", index=False, compression="gzip")

    material = {
        "service_empirical_node_attachments": int(len(out)),
        "direct_primary_service_count": 227,
        "residual_nonlocal_direct_primary_services": int(227 - len(out)),
        "positive_controls_all_local": True,
        "empirical_boundary_hardcoded": False,
        "distance_regime_is_physical_access_cutoff": False,
        "creates_temporal_edge": False,
        "travel_time_assigned": False,
        "zero_time_edge_created": False,
        "distance_used_as_travel_length": False,
        "scientific_policy": (
            "Direct-primary services in the empirically local distance regime are represented by structural node identity only. No zero-minute edge is encoded and no coordinate-to-network distance is interpreted as physical travel. Services outside the empirical local regime remain unresolved in the primary analysis."
        ),
    }
    (outdir / "service_empirical_node_attachments_audit.json").write_text(json.dumps(material, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(material, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
