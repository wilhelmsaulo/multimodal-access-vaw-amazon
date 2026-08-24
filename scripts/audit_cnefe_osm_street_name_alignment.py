from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA = ROOT / "artifacts" / "representative_origin_cnefe_metadata" / "representative_origin_cnefe_metadata.csv.gz"
DEFAULT_ORIGINS = ROOT / "data" / "processed" / "ibge" / "pa_cnefe_sector_origins_2022.csv"
DEFAULT_ROADS = ROOT / "artifacts" / "multimodal_graph_inputs" / "roads.gpkg"
DEFAULT_SECTORS = ROOT / "data" / "processed" / "ibge" / "pa_census_sectors_2022.gpkg"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "cnefe_osm_street_name_alignment"
METRIC_CRS = "EPSG:5880"

STREET_TYPES = {
    "RUA", "AV", "AVENIDA", "TV", "TRAV", "TRAVESSA", "ROD", "RODOVIA",
    "EST", "ESTRADA", "AL", "ALAMEDA", "PASS", "PASSAGEM", "PRACA", "PCA",
    "VIA", "VILA", "BECO", "RAMAL", "CAMINHO", "LADEIRA", "CONJUNTO",
}


def _ascii_upper(value: object) -> str:
    s = "" if pd.isna(value) else str(value)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def _core_name(value: object) -> str:
    tokens = _ascii_upper(value).split()
    while tokens and tokens[0] in STREET_TYPES:
        tokens = tokens[1:]
    return " ".join(tokens)


def _cnefe_full(row: pd.Series) -> str:
    parts = [
        row.get("representative_cnefe_street_type"),
        row.get("representative_cnefe_street_title"),
        row.get("representative_cnefe_street_name"),
    ]
    return _ascii_upper(" ".join(str(x) for x in parts if pd.notna(x) and str(x).strip()))


