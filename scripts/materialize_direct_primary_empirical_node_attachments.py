from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REGIME_DIR = Path("artifacts/direct_primary_origin_distance_regimes")
REGIME_CSV = REGIME_DIR / "direct_primary_origin_distance_regimes.csv.gz"
REGIME_AUDIT = REGIME_DIR / "direct_primary_origin_distance_regimes_audit.json"
INTERSECTION_CSV = Path("artifacts/origin_cartographic_topology_intersection/origin_cartographic_topology_intersection.csv.gz")
OUTDIR = Path("artifacts/direct_primary_empirical_node_attachments")


def main() -> None:
    audit = json.loads(REGIME_AUDIT.read_text(encoding="utf-8"))

    # Scientific gates: the empirical regime must be strongly supported and must
    # reproduce every independently validated positive control before it can be
    # used as structural cartographic attachment evidence.
    if audit["bic_improvement_two_over_one"] <= 0:
        raise RuntimeError("Two-regime model is not preferred by BIC")
    if audit["positive_control_count"] != 4368:
        raise RuntimeError(f"Unexpected positive-control count: {audit['positive_control_count']}")
    if audit["positive_control_lower_regime_fraction"] != 1.0:
        raise RuntimeError("Not all independent positive controls fall in the lower empirical regime")
    if audit["bootstrap_valid_intersections"] < 190:
        raise RuntimeError("Fewer than 190/200 bootstrap samples produced a valid regime intersection")
    if audit["bootstrap_bic_gain"]["p05"] is None or audit["bootstrap_bic_gain"]["p05"] <= 0:
        raise RuntimeError("Bootstrap does not consistently support the two-regime model")
    if audit["distance_regime_is_routing_cutoff"] is not False:
        raise RuntimeError("Distance regime must not be encoded as a routing cutoff")
    if audit["connector_promoted"] is not False or audit["travel_time_assigned"] is not False:
        raise RuntimeError("Upstream regime audit unexpectedly promoted a connector or time")

    regimes = pd.read_csv(REGIME_CSV, dtype={"origin_id": "string"}, low_memory=False)
    topo = pd.read_csv(INTERSECTION_CSV, dtype={"origin_id": "string"}, low_memory=False)
    required_topo = ["origin_id", "nearest_osm_node_id"]
    missing = [c for c in required_topo if c not in topo.columns]
    if missing:
        raise RuntimeError(f"Missing topology columns: {missing}")

    x = regimes.merge(topo[required_topo], on="origin_id", how="left", validate="one_to_one")
    is_control = x["cartographic_topology_class"].eq("local_alignment_and_primary_motor_topology")
    lower = x["empirical_lower_distance_regime"].fillna(False).astype(bool)
    target = x[lower & ~is_control].copy()

    expected = int(audit["unvalidated_direct_in_lower_regime"])
    if len(target) != expected:
        raise RuntimeError(f"Expected {expected} additional empirical attachments, found {len(target)}")
    if target["nearest_osm_node_id"].isna().any():
        raise RuntimeError("Missing nearest OSM node for an empirical direct-primary attachment")

    out = target[[
        "origin_id", "nearest_osm_node_id", "distance_to_road_m",
        "lower_distance_regime_posterior"
    ]].copy()
    out["attachment_role"] = "non_temporal_cartographic_node_identity"
    out["attachment_basis"] = "direct_primary_empirical_lower_cartographic_regime_validated_by_independent_positive_controls"
    out["creates_temporal_edge"] = False
    out["travel_time_assigned"] = False
    out["zero_time_edge_created"] = False
    out["distance_used_as_travel_length"] = False

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTDIR / "direct_primary_empirical_node_attachments.csv.gz", index=False, compression="gzip")

    result = {
        "additional_empirical_direct_primary_attachments": int(len(out)),
        "unique_origins": int(out["origin_id"].nunique()),
        "unique_primary_motor_nodes": int(out["nearest_osm_node_id"].nunique()),
        "positive_controls_required": 4368,
        "positive_control_lower_regime_fraction_required": 1.0,
        "observed_posterior_intersection_m": audit["posterior_intersection_m"],
        "empirical_boundary_hardcoded": False,
        "distance_regime_is_physical_access_cutoff": False,
        "attachment_role": "non_temporal_cartographic_node_identity",
        "creates_temporal_edge": False,
        "travel_time_assigned": False,
        "zero_time_edge_created": False,
        "distance_used_as_travel_length": False,
        "scientific_policy": (
            "Direct-primary origins assigned to the lower data-derived cartographic distance regime are materialized only as structural OSM node identities after the regime is independently validated by all 4,368 nominal/topological positive controls and by bootstrap model stability. The learned posterior boundary is recalculated from the data and is not a statewide physical-distance cutoff. No connector edge, zero-minute edge, Euclidean travel length, or travel time is created."
        ),
    }
    (OUTDIR / "direct_primary_empirical_node_attachments_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
