from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

DISTANCE_CRS = "EPSG:5880"  # SIRGAS 2000 / Brazil Polyconic; statewide metric CRS for Pará
GEOGRAPHIC_CRS = "EPSG:4674"


def _points_from_csv(path: Path, id_col: str) -> gpd.GeoDataFrame:
    df = pd.read_csv(path, low_memory=False)
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    keep = lat.notna() & lon.notna()
    df = df.loc[keep].copy()
    g = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(lon.loc[keep], lat.loc[keep]),
        crs=GEOGRAPHIC_CRS,
    )
    if g[id_col].duplicated().any():
        raise ValueError(f"{id_col} must be unique")
    return g


def _nearest_distance(points: gpd.GeoDataFrame, targets: gpd.GeoDataFrame, prefix: str) -> pd.DataFrame:
    if targets.empty:
        raise ValueError(f"Target layer {prefix} is empty")
    p = points.to_crs(DISTANCE_CRS).copy()
    t = targets.to_crs(DISTANCE_CRS).copy().reset_index(drop=True)
    t["target_index"] = t.index.astype("int64")
    joined = gpd.sjoin_nearest(
        p[["geometry"]],
        t[["target_index", "geometry"]],
        how="left",
        distance_col=f"distance_to_{prefix}_m",
    )
    joined = joined.reset_index().rename(columns={"index": "point_index"})
    joined = joined.sort_values(["point_index", f"distance_to_{prefix}_m", "target_index"])
    joined = joined.drop_duplicates("point_index", keep="first").set_index("point_index")
    return joined[["target_index", f"distance_to_{prefix}_m"]]


def _summary(values: pd.Series) -> dict[str, float | int | None]:
    x = pd.to_numeric(values, errors="coerce").dropna()
    if x.empty:
        return {"n": 0, "median_m": None, "p90_m": None, "p95_m": None, "p99_m": None, "max_m": None}
    return {
        "n": int(len(x)),
        "median_m": float(x.median()),
        "p90_m": float(x.quantile(0.90)),
        "p95_m": float(x.quantile(0.95)),
        "p99_m": float(x.quantile(0.99)),
        "max_m": float(x.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit geometric proximity of routing origins to road and water transport layers.")
    parser.add_argument("--origins", type=Path, default=Path("artifacts/routing_inputs/origins_for_routing.csv"))
    parser.add_argument("--roads", type=Path, default=Path("artifacts/multimodal_graph_inputs/roads.gpkg"))
    parser.add_argument("--waterways", type=Path, default=Path("artifacts/multimodal_graph_inputs/waterways.gpkg"))
    parser.add_argument("--ports", type=Path, default=Path("artifacts/multimodal_graph_inputs/ports.gpkg"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/origin_modal_proximity"))
    args = parser.parse_args()

    origins = _points_from_csv(args.origins, "origin_id")
    roads = gpd.read_file(args.roads)
    waterways = gpd.read_file(args.waterways)
    ports = gpd.read_file(args.ports)

    road = _nearest_distance(origins, roads, "road")
    water = _nearest_distance(origins, waterways, "waterway")
    port = _nearest_distance(origins, ports, "port")

    base = origins.reset_index(drop=True).copy()
    out = pd.DataFrame({
        "origin_id": base["origin_id"].astype(str),
        "municipality_code": base.get("municipality_code"),
        "municipality_name": base.get("municipality_name"),
        "female_population": base.get("female_population"),
        "latitude": base.geometry.y,
        "longitude": base.geometry.x,
    })
    for frame in (road, water, port):
        frame2 = frame.reset_index(drop=True)
        for col in frame2.columns:
            out[col] = frame2[col].values

    out["waterway_minus_road_m"] = out["distance_to_waterway_m"] - out["distance_to_road_m"]
    out["port_minus_road_m"] = out["distance_to_port_m"] - out["distance_to_road_m"]
    out["waterway_to_road_distance_ratio"] = np.where(
        out["distance_to_road_m"] > 0,
        out["distance_to_waterway_m"] / out["distance_to_road_m"],
        np.nan,
    )
    out["nearest_geometry_signal"] = np.where(
        out["distance_to_waterway_m"] < out["distance_to_road_m"],
        "waterway_closer_than_road",
        "road_closer_or_equal",
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output_dir / "origin_modal_proximity_audit.csv.gz", index=False, compression="gzip")

    road_dist = pd.to_numeric(out["distance_to_road_m"], errors="coerce")
    water_dist = pd.to_numeric(out["distance_to_waterway_m"], errors="coerce")
    port_dist = pd.to_numeric(out["distance_to_port_m"], errors="coerce")
    water_closer = water_dist < road_dist

    descriptive_road_bands = {
        "within_100m": int((road_dist <= 100).sum()),
        "within_500m": int((road_dist <= 500).sum()),
        "within_1000m": int((road_dist <= 1000).sum()),
        "within_5000m": int((road_dist <= 5000).sum()),
        "beyond_5000m": int((road_dist > 5000).sum()),
    }

    remote5 = road_dist > 5000
    remote1 = road_dist > 1000
    audit = {
        "origins": int(len(out)),
        "distance_crs": DISTANCE_CRS,
        "distance_crs_rationale": "SIRGAS 2000 / Brazil Polyconic is valid statewide and avoids single-zone UTM distortion across Pará.",
        "layers": {
            "roads": int(len(roads)),
            "waterways": int(len(waterways)),
            "ports": int(len(ports)),
        },
        "distance_summary": {
            "road": _summary(road_dist),
            "waterway": _summary(water_dist),
            "port": _summary(port_dist),
        },
        "descriptive_road_distance_bands": descriptive_road_bands,
        "relative_modal_proximity": {
            "waterway_closer_than_road_all_origins": int(water_closer.sum()),
            "road_closer_or_equal_all_origins": int((~water_closer).sum()),
            "waterway_closer_fraction_all_origins": float(water_closer.mean()),
            "origins_beyond_1km_from_road": int(remote1.sum()),
            "waterway_closer_among_beyond_1km_from_road": int((remote1 & water_closer).sum()),
            "origins_beyond_5km_from_road": int(remote5.sum()),
            "waterway_closer_among_beyond_5km_from_road": int((remote5 & water_closer).sum()),
        },
        "policy": (
            "This audit compares geometric proximity only. The 1 km and 5 km values are descriptive bands, not accepted routing thresholds. "
            "No origin is assigned a travel mode, no connector is promoted, and no speed or travel time is inferred from these distances."
        ),
        "ready_for_connector_model_decision": True,
        "travel_time_assigned": False,
    }
    (args.output_dir / "origin_modal_proximity_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
