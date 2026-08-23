from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

DISTANCE_CRS = "EPSG:5880"
ORIGINS = Path("artifacts/routing_inputs/origins_for_routing.csv")
DESTINATIONS = Path("artifacts/routing_inputs/destinations_for_routing.csv")
ORIGIN_SOURCE = Path("data/processed/ibge/pa_cnefe_sector_origins_2022.csv")
SERVICES = Path("artifacts/service_inventory/services_readiness.csv")
ROADS = Path("artifacts/multimodal_graph_inputs/roads.gpkg")
WATERWAYS = Path("artifacts/multimodal_graph_inputs/waterways.gpkg")
OUT = Path("artifacts/access_connector_semantics")


def _points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    if lat.isna().any() or lon.isna().any():
        raise ValueError("Routing-ready points must have complete coordinates")
    return gpd.GeoDataFrame(
        df.copy(), geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4674"
    )


def _nearest(points: gpd.GeoDataFrame, target: gpd.GeoDataFrame, name: str) -> pd.Series:
    p = points.to_crs(DISTANCE_CRS)
    t = target.to_crs(DISTANCE_CRS)[["geometry"]].reset_index(drop=True)
    joined = gpd.sjoin_nearest(p[["geometry"]], t, how="left", distance_col="distance_m")
    joined = joined.reset_index().sort_values(["index", "distance_m"]).drop_duplicates("index")
    return pd.Series(joined["distance_m"].to_numpy(), index=range(len(points)), name=f"distance_to_{name}_m")


def _summary(x: pd.Series) -> dict:
    v = pd.to_numeric(x, errors="coerce").dropna()
    return {
        "n": int(len(v)),
        "min_m": float(v.min()) if len(v) else None,
        "median_m": float(v.median()) if len(v) else None,
        "p90_m": float(v.quantile(0.90)) if len(v) else None,
        "p95_m": float(v.quantile(0.95)) if len(v) else None,
        "p99_m": float(v.quantile(0.99)) if len(v) else None,
        "max_m": float(v.max()) if len(v) else None,
    }


def main() -> None:
    origins = pd.read_csv(ORIGINS, low_memory=False)
    destinations = pd.read_csv(DESTINATIONS, low_memory=False)
    origin_source = pd.read_csv(ORIGIN_SOURCE, low_memory=False)
    services = pd.read_csv(SERVICES, low_memory=False)
    roads = gpd.read_file(ROADS)
    waterways = gpd.read_file(WATERWAYS)

    origin_points = _points(origins)
    destination_points = _points(destinations)

    origin_road = _nearest(origin_points, roads, "road")
    origin_water = _nearest(origin_points, waterways, "waterway")
    service_road = _nearest(destination_points, roads, "road")
    service_water = _nearest(destination_points, waterways, "waterway")

    origin_out = origins[[c for c in ["origin_id", "municipality_code", "municipality_name", "latitude", "longitude", "female_population"] if c in origins.columns]].copy()
    origin_out["distance_to_road_m"] = origin_road.values
    origin_out["distance_to_waterway_m"] = origin_water.values
    origin_meta = origin_source[[c for c in ["origin_id", "origin_method", "origin_validation_status", "eligible_residential_address_count"] if c in origin_source.columns]].drop_duplicates("origin_id")
    origin_out = origin_out.merge(origin_meta, on="origin_id", how="left", validate="one_to_one")
    origin_out["connector_semantics_status"] = "unresolved_physical_access_or_network_alignment"
    origin_out["travel_time_min"] = pd.NA

    service_out = destinations[[c for c in ["service_id", "physical_site_id", "service_type", "municipality_code", "municipality_name", "latitude", "longitude", "validation_status", "address_public"] if c in destinations.columns]].copy()
    service_out["distance_to_road_m"] = service_road.values
    service_out["distance_to_waterway_m"] = service_water.values
    service_out["connector_semantics_status"] = "unresolved_physical_access_or_network_alignment"
    service_out["travel_time_min"] = pd.NA

    OUT.mkdir(parents=True, exist_ok=True)
    origin_out.to_csv(OUT / "origin_access_connector_semantics.csv.gz", index=False, compression="gzip")
    service_out.to_csv(OUT / "service_access_connector_semantics.csv", index=False)

    origin_methods = origin_out.get("origin_method", pd.Series(dtype="string")).fillna("unknown").value_counts().to_dict()
    origin_validation = origin_out.get("origin_validation_status", pd.Series(dtype="string")).fillna("unknown").value_counts().to_dict()
    service_validation = service_out.get("validation_status", pd.Series(dtype="string")).fillna("unknown").value_counts().to_dict()
    manual_marker = service_out.get("validation_status", pd.Series(dtype="string")).astype("string").str.contains(
        "manual_operational_coordinates_accepted_2026-08-21", regex=False, na=False
    )

    audit = {
        "origin_count": int(len(origin_out)),
        "service_site_count": int(len(service_out)),
        "origin_coordinate_methods": {str(k): int(v) for k, v in origin_methods.items()},
        "origin_validation_status": {str(k): int(v) for k, v in origin_validation.items()},
        "service_validation_status": {str(k): int(v) for k, v in service_validation.items()},
        "service_sites_with_manual_operational_coordinate_marker": int(manual_marker.sum()),
        "origin_distance_summary": {
            "road": _summary(origin_out["distance_to_road_m"]),
            "waterway": _summary(origin_out["distance_to_waterway_m"]),
        },
        "service_distance_summary": {
            "road": _summary(service_out["distance_to_road_m"]),
            "waterway": _summary(service_out["distance_to_waterway_m"]),
        },
        "origin_representation": "sector-level representative residential point derived from CNEFE residential address coordinates; not a sector centroid",
        "service_representation": "validated or operationally accepted physical service-site coordinate",
        "origin_connector_rule_resolved": False,
        "service_connector_rule_resolved": False,
        "straight_line_distance_to_time_conversion_used": False,
        "universal_distance_cutoff_used": False,
        "nearest_geometry_promoted_automatically": False,
        "cartographic_alignment_assumed_statewide": False,
        "ready_for_empirical_access_connector_decision": True,
        "scientific_policy": (
            "This audit characterizes where routing-ready sector origins and service sites sit relative to the road and hydro networks and records coordinate provenance. "
            "Distances are descriptive only. A CNEFE-derived residential representative point is not automatically assumed to lie on a transport network, and a service-site coordinate is not automatically snapped as a zero-cost connector. "
            "No straight-line distance is converted to time, no universal proximity cutoff is adopted, and nearest geometry alone does not authorize routing."
        ),
    }
    (OUT / "access_connector_semantics_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
