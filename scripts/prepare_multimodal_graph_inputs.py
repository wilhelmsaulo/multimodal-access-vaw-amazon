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
        elif p.suffix.lower() in {".shp", ".geojson", ".json", ".gpkg", ".kml"}:
            roots.append(p)
    return roots


def _read_geodata(path: Path) -> list[gpd.GeoDataFrame]:
    frames: list[gpd.GeoDataFrame] = []
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
        g["source_id"] = source_id
        kept.append(g)
    if not kept:
        return gpd.GeoDataFrame({"source_id": pd.Series(dtype="string")}, geometry=[], crs=TARGET_CRS)
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
        "roads": ("dnit_roads", "line"),
        "waterways": ("antaq_waterways", "line"),
        "ports": ("antaq_ports", "point"),
        "airports": ("decea_airports", "point"),
    }
    audit: dict[str, object] = {"target_crs": TARGET_CRS, "layers": {}, "policy": "Canonical geometry preparation only; no travel-time weights or unsupported modal speeds are assigned."}

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
            }

    required = ["roads", "waterways", "ports", "airports"]
    audit["all_required_modal_layers_ready"] = all(audit["layers"][k]["ready"] for k in required)
    (args.output_dir / "graph_input_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
