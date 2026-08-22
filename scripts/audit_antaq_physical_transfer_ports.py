from __future__ import annotations

import json
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

PORT_ZIP = Path("data/raw/transport/antaq_ports/Instalaesporturias06052025.zip")
WATER_DIR = Path("data/raw/transport/antaq_waterways")
ROADS = Path("artifacts/multimodal_graph_inputs/roads.gpkg")
OUT = Path("artifacts/antaq_physical_transfer_ports")
DIST_CRS = "EPSG:5880"


def norm(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def col_ci(df: pd.DataFrame, wanted: str) -> str | None:
    w = norm(wanted)
    for c in df.columns:
        if norm(c) == w:
            return str(c)
    return None


def read_zip(path: Path) -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(root)
        shp = next(iter(root.rglob("*.shp")), None)
        if shp is None:
            raise RuntimeError(f"No shapefile in {path}")
        return gpd.read_file(shp)


def qstats(s: pd.Series) -> dict[str, float | None]:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return {k: None for k in ("min", "p25", "median", "p75", "p90", "p95", "p99", "max")}
    return {
        "min": float(s.min()),
        "p25": float(s.quantile(.25)),
        "median": float(s.median()),
        "p75": float(s.quantile(.75)),
        "p90": float(s.quantile(.90)),
        "p95": float(s.quantile(.95)),
        "p99": float(s.quantile(.99)),
        "max": float(s.max()),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ports = read_zip(PORT_ZIP)
    cidade = col_ci(ports, "cidade")
    estado = col_ci(ports, "estado")
    nome = col_ci(ports, "nome")
    pid = col_ci(ports, "idseq")
    if not all((cidade, estado)):
        raise RuntimeError("Current ANTAQ port layer lacks cidade/estado")
    ports = ports[ports[estado].map(norm).isin({"pa", "para"})].copy()
    ports["municipality_norm"] = ports[cidade].map(norm)
    ports["state_norm"] = "pa"
    ports["port_name"] = ports[nome].astype(str) if nome else ""
    ports["port_id"] = ports[pid].astype(str) if pid else ports.index.astype(str)
    ports = ports[ports.geometry.notna() & ~ports.geometry.is_empty].copy().reset_index(drop=True)
    ports["port_index"] = ports.index.astype(int)
    if ports.crs is None:
        ports = ports.set_crs("EPSG:4674")
    ports_m = ports.to_crs(DIST_CRS)

    water_parts = []
    for z in sorted(WATER_DIR.glob("*.zip")):
        g = read_zip(z)
        om = col_ci(g, "mun_origem")
        os = col_ci(g, "est_origem")
        dm = col_ci(g, "mun_estino")
        ds = col_ci(g, "est_estino")
        if not om or not dm:
            continue
        tmp = g.copy()
        tmp["dataset"] = z.name
        tmp["origin_municipality_norm"] = tmp[om].map(norm)
        tmp["origin_state_norm"] = tmp[os].map(norm) if os else ""
        tmp["destination_municipality_norm"] = tmp[dm].map(norm)
        tmp["destination_state_norm"] = tmp[ds].map(norm) if ds else ""
        if tmp.crs is None:
            tmp = tmp.set_crs("EPSG:4674")
        water_parts.append(tmp.to_crs(DIST_CRS))
    if not water_parts:
        raise RuntimeError("No ANTAQ waterway layers with endpoint fields")
    water = pd.concat(water_parts, ignore_index=True)
    water = gpd.GeoDataFrame(water, geometry="geometry", crs=DIST_CRS)

    rows = []
    for _, p in ports_m.iterrows():
        m = p["municipality_norm"]
        compatible = water[
            ((water["origin_municipality_norm"] == m) & water["origin_state_norm"].isin({"", "pa", "para"})) |
            ((water["destination_municipality_norm"] == m) & water["destination_state_norm"].isin({"", "pa", "para"}))
        ]
        if compatible.empty:
            rows.append({"port_index": int(p["port_index"]), "port_id": p["port_id"], "port_name": p["port_name"], "municipality": m, "compatible_hydro_segments": 0, "hydro_distance_m": None})
            continue
        d = compatible.geometry.distance(p.geometry)
        j = d.idxmin()
        rows.append({
            "port_index": int(p["port_index"]), "port_id": p["port_id"], "port_name": p["port_name"], "municipality": m,
            "compatible_hydro_segments": int(len(compatible)), "hydro_distance_m": float(d.loc[j]),
            "hydro_dataset": str(compatible.loc[j, "dataset"]),
        })
    result = pd.DataFrame(rows)

    roads = gpd.read_file(ROADS, layer="roads")
    if roads.crs is None:
        roads = roads.set_crs("EPSG:4674")
    roads_m = roads.to_crs(DIST_CRS)
    port_pts = ports_m[["port_index", "geometry"]].copy()
    road_near = gpd.sjoin_nearest(port_pts, roads_m[["geometry"]], how="left", distance_col="road_distance_m")
    road_near = road_near.sort_values(["port_index", "road_distance_m"]).drop_duplicates("port_index")
    road_map = dict(zip(road_near["port_index"].astype(int), pd.to_numeric(road_near["road_distance_m"], errors="coerce")))
    result["road_distance_m"] = result["port_index"].astype(int).map(road_map)
    result["dual_physical_distance_max_m"] = result[["hydro_distance_m", "road_distance_m"]].max(axis=1, skipna=False)

    hydro_valid = result["hydro_distance_m"].notna()
    dual_valid = result["dual_physical_distance_max_m"].notna()
    thresholds = [100, 250, 500, 1000, 2000, 5000, 10000]
    audit = {
        "port_source": PORT_ZIP.name,
        "pa_port_rows": int(len(result)),
        "ports_with_endpoint_compatible_hydro": int(hydro_valid.sum()),
        "ports_with_hydro_and_road_distance": int(dual_valid.sum()),
        "hydro_distance_m": qstats(result.loc[hydro_valid, "hydro_distance_m"]),
        "road_distance_m": qstats(result.loc[result["road_distance_m"].notna(), "road_distance_m"]),
        "dual_max_distance_m": qstats(result.loc[dual_valid, "dual_physical_distance_max_m"]),
        "dual_within_distance_counts": {f"{t}m": int((result.loc[dual_valid, "dual_physical_distance_max_m"] <= t).sum()) for t in thresholds},
        "connector_promoted": False,
        "ready_for_physical_transfer_rule_decision": True,
        "scientific_policy": "Candidate intermodal transfer points are anchored at current 2025 ANTAQ port-installation geometries in Para. Hydro candidates are restricted to ANTAQ route geometries whose official origin/destination municipality matches the port municipality. Road distance is measured to the OSM routable geometry using a unique internal port-row key. Distances are diagnostic only; no threshold is selected or connector promoted here.",
    }
    result.to_csv(OUT / "pa_physical_transfer_port_candidates.csv", index=False)
    (OUT / "pa_physical_transfer_port_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