def _quantiles(values: pd.Series) -> dict[str, float | None]:
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return {k: None for k in ["min", "p25", "median", "p75", "p90", "p95", "p99", "max"]}
    q = s.quantile([0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0])
    return {
        "min": float(q.loc[0.0]), "p25": float(q.loc[0.25]), "median": float(q.loc[0.5]),
        "p75": float(q.loc[0.75]), "p90": float(q.loc[0.9]), "p95": float(q.loc[0.95]),
        "p99": float(q.loc[0.99]), "max": float(q.loc[1.0]),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    p.add_argument("--origins", type=Path, default=DEFAULT_ORIGINS)
    p.add_argument("--roads", type=Path, default=DEFAULT_ROADS)
    p.add_argument("--sectors", type=Path, default=DEFAULT_SECTORS)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = p.parse_args()

    meta = pd.read_csv(args.metadata, dtype={"origin_id": "string"}, low_memory=False)
    meta = meta[meta["full_cnefe_metadata_match"].fillna(False).astype(bool)].copy()
    origins = pd.read_csv(args.origins, dtype={"origin_id": "string"}, low_memory=False)
    origins = origins[["origin_id", "latitude", "longitude"]].drop_duplicates("origin_id")
    meta = meta.merge(origins, on="origin_id", how="left", validate="one_to_one")
    meta["municipality_code"] = meta["origin_id"].astype("string").str[:7]
    meta["cnefe_full_norm"] = meta.apply(_cnefe_full, axis=1)
    meta["cnefe_core_norm"] = meta["representative_cnefe_street_name"].map(_core_name)
    meta = meta[meta["cnefe_core_norm"].ne("")].copy()

    sectors = gpd.read_file(args.sectors, layer="pa_census_sectors_2022", columns=["CD_MUN", "geometry"])
    municipalities = sectors[["CD_MUN", "geometry"]].dissolve(by="CD_MUN", as_index=False)

    roads = gpd.read_file(args.roads, layer="roads", columns=["osm_id", "highway", "name", "geometry"])
    roads = roads[roads["name"].notna() & roads.geometry.notna() & ~roads.geometry.is_empty].copy()
    roads["osm_name_norm"] = roads["name"].map(_ascii_upper)
    roads["osm_core_norm"] = roads["name"].map(_core_name)
    roads = roads[roads["osm_core_norm"].ne("")].copy()
    roads["road_row_id"] = roads.index.astype(int)

    # Municipality membership is used only to restrict candidate names to the same official IBGE municipality.
    rp = roads[["road_row_id", "osm_id", "highway", "name", "osm_name_norm", "osm_core_norm", "geometry"]].copy()
    rp["geometry"] = rp.geometry.representative_point()
    if rp.crs != municipalities.crs:
        rp = rp.to_crs(municipalities.crs)
    joined = gpd.sjoin(rp, municipalities[["CD_MUN", "geometry"]], how="left", predicate="within")
    joined["municipality_code"] = joined["CD_MUN"].astype("string")

    strict_keys = set(zip(joined["municipality_code"].astype(str), joined["osm_name_norm"].astype(str)))
    core_keys = set(zip(joined["municipality_code"].astype(str), joined["osm_core_norm"].astype(str)))
    meta["strict_full_name_match_same_municipality"] = [
        (str(m), str(n)) in strict_keys for m, n in zip(meta["municipality_code"], meta["cnefe_full_norm"])
    ]
    meta["core_name_match_same_municipality"] = [
        (str(m), str(n)) in core_keys for m, n in zip(meta["municipality_code"], meta["cnefe_core_norm"])
    ]
    meta["nominal_alignment_evidence"] = "none"
    meta.loc[meta["core_name_match_same_municipality"], "nominal_alignment_evidence"] = "core_name_same_municipality"
    meta.loc[meta["strict_full_name_match_same_municipality"], "nominal_alignment_evidence"] = "strict_full_name_same_municipality"
    meta["any_nominal_match_same_municipality"] = (
        meta["strict_full_name_match_same_municipality"] | meta["core_name_match_same_municipality"]
    )

    # Measure distance to same-name OSM geometry in a metric CRS. This is descriptive evidence only:
    # no threshold is defined and no feature is selected or promoted as a connector.
    road_mun = joined[["road_row_id", "municipality_code", "osm_name_norm", "osm_core_norm"]].dropna(subset=["municipality_code"])
    roads_metric = roads.to_crs(METRIC_CRS).set_index("road_row_id")
    strict_geoms: dict[tuple[str, str], object] = {}
    core_geoms: dict[tuple[str, str], object] = {}
    for key, group in road_mun.groupby(["municipality_code", "osm_name_norm"], sort=False):
        strict_geoms[(str(key[0]), str(key[1]))] = unary_union(roads_metric.loc[group["road_row_id"].astype(int), "geometry"].tolist())
    for key, group in road_mun.groupby(["municipality_code", "osm_core_norm"], sort=False):
        core_geoms[(str(key[0]), str(key[1]))] = unary_union(roads_metric.loc[group["road_row_id"].astype(int), "geometry"].tolist())

    origin_gdf = gpd.GeoDataFrame(
        meta[["origin_id"]].copy(),
        geometry=gpd.points_from_xy(pd.to_numeric(meta["longitude"], errors="coerce"), pd.to_numeric(meta["latitude"], errors="coerce")),
        crs="EPSG:4674",
    ).to_crs(METRIC_CRS)
    points = dict(zip(origin_gdf["origin_id"].astype(str), origin_gdf.geometry))

    strict_dist: list[float | None] = []
    core_dist: list[float | None] = []
    for row in meta.itertuples(index=False):
        point = points.get(str(row.origin_id))
        sd = None
        cd = None
        if point is not None and row.strict_full_name_match_same_municipality:
            geom = strict_geoms.get((str(row.municipality_code), str(row.cnefe_full_norm)))
            if geom is not None:
                sd = float(point.distance(geom))
        if point is not None and row.core_name_match_same_municipality:
            geom = core_geoms.get((str(row.municipality_code), str(row.cnefe_core_norm)))
            if geom is not None:
                cd = float(point.distance(geom))
        strict_dist.append(sd)
        core_dist.append(cd)
    meta["distance_to_same_strict_name_osm_m"] = strict_dist
    meta["distance_to_same_core_name_osm_m"] = core_dist
    meta["distance_to_any_same_name_osm_m"] = meta[[
        "distance_to_same_strict_name_osm_m", "distance_to_same_core_name_osm_m"
    ]].min(axis=1, skipna=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_cols = [
        "origin_id", "representative_cnefe_locality", "representative_cnefe_street_type",
        "representative_cnefe_street_title", "representative_cnefe_street_name",
        "strict_full_name_match_same_municipality", "core_name_match_same_municipality",
        "any_nominal_match_same_municipality", "nominal_alignment_evidence",
        "distance_to_same_strict_name_osm_m", "distance_to_same_core_name_osm_m",
        "distance_to_any_same_name_osm_m",
    ]
    meta[out_cols].to_csv(args.output_dir / "cnefe_osm_street_name_alignment.csv.gz", index=False, compression="gzip")

    n = len(meta)
    strict = int(meta["strict_full_name_match_same_municipality"].sum())
    core = int(meta["core_name_match_same_municipality"].sum())
    any_match = int(meta["any_nominal_match_same_municipality"].sum())
    audit = {
        "origins_with_cnefe_street_metadata": int(n),
        "named_osm_road_features": int(len(roads)),
        "named_osm_road_features_assigned_to_municipality": int(joined["CD_MUN"].notna().sum()),
        "strict_full_name_matches_same_municipality": strict,
        "strict_full_name_match_fraction": float(strict / n) if n else None,
        "core_name_matches_same_municipality": core,
        "core_name_match_fraction": float(core / n) if n else None,
        "any_nominal_matches_same_municipality": any_match,
        "any_nominal_match_fraction": float(any_match / n) if n else None,
        "same_name_distance_m_quantiles": _quantiles(meta["distance_to_any_same_name_osm_m"]),
        "strict_same_name_distance_m_quantiles": _quantiles(meta["distance_to_same_strict_name_osm_m"]),
        "core_same_name_distance_m_quantiles": _quantiles(meta["distance_to_same_core_name_osm_m"]),
        "municipality_restriction": "IBGE 2022 municipality geometry dissolved from census sectors; OSM line representative point used only for municipal membership",
        "name_normalization": "uppercase ASCII, punctuation/whitespace normalization; core match additionally removes only standardized leading street-type tokens",
        "distance_measurement_crs": METRIC_CRS,
        "same_name_distance_is_descriptive_only": True,
        "coordinate_changed": False,
        "distance_cutoff_used": False,
        "network_connector_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "Nominal CNEFE-to-OSM agreement and distance to the same-name OSM geometry are evidence of cartographic alignment only. "
            "Matches are restricted to the same official IBGE municipality. Distance distributions are measured without defining a cutoff. "
            "No road feature is selected, no connector is promoted, and no travel time is assigned by this audit."
        ),
    }
    (args.output_dir / "cnefe_osm_street_name_alignment_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
