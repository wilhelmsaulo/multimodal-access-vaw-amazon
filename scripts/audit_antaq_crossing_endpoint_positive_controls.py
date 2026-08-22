from __future__ import annotations

import importlib.util
import json
import math
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

CROSSING_ZIP = Path("data/raw/transport/antaq_ports/Linhasdetravessias06052025.zip")
PORT_ZIP = Path("data/raw/transport/antaq_ports/Instalaesporturias06052025.zip")
ROADS = Path("artifacts/multimodal_graph_inputs/roads.gpkg")
WATERWAYS = Path("artifacts/multimodal_graph_inputs/waterways.gpkg")
OUT = Path("artifacts/antaq_crossing_endpoint_positive_controls")
GEOGRAPHIC_CRS = "EPSG:4674"
DISTANCE_CRS = "EPSG:5880"


def norm(v: object) -> str:
    s = "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().strip().split())


def col_ci(df: pd.DataFrame, *names: str) -> str | None:
    lookup = {norm(c).replace(" ", "_"): str(c) for c in df.columns}
    for name in names:
        key = norm(name).replace(" ", "_")
        if key in lookup:
            return lookup[key]
    return None


def read_zip(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    with zipfile.ZipFile(path) as z:
        shp = [n for n in z.namelist() if n.lower().endswith(".shp")]
        if not shp:
            raise RuntimeError(f"No shapefile in {path}")
        layer = shp[0]
    return gpd.read_file(f"zip://{path}!{layer}")


def quantiles(s: pd.Series) -> dict[str, float | None]:
    x = pd.to_numeric(s, errors="coerce").dropna()
    if x.empty:
        return {k: None for k in ("min", "p25", "median", "p75", "p90", "p95", "max")}
    return {
        "min": float(x.min()),
        "p25": float(x.quantile(0.25)),
        "median": float(x.median()),
        "p75": float(x.quantile(0.75)),
        "p90": float(x.quantile(0.90)),
        "p95": float(x.quantile(0.95)),
        "max": float(x.max()),
    }


def within_counts(s: pd.Series) -> dict[str, int]:
    x = pd.to_numeric(s, errors="coerce")
    return {
        "100m": int((x <= 100).sum()),
        "250m": int((x <= 250).sum()),
        "500m": int((x <= 500).sum()),
        "1000m": int((x <= 1000).sum()),
        "2000m": int((x <= 2000).sum()),
        "5000m": int((x <= 5000).sum()),
    }


def nearest_distance(point, geoms: gpd.GeoSeries) -> float | None:
    if geoms.empty:
        return None
    vals = geoms.distance(point)
    if vals.empty:
        return None
    return float(vals.min())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    crossings = read_zip(CROSSING_ZIP)
    ports = read_zip(PORT_ZIP)
    roads = gpd.read_file(ROADS, layer="roads")
    hydro = gpd.read_file(WATERWAYS, layer="waterways")

    # Exact semantic fields documented in the ANTAQ crossing dataset.
    c_mun_o = col_ci(crossings, "mun_origem")
    c_uf_o = col_ci(crossings, "est_origem")
    c_mun_d = col_ci(crossings, "mun_estino", "mun_destino")
    c_uf_d = col_ci(crossings, "est_estino", "est_destino")
    c_lat_o = col_ci(crossings, "orig_lat")
    c_lon_o = col_ci(crossings, "orig_long")
    c_lat_d = col_ci(crossings, "dest_lat")
    c_lon_d = col_ci(crossings, "dest_long")
    c_river = col_ci(crossings, "nome_rio")
    c_river_id = col_ci(crossings, "IDRio", "id_rio")
    c_code_o = col_ci(crossings, "cod_origem")
    c_code_d = col_ci(crossings, "cod_estino", "cod_destino")

    required = [c_mun_o, c_uf_o, c_mun_d, c_uf_d, c_lat_o, c_lon_o, c_lat_d, c_lon_d]
    if any(v is None for v in required):
        raise RuntimeError(f"Missing required crossing endpoint fields: {required}")

    p_mun = col_ci(ports, "cidade")
    p_uf = col_ci(ports, "estado")
    p_name = col_ci(ports, "nome")
    if not p_mun or not p_uf:
        raise RuntimeError("Current ANTAQ port layer lacks cidade/estado")

    # Canonical hydro already has standardized semantic fields.
    for c in ("origin_municipality", "origin_state", "destination_municipality", "destination_state"):
        if c not in hydro.columns:
            raise RuntimeError(f"Canonical hydro missing {c}")

    # Restrict ports to Pará for the same-municipality positive-control association.
    ports = ports[ports[p_uf].map(norm).isin({"pa", "para"})].copy()
    ports = ports[ports.geometry.notna() & ~ports.geometry.is_empty].copy()
    if ports.crs is None:
        ports = ports.set_crs(GEOGRAPHIC_CRS)
    ports = ports.to_crs(DISTANCE_CRS).reset_index(drop=True)
    ports["_mun_norm"] = ports[p_mun].map(norm)
    ports["_uf_norm"] = ports[p_uf].map(norm)

    if roads.crs is None:
        roads = roads.set_crs(GEOGRAPHIC_CRS)
    roads = roads.to_crs(DISTANCE_CRS)
    roads = roads[roads.geometry.notna() & ~roads.geometry.is_empty].copy()

    if hydro.crs is None:
        hydro = hydro.set_crs(GEOGRAPHIC_CRS)
    hydro = hydro.to_crs(DISTANCE_CRS)
    hydro = hydro[hydro.geometry.notna() & ~hydro.geometry.is_empty].copy()
    hydro["_origin_mun_norm"] = hydro["origin_municipality"].map(norm)
    hydro["_origin_uf_norm"] = hydro["origin_state"].map(norm)
    hydro["_dest_mun_norm"] = hydro["destination_municipality"].map(norm)
    hydro["_dest_uf_norm"] = hydro["destination_state"].map(norm)

    pa_lines_mask = (
        crossings[c_uf_o].map(norm).isin({"pa", "para"})
        | crossings[c_uf_d].map(norm).isin({"pa", "para"})
    )
    pa_lines = crossings.loc[pa_lines_mask].copy().reset_index(drop=False).rename(columns={"index": "crossing_row_index"})

    endpoint_rows: list[dict[str, object]] = []
    for _, r in pa_lines.iterrows():
        for side in ("origin", "destination"):
            if side == "origin":
                municipality = r[c_mun_o]
                state = r[c_uf_o]
                lat = pd.to_numeric(pd.Series([r[c_lat_o]]), errors="coerce").iloc[0]
                lon = pd.to_numeric(pd.Series([r[c_lon_o]]), errors="coerce").iloc[0]
                code = r[c_code_o] if c_code_o else None
            else:
                municipality = r[c_mun_d]
                state = r[c_uf_d]
                lat = pd.to_numeric(pd.Series([r[c_lat_d]]), errors="coerce").iloc[0]
                lon = pd.to_numeric(pd.Series([r[c_lon_d]]), errors="coerce").iloc[0]
                code = r[c_code_d] if c_code_d else None

            # The calibration population is the official endpoint itself when located in Pará.
            if norm(state) not in {"pa", "para"}:
                continue
            if pd.isna(lat) or pd.isna(lon):
                continue

            pt_geo = gpd.GeoSeries([Point(float(lon), float(lat))], crs=GEOGRAPHIC_CRS)
            pt = pt_geo.to_crs(DISTANCE_CRS).iloc[0]
            mun_n = norm(municipality)

            p_candidates = ports[(ports["_mun_norm"] == mun_n) & (ports["_uf_norm"].isin({"pa", "para"}))]
            port_dist = nearest_distance(pt, p_candidates.geometry)
            nearest_port_name = None
            if port_dist is not None and not p_candidates.empty:
                d = p_candidates.geometry.distance(pt)
                pi = d.idxmin()
                nearest_port_name = str(p_candidates.loc[pi, p_name]) if p_name else None

            hydro_dist_any = nearest_distance(pt, hydro.geometry)
            h_compat = hydro[
                ((hydro["_origin_mun_norm"] == mun_n) & hydro["_origin_uf_norm"].isin({"pa", "para"}))
                | ((hydro["_dest_mun_norm"] == mun_n) & hydro["_dest_uf_norm"].isin({"pa", "para"}))
            ]
            hydro_dist_compatible = nearest_distance(pt, h_compat.geometry)
            road_dist = nearest_distance(pt, roads.geometry)

            endpoint_rows.append({
                "crossing_row_index": int(r["crossing_row_index"]),
                "endpoint_side": side,
                "endpoint_code": None if code is None else str(code),
                "municipality": str(municipality),
                "state": str(state),
                "river_id": None if c_river_id is None else str(r[c_river_id]),
                "river_name": None if c_river is None else str(r[c_river]),
                "latitude": float(lat),
                "longitude": float(lon),
                "same_municipality_port_available": bool(not p_candidates.empty),
                "nearest_same_municipality_port_name": nearest_port_name,
                "endpoint_to_same_municipality_port_m": port_dist,
                "endpoint_to_nearest_canonical_hydro_m": hydro_dist_any,
                "endpoint_to_municipality_compatible_hydro_m": hydro_dist_compatible,
                "endpoint_to_osm_road_m": road_dist,
            })

    endpoints = pd.DataFrame(endpoint_rows)
    endpoints.to_csv(OUT / "pa_crossing_endpoints_positive_controls.csv", index=False)

    n = int(len(endpoints))
    audit = {
        "source": str(CROSSING_ZIP),
        "pa_crossing_lines": int(len(pa_lines)),
        "pa_official_endpoints_with_coordinates": n,
        "endpoints_with_same_municipality_port": int(endpoints["same_municipality_port_available"].sum()) if n else 0,
        "endpoint_to_same_municipality_port_m": {
            "n": int(endpoints["endpoint_to_same_municipality_port_m"].notna().sum()) if n else 0,
            "quantiles": quantiles(endpoints["endpoint_to_same_municipality_port_m"]) if n else {},
            "within_counts": within_counts(endpoints["endpoint_to_same_municipality_port_m"]) if n else {},
        },
        "endpoint_to_nearest_canonical_hydro_m": {
            "n": int(endpoints["endpoint_to_nearest_canonical_hydro_m"].notna().sum()) if n else 0,
            "quantiles": quantiles(endpoints["endpoint_to_nearest_canonical_hydro_m"]) if n else {},
            "within_counts": within_counts(endpoints["endpoint_to_nearest_canonical_hydro_m"]) if n else {},
        },
        "endpoint_to_municipality_compatible_hydro_m": {
            "n": int(endpoints["endpoint_to_municipality_compatible_hydro_m"].notna().sum()) if n else 0,
            "quantiles": quantiles(endpoints["endpoint_to_municipality_compatible_hydro_m"]) if n else {},
            "within_counts": within_counts(endpoints["endpoint_to_municipality_compatible_hydro_m"]) if n else {},
        },
        "endpoint_to_osm_road_m": {
            "n": int(endpoints["endpoint_to_osm_road_m"].notna().sum()) if n else 0,
            "quantiles": quantiles(endpoints["endpoint_to_osm_road_m"]) if n else {},
            "within_counts": within_counts(endpoints["endpoint_to_osm_road_m"]) if n else {},
        },
        "connector_rule_adopted": False,
        "distance_threshold_adopted": False,
        "distance_to_time_conversion_used": False,
        "routing_enabled": False,
        "scientific_policy": (
            "Official ANTAQ crossing origin/destination coordinates in Para are used as positive controls for how known "
            "water-transfer terminals align with the current ANTAQ port layer, the standardized ANTAQ hydro geometry, "
            "and the OSM road geometry. Distances are calibration evidence only. No cutoff is selected, no connector is "
            "promoted, and no distance is converted to time."
        ),
        "ready_for_empirical_connector_geometry_decision": bool(n > 0),
    }
    (OUT / "pa_crossing_endpoints_positive_controls_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
