from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Geod
from shapely.geometry import LineString, MultiLineString

SRC = Path("artifacts/hydro_temporal_graph_reference/waterways_with_reference_time.gpkg")
OUT = Path("artifacts/hydro_temporal_subdivision")
GEOD = Geod(ellps="GRS80")
TOL_MIN = 1e-9


def geodesic_length_m(line: LineString) -> float:
    coords = list(line.coords)
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for a, b in zip(coords[:-1], coords[1:]):
        _, _, d = GEOD.inv(float(a[0]), float(a[1]), float(b[0]), float(b[1]))
        total += max(float(d), 0.0)
    return total


def iter_parts(geom):
    if isinstance(geom, LineString):
        yield 0, geom
    elif isinstance(geom, MultiLineString):
        for i, part in enumerate(geom.geoms):
            yield i, part
    else:
        raise TypeError(f"Unsupported hydro geometry: {type(geom).__name__}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    routes = gpd.read_file(SRC, layer="waterways_reference_time").reset_index(drop=True)
    required = {"travel_time_min", "geometry"}
    if not required.issubset(routes.columns):
        raise RuntimeError(f"Missing required columns: {sorted(required - set(routes.columns))}")
    if routes["travel_time_min"].isna().any():
        raise RuntimeError("All hydro routes must have official reference time before subdivision")

    edge_rows: list[dict] = []
    zero_length_pairs = 0

    for route_index, row in routes.iterrows():
        route_key = f"hydro_route_{route_index:04d}"
        candidates: list[dict] = []
        for part_index, part in iter_parts(row.geometry):
            coords = list(part.coords)
            for vertex_index, (a, b) in enumerate(zip(coords[:-1], coords[1:])):
                edge = LineString([a, b])
                length_m = geodesic_length_m(edge)
                if length_m <= 0:
                    zero_length_pairs += 1
                    continue
                candidates.append(
                    {
                        "route_key": route_key,
                        "route_index": int(route_index),
                        "hydro_id": row.get("hydro_id"),
                        "part_index": int(part_index),
                        "vertex_index": int(vertex_index),
                        "edge_length_m": float(length_m),
                        "geometry": edge,
                    }
                )

        if not candidates:
            raise RuntimeError(f"Route {route_key} has no positive-length geometry")

        total_geom_m = sum(x["edge_length_m"] for x in candidates)
        official_time = float(row["travel_time_min"])
        allocated = 0.0
        for pos, edge in enumerate(candidates):
            if pos < len(candidates) - 1:
                edge_time = official_time * edge["edge_length_m"] / total_geom_m
                allocated += edge_time
            else:
                # Residual on the final edge guarantees exact route-level conservation
                # up to floating-point representation, without altering the official total.
                edge_time = official_time - allocated
            edge["travel_time_min"] = float(edge_time)
            edge["time_share"] = float(edge_time / official_time)
            edge["time_source"] = "antaq_official_network_reference_time_proportional_geodesic_subdivision"
            edge["passenger_realized_time"] = False
            edge["waiting_time_included"] = False
            edge["subdivision_role"] = "bookkeeping_decomposition_of_official_route_reference_time"
            edge_rows.append(edge)

    edges = gpd.GeoDataFrame(edge_rows, geometry="geometry", crs=routes.crs)
    if edges.empty:
        raise RuntimeError("Hydro subdivision produced no edges")

    checks = (
        edges.groupby("route_key", as_index=False)
        .agg(
            subdivided_edges=("route_key", "size"),
            subdivided_geometry_length_m=("edge_length_m", "sum"),
            subdivided_time_min=("travel_time_min", "sum"),
            time_share_sum=("time_share", "sum"),
        )
    )
    route_ref = routes.reset_index(names="route_index")[["route_index", "travel_time_min"]].copy()
    route_ref["route_key"] = route_ref["route_index"].map(lambda i: f"hydro_route_{int(i):04d}")
    checks = checks.merge(route_ref[["route_key", "travel_time_min"]], on="route_key", how="left")
    checks = checks.rename(columns={"travel_time_min": "official_route_time_min"})
    checks["absolute_time_conservation_error_min"] = (
        checks["subdivided_time_min"] - checks["official_route_time_min"]
    ).abs()
    checks["time_conserved"] = checks["absolute_time_conservation_error_min"] <= TOL_MIN

    if len(checks) != len(routes):
        raise RuntimeError(f"Route conservation audit count mismatch: {len(checks)} != {len(routes)}")
    if not checks["time_conserved"].all():
        bad = checks.loc[~checks["time_conserved"], ["route_key", "absolute_time_conservation_error_min"]]
        raise RuntimeError(f"Official hydro time not conserved:\n{bad.to_string(index=False)}")
    if (edges["travel_time_min"] <= 0).any():
        raise RuntimeError("Subdivision produced non-positive edge time")

    edges.to_file(OUT / "hydro_reference_time_subedges.gpkg", layer="hydro_reference_time_subedges", driver="GPKG")
    checks.to_csv(OUT / "hydro_route_time_conservation.csv", index=False)

    audit = {
        "official_routes_total": int(len(routes)),
        "official_routes_audited": int(len(checks)),
        "subedges_total": int(len(edges)),
        "zero_length_vertex_pairs_skipped": int(zero_length_pairs),
        "routes_with_exact_time_conservation_within_tolerance": int(checks["time_conserved"].sum()),
        "time_conservation_fraction": float(checks["time_conserved"].mean()),
        "max_absolute_time_conservation_error_min": float(checks["absolute_time_conservation_error_min"].max()),
        "max_absolute_time_share_error": float((checks["time_share_sum"] - 1.0).abs().max()),
        "allocation_basis": "proportional_geodesic_length_within_each_official_antaq_route_geometry",
        "geodesic_ellipsoid": "GRS80",
        "allocation_interpretation": "bookkeeping subdivision of the official route-level reference impedance; it does not estimate or claim observed local vessel speed",
        "parallel_routes_collapsed": False,
        "route_specific_identity_preserved": True,
        "waiting_time_included": False,
        "distance_to_external_speed_conversion_used": False,
        "passenger_realized_time_claimed": False,
        "ready_for_hydro_topology_integration": bool(checks["time_conserved"].all()),
        "scientific_policy": (
            "When an official ANTAQ route geometry is subdivided for graph topology, its published route-level reference time is conserved exactly at route level. "
            "The same total is apportioned across within-route geometric subedges in proportion to GRS80 geodesic length solely as a bookkeeping decomposition because no official subedge times are available. "
            "This does not infer a statewide navigation speed, does not convert connector distances to time, does not include waiting, and preserves parallel route-specific edges."
        ),
    }
    (OUT / "hydro_temporal_subdivision_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
