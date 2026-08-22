from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

TARGET_CRS = "EPSG:31982"  # SIRGAS 2000 / UTM 22S, suitable for most of Pará metric distance audit
INPUT_CRS = "EPSG:4674"


def _points_from_csv(path: Path, id_col: str) -> gpd.GeoDataFrame:
    df = pd.read_csv(path, low_memory=False)
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    keep = lat.notna() & lon.notna()
    df = df.loc[keep].copy()
    geom = gpd.points_from_xy(lon.loc[keep], lat.loc[keep], crs=INPUT_CRS)
    gdf = gpd.GeoDataFrame(df, geometry=geom, crs=INPUT_CRS)
    if gdf[id_col].duplicated().any():
        raise ValueError(f"{id_col} must be unique")
    return gdf


def _prepare_roads(path: Path) -> gpd.GeoDataFrame:
    roads = gpd.read_file(path, layer="roads")
    roads = roads[roads.geometry.notna() & ~roads.geometry.is_empty].copy()
    roads = roads[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    roads = roads.reset_index(drop=True)
    roads["road_feature_id"] = np.arange(len(roads), dtype="int64")
    return roads[["road_feature_id", "geometry"]].to_crs(TARGET_CRS)


def _nearest_connectors(points: gpd.GeoDataFrame, roads_m: gpd.GeoDataFrame, id_col: str) -> gpd.GeoDataFrame:
    pts_m = points.to_crs(TARGET_CRS)
    nearest = gpd.sjoin_nearest(
        pts_m[[id_col, "geometry"]],
        roads_m,
        how="left",
        distance_col="snap_distance_m",
    )
    # Ties may create duplicate point rows; retain the first deterministic road id.
    nearest = nearest.sort_values([id_col, "snap_distance_m", "road_feature_id"]).drop_duplicates(id_col)
    road_geom = roads_m.set_index("road_feature_id").geometry

    rows: list[dict] = []
    geoms: list[LineString] = []
    for row in nearest.itertuples(index=False):
        pid = getattr(row, id_col)
        p = row.geometry
        rid = int(row.road_feature_id)
        line = road_geom.loc[rid]
        snap = nearest_points(p, line)[1]
        rows.append({
            id_col: pid,
            "road_feature_id": rid,
            "snap_distance_m": float(p.distance(snap)),
            "point_x_m": float(p.x),
            "point_y_m": float(p.y),
            "snap_x_m": float(snap.x),
            "snap_y_m": float(snap.y),
            "status": "candidate_only_not_promoted",
        })
        geoms.append(LineString([p, snap]))
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=TARGET_CRS).to_crs(INPUT_CRS)


def _summary(gdf: gpd.GeoDataFrame, id_col: str) -> dict:
    d = pd.to_numeric(gdf["snap_distance_m"], errors="coerce")
    return {
        "rows": int(len(gdf)),
        "unique_ids": int(gdf[id_col].nunique()),
        "resolved": int(d.notna().sum()),
        "median_snap_distance_m": float(d.median()),
        "p90_snap_distance_m": float(d.quantile(0.90)),
        "p95_snap_distance_m": float(d.quantile(0.95)),
        "p99_snap_distance_m": float(d.quantile(0.99)),
        "max_snap_distance_m": float(d.max()),
        "within_100m": int((d <= 100).sum()),
        "within_500m": int((d <= 500).sum()),
        "within_1000m": int((d <= 1000).sum()),
        "within_5000m": int((d <= 5000).sum()),
        "status": "candidate_only_not_promoted",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build geometric access connector candidates from origins/services to OSM road network.")
    parser.add_argument("--roads", type=Path, default=Path("artifacts/multimodal_graph_inputs/roads.gpkg"))
    parser.add_argument("--origins", type=Path, default=Path("artifacts/routing_inputs/origins_for_routing.csv"))
    parser.add_argument("--destinations", type=Path, default=Path("artifacts/routing_inputs/destinations_for_routing.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/access_connector_candidates"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    roads = _prepare_roads(args.roads)
    origins = _points_from_csv(args.origins, "origin_id")
    services = _points_from_csv(args.destinations, "service_id")

    origin_conn = _nearest_connectors(origins, roads, "origin_id")
    service_conn = _nearest_connectors(services, roads, "service_id")

    origin_path = args.output_dir / "origin_to_road_connector_candidates.gpkg"
    service_path = args.output_dir / "service_to_road_connector_candidates.gpkg"
    origin_conn.to_file(origin_path, layer="origin_to_road", driver="GPKG")
    service_conn.to_file(service_path, layer="service_to_road", driver="GPKG")

    audit = {
        "distance_crs": TARGET_CRS,
        "road_features": int(len(roads)),
        "origin_to_road": _summary(origin_conn, "origin_id"),
        "service_to_road": _summary(service_conn, "service_id"),
        "policy": (
            "Nearest-road connectors are geometric candidates only. No connector is promoted solely by proximity; "
            "distance thresholds and treatment of remote/riverside origins must be decided after auditing the distribution."
        ),
        "travel_time_assigned": False,
        "ready_for_access_connector_rule_audit": True,
    }
    (args.output_dir / "access_connector_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
