from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Geod
from shapely.geometry import LineString, Point

PA_BBOX = (-58.95, -9.95, -46.0, 2.8)
TARGET_CRS = "EPSG:4674"
DISTANCE_CRS = "EPSG:5880"
GEOD = Geod(ellps="GRS80")


def _inside_pa_bbox(lon: float, lat: float) -> bool:
    xmin, ymin, xmax, ymax = PA_BBOX
    return xmin <= lon <= xmax and ymin <= lat <= ymax


def _geodesic_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    _, _, distance = GEOD.inv(a[0], a[1], b[0], b[1])
    return float(distance)


def build_osm_road_graph(pbf: Path, output_dir: Path) -> dict[str, object]:
    import osmium

    output_dir.mkdir(parents=True, exist_ok=True)
    nodes: dict[int, tuple[float, float]] = {}
    edges: list[dict[str, object]] = []
    used_nodes: set[int] = set()
    highway_counts: dict[str, int] = defaultdict(int)

    class Handler(osmium.SimpleHandler):
        def way(self, w):
            highway = w.tags.get("highway")
            if not highway or len(w.nodes) < 2:
                return
            node_rows: list[tuple[int, float, float]] = []
            try:
                for n in w.nodes:
                    if not n.location.valid():
                        return
                    node_rows.append((int(n.ref), float(n.lon), float(n.lat)))
            except Exception:
                return

            for (u, lon1, lat1), (v, lon2, lat2) in zip(node_rows[:-1], node_rows[1:]):
                mid_lon = (lon1 + lon2) / 2.0
                mid_lat = (lat1 + lat2) / 2.0
                if not _inside_pa_bbox(mid_lon, mid_lat):
                    continue
                nodes[u] = (lon1, lat1)
                nodes[v] = (lon2, lat2)
                used_nodes.update((u, v))
                edges.append(
                    {
                        "way_id": int(w.id),
                        "u": u,
                        "v": v,
                        "highway": highway,
                        "oneway": w.tags.get("oneway"),
                        "junction": w.tags.get("junction"),
                        "access": w.tags.get("access"),
                        "motor_vehicle": w.tags.get("motor_vehicle"),
                        "surface": w.tags.get("surface"),
                        "maxspeed_raw": w.tags.get("maxspeed"),
                        "length_m": _geodesic_m((lon1, lat1), (lon2, lat2)),
                    }
                )
                highway_counts[highway] += 1

    h = Handler()
    h.apply_file(str(pbf), locations=True)

    node_records = [
        {"node_id": node_id, "longitude": xy[0], "latitude": xy[1]}
        for node_id, xy in nodes.items()
        if node_id in used_nodes
    ]
    node_df = pd.DataFrame(node_records)
    edge_df = pd.DataFrame(edges)
    node_path = output_dir / "road_nodes.csv.gz"
    edge_path = output_dir / "road_edges.csv.gz"
    node_df.to_csv(node_path, index=False, compression="gzip")
    edge_df.to_csv(edge_path, index=False, compression="gzip")

    return {
        "nodes": int(len(node_df)),
        "edges": int(len(edge_df)),
        "ways": int(edge_df["way_id"].nunique()) if not edge_df.empty else 0,
        "total_length_km": float(edge_df["length_m"].sum() / 1000.0) if not edge_df.empty else 0.0,
        "highway_edge_counts": dict(sorted(highway_counts.items())),
        "nodes_file": str(node_path),
        "edges_file": str(edge_path),
        "topology_basis": "Native OSM way-node topology; consecutive OSM nodes become structural road edges.",
        "weight_policy": "length_m is geometric distance only; no travel-time weight is assigned here.",
    }


