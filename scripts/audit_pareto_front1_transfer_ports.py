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
CLASSIFICATION = Path("artifacts/antaq_physical_transfer_port_classification/pa_physical_transfer_port_ranked_candidates.csv")
OUT = Path("artifacts/antaq_pareto_front1_transfer_port_audit")
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


def value(row: pd.Series, df: pd.DataFrame, *names: str) -> object:
    for name in names:
        c = col_ci(df, name)
        if c and c in row.index:
            v = row[c]
            if not pd.isna(v):
                return v
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cls = pd.read_csv(CLASSIFICATION)
    front1 = cls[pd.to_numeric(cls["pareto_front"], errors="coerce") == 1].copy()
    if front1.empty:
        raise RuntimeError("No Pareto front-1 candidates")

    ports = read_zip(PORT_ZIP)
    estado = col_ci(ports, "estado")
    cidade = col_ci(ports, "cidade")
    if not estado or not cidade:
        raise RuntimeError("Current ANTAQ port layer lacks estado/cidade")
    ports = ports[ports[estado].map(norm).isin({"pa", "para"})].copy()
    ports = ports[ports.geometry.notna() & ~ports.geometry.is_empty].copy()
    if ports.crs is None:
        ports = ports.set_crs("EPSG:4674")
    ports = ports.reset_index(drop=False).rename(columns={"index": "source_row_index"})
    ports_m = ports.to_crs(DIST_CRS)

    water_parts: list[gpd.GeoDataFrame] = []
    for z in sorted(WATER_DIR.glob("*.zip")):
        g = read_zip(z)
        om = col_ci(g, "mun_origem")
        dm = col_ci(g, "mun_estino")
        if not om or not dm:
            continue
        os = col_ci(g, "est_origem")
        ds = col_ci(g, "est_estino")
        tmp = g.copy()
        tmp["dataset"] = z.name
        tmp["origin_municipality_norm"] = tmp[om].map(norm)
        tmp["destination_municipality_norm"] = tmp[dm].map(norm)
        tmp["origin_state_norm"] = tmp[os].map(norm) if os else ""
        tmp["destination_state_norm"] = tmp[ds].map(norm) if ds else ""
        if tmp.crs is None:
            tmp = tmp.set_crs("EPSG:4674")
        water_parts.append(tmp.to_crs(DIST_CRS))
    if not water_parts:
        raise RuntimeError("No compatible ANTAQ waterway datasets")
    water = gpd.GeoDataFrame(pd.concat(water_parts, ignore_index=True), geometry="geometry", crs=DIST_CRS)

    rows: list[dict[str, object]] = []
    for _, c in front1.sort_values("evidence_rank").iterrows():
        pi = int(c["port_index"])
        if pi < 0 or pi >= len(ports_m):
            raise RuntimeError(f"port_index out of range: {pi}")
        p = ports_m.iloc[pi]
        municipality = norm(c["municipality"])
        compatible = water[
            ((water["origin_municipality_norm"] == municipality) & water["origin_state_norm"].isin({"", "pa", "para"})) |
            ((water["destination_municipality_norm"] == municipality) & water["destination_state_norm"].isin({"", "pa", "para"}))
        ].copy()
        if compatible.empty:
            raise RuntimeError(f"No compatible hydro geometry for {c['port_name']}")
        d = compatible.geometry.distance(p.geometry)
        j = d.idxmin()
        h = compatible.loc[j]
        hdf = compatible
        rows.append({
            "evidence_rank": int(c["evidence_rank"]),
            "pareto_front": int(c["pareto_front"]),
            "port_index": pi,
            "port_name": str(c["port_name"]).strip(),
            "municipality": municipality,
            "hydro_distance_m": float(c["hydro_distance_m"]),
            "road_distance_m": float(c["road_distance_m"]),
            "matched_hydro_distance_recomputed_m": float(d.loc[j]),
            "matched_hydro_dataset": str(h["dataset"]),
            "matched_hydro_origin": value(h, hdf, "mun_origem"),
            "matched_hydro_origin_state": value(h, hdf, "est_origem"),
            "matched_hydro_destination": value(h, hdf, "mun_estino"),
            "matched_hydro_destination_state": value(h, hdf, "est_estino"),
            "matched_hydro_river": value(h, hdf, "nome_rio", "rio", "nome"),
            "matched_hydro_time": value(h, hdf, "tempo"),
            "matched_hydro_length": value(h, hdf, "extensao"),
            "administrative_endpoint_match": True,
            "connector_promoted": False,
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "pareto_front1_nominal_audit.csv", index=False)
    audit = {
        "pareto_front1_count": int(len(out)),
        "candidate_names": out["port_name"].tolist(),
        "all_have_administrative_endpoint_match": bool(out["administrative_endpoint_match"].all()),
        "all_recomputed_hydro_distances_consistent": bool(((out["hydro_distance_m"] - out["matched_hydro_distance_recomputed_m"]).abs() < 1e-6).all()),
        "connector_promoted": False,
        "decision_status": "priority_candidates_only_pending_transfer_rule",
        "scientific_policy": "Pareto front-1 identifies priority candidates for validation only. This audit re-identifies the nearest municipality/UF-compatible ANTAQ hydro geometry and records nominal provenance. It does not promote a connector, infer transfer time, or introduce a fixed distance threshold.",
    }
    (OUT / "pareto_front1_nominal_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"audit": audit, "rows": rows}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
