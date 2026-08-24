from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def main() -> None:
    src = Path("artifacts/origin_cartographic_topology_intersection/origin_cartographic_topology_intersection.csv.gz")
    df = pd.read_csv(src, dtype={"origin_id": "string"}, low_memory=False)

    target = df[df["cartographic_topology_class"].eq("local_alignment_and_primary_motor_topology")].copy()
    if len(target) != 4368:
        raise RuntimeError(f"Expected 4368 eligible cartographic attachments, found {len(target)}")

    required = ["origin_id", "nearest_osm_node_id"]
    missing = [c for c in required if c not in target.columns]
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}")

    out = target[["origin_id", "nearest_osm_node_id"]].copy()
    out["attachment_role"] = "non_temporal_cartographic_node_identity"
    out["attachment_basis"] = "same_street_same_municipality_empirical_local_regime_plus_primary_motor_topology"
    out["creates_temporal_edge"] = False
    out["travel_time_assigned"] = False
    out["zero_time_edge_created"] = False

    outdir = Path("artifacts/origin_cartographic_node_attachments")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "origin_cartographic_node_attachments.csv.gz", index=False, compression="gzip")

    audit = {
        "origin_cartographic_node_attachments": int(len(out)),
        "unique_origins": int(out["origin_id"].nunique()),
        "unique_primary_motor_nodes": int(out["nearest_osm_node_id"].nunique()),
        "attachment_role": "non_temporal_cartographic_node_identity",
        "creates_temporal_edge": False,
        "travel_time_assigned": False,
        "zero_time_edge_created": False,
        "euclidean_distance_converted_to_time": False,
        "hydro_priority_residual_absorbed": False,
        "scientific_policy": (
            "Origins with independent same-street/same-municipality evidence in the empirically local cartographic-alignment regime, "
            "whose nearest OSM node is already part of the primary motor graph, are represented by a structural node-identity mapping only. "
            "No connector edge is created, no zero-minute edge is encoded, and no cartographic distance is interpreted as physical travel."
        ),
    }
    (outdir / "origin_cartographic_node_attachments_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