def _nearest_line_connectors(
    points: gpd.GeoDataFrame,
    lines: gpd.GeoDataFrame,
    point_kind: str,
    line_kind: str,
) -> gpd.GeoDataFrame:
    p = points.to_crs(DISTANCE_CRS).reset_index(drop=True).copy()
    l = lines.to_crs(DISTANCE_CRS).reset_index(drop=True).copy()
    p["point_id"] = [f"{point_kind}_{i}" for i in range(len(p))]
    l["line_id"] = [f"{line_kind}_{i}" for i in range(len(l))]
    nearest = gpd.sjoin_nearest(
        p[["point_id", "geometry"]],
        l[["line_id", "geometry"]],
        how="left",
        distance_col="snap_distance_m",
    )
    nearest = nearest.sort_values(["point_id", "snap_distance_m"]).drop_duplicates("point_id")
    right_geom = l.geometry
    snap_points = []
    connector_lines = []
    for _, row in nearest.iterrows():
        if pd.isna(row.get("index_right")):
            snap_points.append(None)
            connector_lines.append(None)
            continue
        source_pt = row.geometry
        target_line = right_geom.iloc[int(row["index_right"])]
        snapped = target_line.interpolate(target_line.project(source_pt))
        snap_points.append(snapped)
        connector_lines.append(LineString([source_pt, snapped]))
    nearest["snap_geometry"] = snap_points
    nearest["geometry"] = connector_lines
    nearest["point_kind"] = point_kind
    nearest["line_kind"] = line_kind
    nearest["connector_status"] = "candidate_distance_only"
    return gpd.GeoDataFrame(nearest, geometry="geometry", crs=DISTANCE_CRS).to_crs(TARGET_CRS)


def _read_optional_layer(path: Path, layer: str) -> gpd.GeoDataFrame | None:
    if not path.exists():
        return None
    try:
        g = gpd.read_file(path, layer=layer)
    except Exception:
        return None
    return g if len(g) else None


def _summarize_connector(name: str, layer: gpd.GeoDataFrame, output_dir: Path) -> dict[str, object]:
    path = output_dir / f"{name}_connector_candidates.gpkg"
    layer.to_file(path, layer=name, driver="GPKG")
    distances = pd.to_numeric(layer["snap_distance_m"], errors="coerce").dropna()
    return {
        "rows": int(len(layer)),
        "resolved": int(distances.notna().sum()),
        "median_snap_distance_m": float(distances.median()) if len(distances) else None,
        "p95_snap_distance_m": float(distances.quantile(0.95)) if len(distances) else None,
        "max_snap_distance_m": float(distances.max()) if len(distances) else None,
        "output": str(path),
        "status": "candidate_only_not_promoted",
    }


def build_connector_candidates(graph_inputs: Path, output_dir: Path) -> dict[str, object]:
    roads = _read_optional_layer(graph_inputs / "roads.gpkg", "roads")
    waterways = _read_optional_layer(graph_inputs / "waterways.gpkg", "waterways")
    ports = _read_optional_layer(graph_inputs / "ports.gpkg", "ports")
    airports = _read_optional_layer(graph_inputs / "airports.gpkg", "airports")

    summary: dict[str, object] = {}
    specs = [
        ("port_to_road", ports, roads, "port", "road"),
        ("port_to_waterway", ports, waterways, "port", "waterway"),
        ("airport_to_road", airports, roads, "airport", "road"),
    ]
    for name, points, lines, point_kind, line_kind in specs:
        if points is None or lines is None:
            missing = []
            if points is None:
                missing.append(point_kind)
            if lines is None:
                missing.append(line_kind)
            summary[name] = {
                "rows": 0,
                "resolved": 0,
                "median_snap_distance_m": None,
                "p95_snap_distance_m": None,
                "max_snap_distance_m": None,
                "output": None,
                "status": "source_temporarily_unavailable_not_promoted",
                "missing_modal_inputs": missing,
            }
            continue
        layer = _nearest_line_connectors(points, lines, point_kind, line_kind)
        summary[name] = _summarize_connector(name, layer, output_dir)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf", type=Path, default=Path("data/raw/transport/osm_roads/norte-latest.osm.pbf"))
    parser.add_argument("--graph-inputs", type=Path, default=Path("artifacts/multimodal_graph_inputs"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/transport_topology"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    road_graph = build_osm_road_graph(args.pbf, args.output_dir)
    connectors = build_connector_candidates(args.graph_inputs, args.output_dir)
    audit = {
        "crs": TARGET_CRS,
        "road_graph": road_graph,
        "connector_candidates": connectors,
        "scientific_policy": (
            "This stage builds structural topology and geometric connector candidates only. "
            "It does not assign modal speeds, waiting times, transfer penalties, seasonal travel times, "
            "or automatically promote a connector solely because it is nearest in Euclidean space. "
            "Temporary source unavailability is recorded as an unresolved connector input rather than promoted or silently imputed."
        ),
        "ready_for_connector_rule_audit": bool(road_graph["nodes"] and road_graph["edges"]),
        "ready_for_travel_time_routing": False,
    }
    (args.output_dir / "transport_topology_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
