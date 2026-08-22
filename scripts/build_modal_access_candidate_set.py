from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

ORIGINS = Path("artifacts/routing_inputs/origins_for_routing.csv")
ROADS = Path("artifacts/multimodal_graph_inputs/roads.gpkg")
WATERWAYS = Path("artifacts/multimodal_graph_inputs/waterways.gpkg")
OUT = Path("artifacts/modal_access_candidates")
DISTANCE_CRS = "EPSG:31982"


def _points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        df.copy(),
        geometry=[Point(xy) for xy in zip(df["longitude"], df["latitude"])],
        crs="EPSG:4674",
    )


def _nearest(points: gpd.GeoDataFrame, network: gpd.GeoDataFrame, mode: str) -> pd.DataFrame:
    p = points.to_crs(DISTANCE_CRS)
    n = network.to_crs(DISTANCE_CRS).reset_index(drop=True)
    joined = gpd.sjoin_nearest(
        p[["origin_id", "geometry"]],
        n[["geometry"]],
        how="left",
        distance_col="access_distance_m",
    )
    joined = joined.sort_values(["origin_id", "access_distance_m"]).drop_duplicates("origin_id")
    return pd.DataFrame({
        "origin_id": joined["origin_id"].astype(str).values,
        "mode": mode,
        "access_distance_m": pd.to_numeric(joined["access_distance_m"], errors="coerce").values,
        "network_feature_index": joined["index_right"].astype("Int64").values,
        "candidate_status": "retained_not_promoted",
    })


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    origins = pd.read_csv(ORIGINS, low_memory=False)
    roads = gpd.read_file(ROADS)
    waterways = gpd.read_file(WATERWAYS)
    pts = _points(origins)

    road = _nearest(pts, roads, "road")
    water = _nearest(pts, waterways, "waterway")
    candidates = pd.concat([road, water], ignore_index=True)

    pivot = candidates.pivot(index="origin_id", columns="mode", values="access_distance_m")
    pivot["nearest_geometric_mode"] = pivot.apply(
        lambda r: "waterway" if r.get("waterway", float("inf")) < r.get("road", float("inf")) else "road",
        axis=1,
    )
    candidates = candidates.merge(
        pivot[["nearest_geometric_mode"]], left_on="origin_id", right_index=True, how="left"
    )
    candidates["is_geometrically_nearest_mode"] = candidates["mode"] == candidates["nearest_geometric_mode"]
    candidates["model_role"] = "alternative_access_candidate"
    candidates["travel_time_min"] = pd.NA
    candidates.to_csv(OUT / "origin_modal_access_candidates.csv.gz", index=False, compression="gzip")

    nearest_counts = pivot["nearest_geometric_mode"].value_counts().to_dict()
    audit = {
        "origins": int(origins["origin_id"].nunique()),
        "candidate_rows": int(len(candidates)),
        "candidates_per_origin": int(len(candidates) / origins["origin_id"].nunique()),
        "modes": ["road", "waterway"],
        "geometrically_nearest_mode_counts": {str(k): int(v) for k, v in nearest_counts.items()},
        "model_choice": "non_exclusive_multimodal_access_candidates",
        "model_rationale": (
            "Origins are not pre-classified as road or waterway. Both structural access alternatives are retained, "
            "and geometric proximity is descriptive only. Final path viability and mode choice must be determined "
            "after defensible temporal calibration and network routing."
        ),
        "threshold_policy": "No fixed 1 km or 5 km connector threshold is used to assign a mode.",
        "travel_time_assigned": False,
        "ready_for_temporal_calibration": True,
    }
    (OUT / "modal_access_candidate_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
