from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture


def main() -> None:
    ev = pd.read_csv("artifacts/origin_network_access_evidence/origin_network_access_evidence.csv.gz", low_memory=False)
    inter = pd.read_csv("artifacts/origin_cartographic_topology_intersection/origin_cartographic_topology_intersection.csv.gz", low_memory=False)
    direct_audit = json.loads(Path("artifacts/direct_primary_origin_distance_regimes/direct_primary_origin_distance_regimes_audit.json").read_text())

    direct = ev[ev["origin_access_evidence_class"].eq("nearest_local_osm_node_in_primary_motor_graph")].copy()
    local = ev[ev["origin_access_evidence_class"].eq("local_osm_topology_connects_to_primary_motor")].copy()
    if len(direct) != 14306 or len(local) != 1049:
        raise RuntimeError(f"Unexpected class counts: direct={len(direct)}, local={len(local)}")

    d = pd.to_numeric(direct["distance_to_road_m"], errors="coerce").to_numpy(dtype=float)
    if (~np.isfinite(d) | (d <= 0)).any():
        raise RuntimeError("Direct-primary distances must all be finite and positive")
    g = GaussianMixture(n_components=2, random_state=20260825, n_init=20).fit(np.log10(d).reshape(-1, 1))
    lower_component = int(np.argsort(g.means_.ravel())[0])

    ld = pd.to_numeric(local["distance_to_road_m"], errors="coerce").to_numpy(dtype=float)
    if (~np.isfinite(ld) | (ld <= 0)).any():
        raise RuntimeError("Local-topology distances must all be finite and positive")
    local["lower_distance_regime_posterior"] = g.predict_proba(np.log10(ld).reshape(-1, 1))[:, lower_component]
    local["empirical_lower_distance_regime"] = local["lower_distance_regime_posterior"] >= 0.5

    local = local.merge(inter[["origin_id", "cartographic_topology_class"]], on="origin_id", how="left", validate="one_to_one")
    control = local["cartographic_topology_class"].eq("local_alignment_but_physical_local_osm_path_required")
    controls_in_lower = int((control & local["empirical_lower_distance_regime"]).sum())
    if int(control.sum()) != 157 or controls_in_lower != 157:
        raise RuntimeError(f"Local positive-control gate failed: {controls_in_lower}/{int(control.sum())}")
    if direct_audit["bootstrap_valid_intersections"] < 190 or direct_audit["bootstrap_bic_gain"]["p05"] <= 0:
        raise RuntimeError("Direct-primary regime stability gate failed")
    if direct_audit["positive_control_lower_regime_fraction"] != 1.0:
        raise RuntimeError("Direct-primary positive-control gate failed")

    target = local[local["empirical_lower_distance_regime"]].copy()
    out = target[["origin_id", "nearest_osm_node_id", "lower_distance_regime_posterior"]].copy()
    out["attachment_role"] = "non_temporal_cartographic_local_osm_node_identity"
    out["attachment_basis"] = "transferred_data_derived_cartographic_regime_validated_by_157_local_positive_controls"
    out["creates_temporal_edge"] = False
    out["travel_time_assigned"] = False
    out["zero_time_edge_created"] = False

    outdir = Path("artifacts/local_topology_empirical_node_attachments")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "local_topology_empirical_node_attachments.csv.gz", index=False, compression="gzip")

    audit = {
        "local_topology_origin_count": int(len(local)),
        "local_positive_control_count": int(control.sum()),
        "local_positive_controls_in_lower_regime": controls_in_lower,
        "local_positive_control_lower_regime_fraction": float(controls_in_lower / control.sum()),
        "empirical_local_topology_node_attachments": int(len(out)),
        "remaining_local_topology_outside_lower_regime": int(len(local) - len(out)),
        "empirical_boundary_hardcoded": False,
        "distance_regime_is_physical_access_cutoff": False,
        "creates_temporal_edge": False,
        "travel_time_assigned": False,
        "zero_time_edge_created": False,
        "scientific_policy": (
            "The already validated direct-primary two-regime cartographic model is transferred to origins whose nearest OSM node is locally connected to the primary motor graph. "
            "Transfer is accepted only because all 157 independently validated same-street/same-municipality local-topology controls fall in the lower regime and the source model passes bootstrap stability gates. "
            "Materialization is structural node identity only; no distance threshold, connector edge, zero-minute edge, or travel time is created."
        ),
    }
    (outdir / "local_topology_empirical_node_attachments_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
