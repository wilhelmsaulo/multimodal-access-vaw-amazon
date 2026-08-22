from __future__ import annotations

import json
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

PORT_ZIP = Path("data/raw/transport/antaq_ports/Instalaesporturias06052025.zip")
WATER_DIR = Path("data/raw/transport/antaq_waterways")
OUT = Path("artifacts/antaq_same_municipality_connector_distances")
DISTANCE_CRS = "EPSG:5880"
TARGET_CRS = "EPSG:4674"


def norm_text(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def read_zip(path: Path) -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(root)
        shp = next(iter(root.rglob("*.shp")), None)
        if shp is None:
            raise RuntimeError(f"No shapefile in {path}")
        return gpd.read_file(shp)


def find_col(cols: list[str], wanted: str) -> str | None:
    nw = norm_text(wanted)
    for c in cols:
        if norm_text(c) == nw:
            return c
    return None


def endpoint_point(geom, side: str):
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "LineString":
        coords = list(geom.coords)
        if not coords:
            return None
        xy = coords[0] if side == "origin" else coords[-1]
        return Point(xy)
    if geom.geom_type == "MultiLineString":
        parts = list(geom.geoms)
        if not parts:
            return None
        line = parts[0] if side == "origin" else parts[-1]
        coords = list(line.coords)
        if not coords:
            return None
        xy = coords[0] if side == "origin" else coords[-1]
        return Point(xy)
    return None


def q(series: pd.Series, p: float):
    return float(series.quantile(p)) if len(series) else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    ports = read_zip(PORT_ZIP).to_crs(TARGET_CRS)
    pcols = list(ports.columns)
    pmun = find_col(pcols, "cidade")
    puf = find_col(pcols, "estado")
    pname = find_col(pcols, "nome")
    pid = find_col(pcols, "idseq")
    if not pmun or not puf:
        raise RuntimeError("Current ANTAQ port layer lacks cidade/estado fields")

    ports = ports.copy()
    ports["municipality_norm"] = ports[pmun].map(norm_text)
    ports["state_norm"] = ports[puf].map(norm_text)
    ports["port_name"] = ports[pname].astype(str) if pname else ""
    ports["port_id"] = ports[pid].astype(str) if pid else ports.index.astype(str)
    ports = ports[ports.geometry.notna() & ~ports.geometry.is_empty].copy()
    ports_m = ports.to_crs(DISTANCE_CRS)

    endpoint_records: list[dict[str, object]] = []
    for z in sorted(WATER_DIR.glob("*.zip")):
        g = read_zip(z).to_crs(TARGET_CRS)
        cols = list(g.columns)
        om = find_col(cols, "mun_origem")
        ou = find_col(cols, "est_origem")
        dm = find_col(cols, "mun_estino")
        du = find_col(cols, "est_estino")
        hid = find_col(cols, "idhidrovia")
        river = find_col(cols, "nome_rio") or find_col(cols, "nome")
        if not om or not dm:
            continue
        for idx, row in g.iterrows():
            for side, mc, uc in (("origin", om, ou), ("destination", dm, du)):
                pt = endpoint_point(row.geometry, side)
                if pt is None:
                    continue
                municipality = norm_text(row[mc])
                state = norm_text(row[uc]) if uc else ""
                if not municipality:
                    continue
                endpoint_records.append({
                    "dataset": z.name,
                    "row": int(idx),
                    "side": side,
                    "hydro_id": str(row[hid]) if hid else "",
                    "river_name": str(row[river]) if river else "",
                    "municipality": municipality,
                    "state": state,
                    "geometry": pt,
                })

    endpoints = gpd.GeoDataFrame(endpoint_records, geometry="geometry", crs=TARGET_CRS)
    endpoints_m = endpoints.to_crs(DISTANCE_CRS)

    rows: list[dict[str, object]] = []
    for _, ep in endpoints_m.iterrows():
        cand = ports_m[ports_m["municipality_norm"].eq(ep["municipality"])]
        if ep["state"]:
            exact = cand[cand["state_norm"].eq(ep["state"])]
            if len(exact):
                cand = exact
        if cand.empty:
            rows.append({**ep.drop(labels="geometry").to_dict(), "matched": False, "port_id": "", "port_name": "", "distance_m": None})
            continue
        distances = cand.geometry.distance(ep.geometry)
        j = distances.idxmin()
        p = cand.loc[j]
        rows.append({
            **ep.drop(labels="geometry").to_dict(),
            "matched": True,
            "port_id": p["port_id"],
            "port_name": p["port_name"],
            "distance_m": float(distances.loc[j]),
        })

    df = pd.DataFrame(rows)
    matched = df.loc[df["matched"] & df["distance_m"].notna(), "distance_m"]
    audit = {
        "port_source": PORT_ZIP.name,
        "endpoint_rows_total": int(len(df)),
        "endpoint_rows_with_same_municipality_port": int(df["matched"].sum()),
        "coverage_fraction": float(df["matched"].mean()) if len(df) else 0.0,
        "distance_m": {
            "min": float(matched.min()) if len(matched) else None,
            "p25": q(matched, 0.25),
            "median": q(matched, 0.50),
            "p75": q(matched, 0.75),
            "p90": q(matched, 0.90),
            "p95": q(matched, 0.95),
            "p99": q(matched, 0.99),
            "max": float(matched.max()) if len(matched) else None,
        },
        "within_distance_counts": {
            "100m": int((matched <= 100).sum()),
            "250m": int((matched <= 250).sum()),
            "500m": int((matched <= 500).sum()),
            "1000m": int((matched <= 1000).sum()),
            "2000m": int((matched <= 2000).sum()),
            "5000m": int((matched <= 5000).sum()),
            "10000m": int((matched <= 10000).sum()),
        },
        "connector_promoted": False,
        "scientific_policy": (
            "Distances are calculated only after exact official municipality/state compatibility between ANTAQ waterway endpoints "
            "and the current 2025 ANTAQ port-installation layer. This audit describes the empirical physical-distance distribution; "
            "it does not select or promote a distance threshold and does not treat same-municipality membership alone as proof of transfer."
        ),
        "ready_for_connector_distance_rule_decision": True,
    }
    df.to_csv(OUT / "same_municipality_port_endpoint_distances.csv", index=False)
    (OUT / "same_municipality_connector_distance_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
