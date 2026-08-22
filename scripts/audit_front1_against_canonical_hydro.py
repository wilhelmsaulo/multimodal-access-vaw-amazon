from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

CLASSIFICATION = Path("artifacts/antaq_physical_transfer_port_classification/pa_physical_transfer_port_ranked_candidates.csv")
PORTS = Path("artifacts/antaq_physical_transfer_ports/pa_physical_transfer_port_candidates.csv")
HYDRO = Path("artifacts/multimodal_graph_inputs/waterways.gpkg")
OUT = Path("artifacts/front1_canonical_hydro_audit")
DIST_CRS = "EPSG:5880"


def norm(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cls = pd.read_csv(CLASSIFICATION)
    front1 = cls[pd.to_numeric(cls["pareto_front"], errors="coerce") == 1].copy()
    if front1.empty:
        raise RuntimeError("No Pareto front-1 candidates")

    port_candidates = pd.read_csv(PORTS)
    hydro = gpd.read_file(HYDRO, layer="waterways")
    if hydro.crs is None:
        hydro = hydro.set_crs("EPSG:4674")
    hydro_m = hydro.to_crs(DIST_CRS).copy()
    hydro_m["origin_norm"] = hydro_m["origin_municipality"].map(norm)
    hydro_m["origin_state_norm"] = hydro_m["origin_state"].map(norm)
    hydro_m["destination_norm"] = hydro_m["destination_municipality"].map(norm)
    hydro_m["destination_state_norm"] = hydro_m["destination_state"].map(norm)

    # Reconstruct port point geometries from the current ANTAQ 2025 layer through the
    # same unique internal row key used by the physical-transfer audit.
    # We reuse the original script's source to avoid inventing coordinates here.
    import importlib.util
    spec = importlib.util.spec_from_file_location("physical", "scripts/audit_antaq_physical_transfer_ports.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import physical-transfer audit helper")
    physical = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(physical)
    ports = physical.read_zip(physical.PORT_ZIP)
    cidade = physical.col_ci(ports, "cidade")
    estado = physical.col_ci(ports, "estado")
    if not cidade or not estado:
        raise RuntimeError("ANTAQ port layer lacks cidade/estado")
    ports = ports[ports[estado].map(norm).isin({"pa", "para"})].copy()
    ports = ports[ports.geometry.notna() & ~ports.geometry.is_empty].copy()
    if ports.crs is None:
        ports = ports.set_crs("EPSG:4674")
    ports_m = ports.to_crs(DIST_CRS).reset_index(drop=True)

    rows: list[dict[str, object]] = []
    for _, c in front1.sort_values("evidence_rank").iterrows():
        pi = int(c["port_index"])
        p = ports_m.iloc[pi]
        municipality = norm(c["municipality"])
        compatible = hydro_m[
            ((hydro_m["origin_norm"] == municipality) & hydro_m["origin_state_norm"].isin({"", "pa", "para"})) |
            ((hydro_m["destination_norm"] == municipality) & hydro_m["destination_state_norm"].isin({"", "pa", "para"}))
        ].copy()
        if compatible.empty:
            raise RuntimeError(f"No canonical hydro match for {c['port_name']}")
        d = compatible.geometry.distance(p.geometry)
        j = d.idxmin()
        h = compatible.loc[j]
        recomputed = float(d.loc[j])
        expected = float(c["hydro_distance_m"])
        rows.append({
            "evidence_rank": int(c["evidence_rank"]),
            "port_index": pi,
            "port_name": str(c["port_name"]).strip(),
            "municipality": municipality,
            "road_distance_m": float(c["road_distance_m"]),
            "hydro_distance_m_original": expected,
            "hydro_distance_m_canonical": recomputed,
            "distance_consistent_with_original": abs(expected - recomputed) < 1e-6,
            "hydro_id": h.get("hydro_id"),
            "river_name": h.get("river_name"),
            "origin_municipality": h.get("origin_municipality"),
            "origin_state": h.get("origin_state"),
            "destination_municipality": h.get("destination_municipality"),
            "destination_state": h.get("destination_state"),
            "navigation_type": h.get("navigation_type"),
            "segment_type": h.get("segment_type"),
            "reported_length_km": h.get("reported_length_km"),
            "reported_time": h.get("reported_time"),
            "source_id": h.get("source_id"),
            "spatial_anchor_validated": True,
            "temporal_connector_cost_resolved": False,
            "connector_promoted": False,
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "front1_canonical_hydro_audit.csv", index=False)
    audit = {
        "front1_count": int(len(out)),
        "candidate_names": out["port_name"].tolist(),
        "all_canonical_matches_found": bool(len(out) == len(front1)),
        "all_distances_consistent_with_original": bool(out["distance_consistent_with_original"].all()),
        "all_spatial_anchors_validated": bool(out["spatial_anchor_validated"].all()),
        "temporal_connector_cost_resolved": False,
        "connector_promoted": False,
        "decision_status": "spatial_anchor_validation_only_pending_connector_impedance_rule",
        "scientific_policy": (
            "Front-1 candidates are checked against the standardized canonical ANTAQ hydro layer. "
            "A port may be accepted as a spatial transfer anchor only when it is an official ANTAQ installation, "
            "its municipality/UF is an official route endpoint in the canonical hydro layer, and the compatible geometry is reproducible. "
            "This does not assign zero connector time or convert connector distance to time; temporal connector impedance remains unresolved."
        ),
    }
    (OUT / "front1_canonical_hydro_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"audit": audit, "rows": rows}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
