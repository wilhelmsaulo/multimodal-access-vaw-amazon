from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

TARGET_CRS = "EPSG:4674"
PA_BBOX = box(-58.95, -9.95, -46.0, 2.8)
PA_BBOX_TUPLE = (-58.95, -9.95, -46.0, 2.8)


def _extract_archives(source_dir: Path, workdir: Path) -> list[Path]:
    roots: list[Path] = []
    for p in sorted(source_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() == ".zip" and zipfile.is_zipfile(p):
            target = workdir / p.stem
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(p) as zf:
                zf.extractall(target)
            roots.append(target)
        elif p.suffix.lower() in {".shp", ".geojson", ".json", ".gpkg", ".kml", ".pbf"}:
            roots.append(p)
    return roots


def _read_pbf_roads(path: Path) -> list[gpd.GeoDataFrame]:
    try:
        g = gpd.read_file(
            path,
            layer="lines",
            bbox=PA_BBOX_TUPLE,
            engine="pyogrio",
        )
    except Exception:
        return []
    if g.empty:
        return []
    if "highway" in g.columns:
        g = g[g["highway"].notna()].copy()
    else:
        return []
    return [g] if not g.empty else []


def _read_geodata(path: Path) -> list[gpd.GeoDataFrame]:
    frames: list[gpd.GeoDataFrame] = []
    if path.suffix.lower() == ".pbf":
        return _read_pbf_roads(path)
    candidates: list[Path]
    if path.is_dir():
        candidates = [p for p in path.rglob("*") if p.suffix.lower() in {".shp", ".geojson", ".json", ".gpkg", ".kml"}]
    else:
        candidates = [path]
    for p in candidates:
        try:
            if p.suffix.lower() == ".gpkg":
                import pyogrio
                for layer, _ in pyogrio.list_layers(p):
                    g = gpd.read_file(p, layer=layer)
                    if not g.empty:
                        frames.append(g)
            else:
                g = gpd.read_file(p)
                if not g.empty:
                    frames.append(g)
        except Exception:
            continue
    return frames


def _find_col(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lookup = {str(c).lower(): str(c) for c in columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def _canonicalize_antaq_waterways(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    cols = [str(c) for c in g.columns if c != "geometry"]
    mapping = {
        "hydro_id": ("idhidrovia", "idantaq"),
        "river_name": ("nome_rio",),
        "origin_municipality": ("mun_origem",),
        "origin_state": ("est_origem",),
        "destination_municipality": ("mun_estino", "mun_destino"),
        "destination_state": ("est_estino", "est_destino"),
        "navigation_type": ("navegacao",),
        "segment_type": ("tipo",),
        "reported_length_km": ("extensao",),
        "reported_time": ("tempo",),
    }
    out = g[["geometry"]].copy()
    for canonical, candidates in mapping.items():
        source = _find_col(cols, candidates)
        out[canonical] = g[source].values if source else pd.NA
    return gpd.GeoDataFrame(out, geometry="geometry", crs=g.crs)


def _normalize(frames: list[gpd.GeoDataFrame], source_id: str, geometry_family: str) -> gpd.GeoDataFrame:
    kept: list[gpd.GeoDataFrame] = []
    for g in frames:
        if g.crs is None:
            continue
        g = g.to_crs(TARGET_CRS)
        g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
        if geometry_family == "line":
            g = g[g.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
        else:
            g["geometry"] = g.geometry.representative_point()
        if g.empty:
            continue
        g = g[g.geometry.intersects(PA_BBOX)].copy()
        if g.empty:
            continue
        if source_id == "antaq_waterways":
            g = _canonicalize_antaq_waterways(g)
        g["source_id"] = source_id
        kept.append(g)
    if not kept:
        return gpd.GeoDataFrame({"source_id": pd.Series(dtype="string")}, geometry=[], crs=TARGET_CRS)

    if source_id == "antaq_waterways":
        canonical_cols = [
            "hydro_id", "river_name", "origin_municipality", "origin_state",
            "destination_municipality", "destination_state", "navigation_type",
            "segment_type", "reported_length_km", "reported_time", "source_id", "geometry",
        ]
        slim = [x.reindex(columns=canonical_cols).copy() for x in kept]
    else:
        cols = sorted(set.intersection(*(set(x.columns) for x in kept)) - {"geometry"})
        cols = [c for c in cols if c != "source_id"][:25]
        slim = [x[[*cols, "source_id", "geometry"]].copy() for x in kept]
    return gpd.GeoDataFrame(pd.concat(slim, ignore_index=True), geometry="geometry", crs=TARGET_CRS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/transport"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/multimodal_graph_inputs"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    specs = {
        "roads": ("osm_roads", "line"),
        "waterways": ("antaq_waterways", "line"),
        "ports": ("antaq_ports", "point"),
        "airports": ("decea_airports", "point"),
    }
    audit: dict[str, object] = {
        "target_crs": TARGET_CRS,
        "layers": {},
        "road_network_policy": (
            "OpenStreetMap is the primary routable terrestrial network because door-to-door routing requires local streets and access roads; "
            "DNIT/SNV remains the official federal-road reference for validation, not a complete door-to-door graph."
        ),
        "policy": "Canonical geometry preparation only; no travel-time weights or unsupported modal speeds are assigned.",
    }

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for layer_name, (source_id, family) in specs.items():
            source_dir = args.raw_dir / source_id
            roots = _extract_archives(source_dir, work / source_id) if source_dir.exists() else []
            frames: list[gpd.GeoDataFrame] = []
            for root in roots:
                frames.extend(_read_geodata(root))
            out = _normalize(frames, source_id, family)
            path = args.output_dir / f"{layer_name}.gpkg"
            if not out.empty:
                out.to_file(path, layer=layer_name, driver="GPKG")
            audit["layers"][layer_name] = {
                "source_id": source_id,
                "features": int(len(out)),
                "geometry_types": sorted(out.geometry.geom_type.unique().tolist()) if not out.empty else [],
                "ready": bool(len(out) > 0),
                "output": str(path) if not out.empty else None,
                "columns": [str(c) for c in out.columns if c != "geometry"],
            }

    required = ["roads", "waterways", "ports", "airports"]
    audit["all_required_modal_layers_ready"] = all(audit["layers"][k]["ready"] for k in required)
    (args.output_dir / "graph_input_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
