from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

AUDIT_CSV = Path("artifacts/front1_canonical_hydro_audit/front1_canonical_hydro_audit.csv")
OUT = Path("artifacts/validated_spatial_transfer_anchors")
TARGET_CRS = "EPSG:4674"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    audit = pd.read_csv(AUDIT_CSV)
    valid = audit[audit["spatial_anchor_validated"].astype(str).str.lower().eq("true")].copy()
    if len(valid) != 3:
        raise RuntimeError(f"Expected 3 validated front-1 anchors, got {len(valid)}")

    spec = importlib.util.spec_from_file_location("physical", "scripts/audit_antaq_physical_transfer_ports.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import physical-transfer helper")
    physical = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(physical)
    ports = physical.read_zip(physical.PORT_ZIP)
    estado = physical.col_ci(ports, "estado")
    if not estado:
        raise RuntimeError("ANTAQ port layer lacks estado")
    norm = physical.norm
    ports = ports[ports[estado].map(norm).isin({"pa", "para"})].copy()
    ports = ports[ports.geometry.notna() & ~ports.geometry.is_empty].copy()
    if ports.crs is None:
        ports = ports.set_crs(TARGET_CRS)
    ports = ports.to_crs(TARGET_CRS).reset_index(drop=True)

    rows = []
    geoms = []
    for _, r in valid.sort_values("evidence_rank").iterrows():
        pi = int(r["port_index"])
        if pi < 0 or pi >= len(ports):
            raise RuntimeError(f"port_index out of range: {pi}")
        p = ports.iloc[pi]
        rows.append({
            "anchor_id": f"antaq_pa_front1_{pi}",
            "evidence_rank": int(r["evidence_rank"]),
            "port_index": pi,
            "port_name": str(r["port_name"]),
            "municipality": str(r["municipality"]),
            "hydro_id": r["hydro_id"],
            "river_name": r["river_name"],
            "road_distance_m": float(r["road_distance_m"]),
            "hydro_distance_m": float(r["hydro_distance_m_canonical"]),
            "reported_hydro_time": r["reported_time"],
            "spatial_anchor_status": "validated",
            "validation_basis": "official_antaq_port+official_endpoint_match+canonical_geometry_reproducibility+pareto_front1",
            "temporal_connector_impedance_status": "unresolved",
            "routing_enabled": False,
            "zero_time_assumed": False,
            "distance_to_time_conversion_used": False,
        })
        geoms.append(p.geometry)

    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=TARGET_CRS)
    gdf.to_file(OUT / "validated_spatial_transfer_anchors.gpkg", layer="anchors", driver="GPKG")
    pd.DataFrame(rows).to_csv(OUT / "validated_spatial_transfer_anchors.csv", index=False)

    summary = {
        "validated_spatial_anchor_count": int(len(gdf)),
        "anchor_names": gdf["port_name"].tolist(),
        "all_spatially_validated": bool((gdf["spatial_anchor_status"] == "validated").all()),
        "temporal_connector_impedance_resolved": False,
        "routing_enabled": False,
        "connector_promoted_for_temporal_routing": False,
        "zero_time_assumed": False,
        "distance_to_time_conversion_used": False,
        "scientific_policy": "These records materialize validated spatial intermodal anchors only. They are not traversable temporal connectors until a defensible transfer-impedance rule is established. No zero-time transfer and no unsupported distance-to-time conversion are introduced.",
    }
    (OUT / "validated_spatial_transfer_anchors_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
