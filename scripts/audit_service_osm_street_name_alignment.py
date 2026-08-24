from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

METRIC_CRS = "EPSG:5880"
STREET_TYPES = {"RUA","AV","AVENIDA","TV","TRAV","TRAVESSA","ROD","RODOVIA","EST","ESTRADA","AL","ALAMEDA","PASS","PASSAGEM","PRACA","PCA","VIA","BECO","RAMAL","CAMINHO","LADEIRA"}


def norm(value: object) -> str:
    s = "" if pd.isna(value) else str(value)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def core(value: object) -> str:
    t = norm(value).split()
    while t and t[0] in STREET_TYPES:
        t = t[1:]
    return " ".join(t)


def address_street(value: object) -> str:
    # Conservative parse: keep only text before the first comma; this avoids unit number/SN.
    s = "" if pd.isna(value) else str(value)
    return s.split(",", 1)[0].strip()


def q(s: pd.Series) -> dict:
    v = pd.to_numeric(s, errors="coerce").dropna()
    if v.empty:
        return {"n": 0}
    return {"n": int(len(v)), "min": float(v.min()), "median": float(v.median()), "p90": float(v.quantile(.9)), "p95": float(v.quantile(.95)), "p99": float(v.quantile(.99)), "max": float(v.max())}


def main() -> None:
    services = pd.read_csv("artifacts/routing_inputs/destinations_for_routing.csv", low_memory=False)
    access = pd.read_csv("artifacts/service_local_access_primary_motor_audit/service_local_access_to_primary_motor.csv.gz", low_memory=False)
    roads = gpd.read_file("artifacts/multimodal_graph_inputs/roads.gpkg", layer="roads", columns=["osm_id","name","geometry"])
    sectors = gpd.read_file("data/processed/ibge/pa_census_sectors_2022.gpkg", layer="pa_census_sectors_2022", columns=["CD_MUN","geometry"])
    municipalities = sectors[["CD_MUN","geometry"]].dissolve(by="CD_MUN", as_index=False)

    svc = services.merge(access[["service_id","nearest_osm_node_in_primary_motor_graph"]], on="service_id", how="left", validate="one_to_one")
    svc["street_text"] = svc["address_public"].map(address_street)
    svc["street_norm"] = svc["street_text"].map(norm)
    svc["street_core_norm"] = svc["street_text"].map(core)

    sg = gpd.GeoDataFrame(svc.copy(), geometry=gpd.points_from_xy(pd.to_numeric(svc["longitude"], errors="coerce"), pd.to_numeric(svc["latitude"], errors="coerce")), crs="EPSG:4674")
    sj = gpd.sjoin(sg, municipalities[["CD_MUN","geometry"]], how="left", predicate="within")
    svc["spatial_municipality_code"] = sj["CD_MUN"].astype("string").to_numpy()
    # Prefer explicit routing-input municipality code when available; spatial membership only fills missing values.
    explicit = pd.to_numeric(svc.get("municipality_code"), errors="coerce").astype("Int64").astype("string")
    svc["municipality_code_for_match"] = explicit.where(explicit.notna(), svc["spatial_municipality_code"])

    roads = roads[roads["name"].notna() & roads.geometry.notna() & ~roads.geometry.is_empty].copy()
    roads["name_norm"] = roads["name"].map(norm)
    roads["core_norm"] = roads["name"].map(core)
    roads["rid"] = roads.index.astype(int)
    rp = roads[["rid","name_norm","core_norm","geometry"]].copy()
    rp["geometry"] = rp.geometry.representative_point()
    rp = rp.to_crs(municipalities.crs)
    rj = gpd.sjoin(rp, municipalities[["CD_MUN","geometry"]], how="left", predicate="within")
    rj["mun"] = rj["CD_MUN"].astype("string")
    strict_keys = set(zip(rj["mun"].astype(str), rj["name_norm"].astype(str)))
    core_keys = set(zip(rj["mun"].astype(str), rj["core_norm"].astype(str)))
    svc["strict_address_street_match_same_municipality"] = [(str(m), str(n)) in strict_keys and bool(n) for m,n in zip(svc["municipality_code_for_match"], svc["street_norm"])]
    svc["core_address_street_match_same_municipality"] = [(str(m), str(n)) in core_keys and bool(n) for m,n in zip(svc["municipality_code_for_match"], svc["street_core_norm"])]
    svc["any_address_street_match_same_municipality"] = svc["strict_address_street_match_same_municipality"] | svc["core_address_street_match_same_municipality"]

    road_m = roads.to_crs(METRIC_CRS).set_index("rid")
    rm = rj[["rid","mun","name_norm","core_norm"]].dropna(subset=["mun"])
    core_geoms = {}
    for key, g in rm.groupby(["mun","core_norm"], sort=False):
        core_geoms[(str(key[0]),str(key[1]))] = unary_union(road_m.loc[g["rid"].astype(int),"geometry"].tolist())
    pts = sg.to_crs(METRIC_CRS).geometry.to_list()
    dist=[]
    for i,row in svc.iterrows():
        geom = core_geoms.get((str(row["municipality_code_for_match"]), str(row["street_core_norm"]))) if row["core_address_street_match_same_municipality"] else None
        dist.append(float(pts[i].distance(geom)) if geom is not None else None)
    svc["distance_to_same_core_address_osm_m"] = dist

    direct = svc["nearest_osm_node_in_primary_motor_graph"].fillna(False).astype(bool)
    outdir=Path("artifacts/service_osm_street_name_alignment")
    outdir.mkdir(parents=True, exist_ok=True)
    svc.to_csv(outdir/"service_osm_street_name_alignment.csv.gz", index=False, compression="gzip")
    audit={
        "service_count": int(len(svc)),
        "direct_primary_service_count": int(direct.sum()),
        "services_with_nonempty_address_street": int(svc["street_core_norm"].ne("").sum()),
        "any_address_street_match_same_municipality_count": int(svc["any_address_street_match_same_municipality"].sum()),
        "direct_primary_with_address_street_match_count": int((direct & svc["any_address_street_match_same_municipality"]).sum()),
        "same_name_distance_m": q(svc["distance_to_same_core_address_osm_m"]),
        "address_parse_rule": "text before first comma only; street-type tokens removed only for core-name comparison",
        "municipality_rule": "explicit routing municipality code when available, otherwise official IBGE municipality polygon membership",
        "distance_cutoff_used": False,
        "connector_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": "Public service addresses are compared with named OSM roads only within the same municipality as independent nominal cartographic evidence. Address parsing is conservative and distances to same-name geometry are descriptive only. No name match or distance promotes a connector or assigns travel time in this audit."
    }
    (outdir/"service_osm_street_name_alignment_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
