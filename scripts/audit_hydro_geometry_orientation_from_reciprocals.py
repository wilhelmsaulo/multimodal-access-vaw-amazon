from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Geod
from shapely.geometry import LineString, MultiLineString

SRC = Path("artifacts/hydro_temporal_graph_reference/waterways_with_reference_time.gpkg")
OUT = Path("artifacts/hydro_geometry_orientation_audit")
GEOD = Geod(ellps="GRS80")


def norm(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.strip().lower().split())


def endpoints(geom) -> tuple[tuple[float, float], tuple[float, float]]:
    if isinstance(geom, LineString):
        coords = list(geom.coords)
        if len(coords) < 2:
            raise RuntimeError("LineString has fewer than 2 vertices")
        return tuple(coords[0]), tuple(coords[-1])
    if isinstance(geom, MultiLineString):
        parts = list(geom.geoms)
        if not parts:
            raise RuntimeError("Empty MultiLineString")
        first = list(parts[0].coords)
        last = list(parts[-1].coords)
        if not first or not last:
            raise RuntimeError("Empty MultiLineString part")
        return tuple(first[0]), tuple(last[-1])
    raise RuntimeError(f"Unsupported geometry type: {type(geom).__name__}")


def dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    _, _, d = GEOD.inv(float(a[0]), float(a[1]), float(b[0]), float(b[1]))
    return abs(float(d))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    routes = gpd.read_file(SRC, layer="waterways_reference_time").reset_index(drop=True)
    required = {"origin_municipality", "destination_municipality", "geometry", "travel_time_min"}
    missing = required - set(routes.columns)
    if missing:
        raise RuntimeError(f"Missing required columns: {sorted(missing)}")

    routes["origin_norm"] = routes["origin_municipality"].map(norm)
    routes["destination_norm"] = routes["destination_municipality"].map(norm)
    informative = routes[
        routes["origin_norm"].ne("")
        & routes["destination_norm"].ne("")
        & routes["origin_norm"].ne(routes["destination_norm"])
    ].copy()

    by_pair: dict[tuple[str, str], list[int]] = {}
    for i, r in informative.iterrows():
        by_pair.setdefault((r["origin_norm"], r["destination_norm"]), []).append(int(i))

    rows: list[dict] = []
    seen_record_pairs: set[tuple[int, int]] = set()
    for (a, b), idxs in sorted(by_pair.items()):
        rev = by_pair.get((b, a), [])
        if not rev:
            continue
        for ia in idxs:
            for ib in rev:
                if ia == ib:
                    continue
                pair_key = tuple(sorted((ia, ib)))
                if pair_key in seen_record_pairs:
                    continue
                seen_record_pairs.add(pair_key)
                ra = routes.loc[ia]
                rb = routes.loc[ib]
                a0, a1 = endpoints(ra.geometry)
                b0, b1 = endpoints(rb.geometry)
                same = dist_m(a0, b0) + dist_m(a1, b1)
                reversed_alignment = dist_m(a0, b1) + dist_m(a1, b0)
                delta = same - reversed_alignment
                if reversed_alignment < same:
                    cls = "reverse_geometry_order_supported"
                elif same < reversed_alignment:
                    cls = "same_geometry_order_supported"
                else:
                    cls = "tie_unresolved"
                rows.append({
                    "route_index_a": ia,
                    "route_index_b": ib,
                    "a_origin": ra["origin_municipality"],
                    "a_destination": ra["destination_municipality"],
                    "b_origin": rb["origin_municipality"],
                    "b_destination": rb["destination_municipality"],
                    "hydro_id_a": ra.get("hydro_id"),
                    "hydro_id_b": rb.get("hydro_id"),
                    "time_a_min": float(ra["travel_time_min"]),
                    "time_b_min": float(rb["travel_time_min"]),
                    "same_order_endpoint_alignment_m": float(same),
                    "reverse_order_endpoint_alignment_m": float(reversed_alignment),
                    "same_minus_reverse_alignment_m": float(delta),
                    "orientation_evidence": cls,
                })

    pairs = pd.DataFrame(rows)
    if pairs.empty:
        raise RuntimeError("No non-self reciprocal municipality route records found")

    reverse_n = int((pairs["orientation_evidence"] == "reverse_geometry_order_supported").sum())
    same_n = int((pairs["orientation_evidence"] == "same_geometry_order_supported").sum())
    tie_n = int((pairs["orientation_evidence"] == "tie_unresolved").sum())
    decisive_n = reverse_n + same_n
    reverse_share = float(reverse_n / decisive_n) if decisive_n else None

    # Reciprocal geometry is supporting evidence only. Contradictory pairs are
    # sufficient to prevent statewide validation from this audit alone.
    audit = {
        "official_routes_total": int(len(routes)),
        "informative_nonself_routes": int(len(informative)),
        "reciprocal_record_pairs_evaluated": int(len(pairs)),
        "reverse_geometry_order_supported_pairs": reverse_n,
        "same_geometry_order_supported_pairs": same_n,
        "tie_unresolved_pairs": tie_n,
        "decisive_pair_count": decisive_n,
        "reverse_order_support_fraction_among_decisive_pairs": reverse_share,
        "reciprocal_evidence_supports_directional_ordering": bool(reverse_n > same_n),
        "reciprocal_evidence_contains_contradictions": bool(same_n > 0 or tie_n > 0),
        "geometry_vertex_order_validated_as_origin_to_destination": False,
        "statewide_symmetric_time_assumption_used": False,
        "automatic_reverse_edge_creation_used": False,
        "distance_threshold_used": False,
        "scientific_policy": (
            "Explicit reciprocal ANTAQ records provide supporting evidence about endpoint ordering, but contradictory reciprocal geometries prevent this audit alone from validating statewide geometry direction. "
            "No absolute distance cutoff is selected, no reverse edge is synthesized, and reported directional times remain route-record specific."
        ),
        "ready_for_directional_hydro_graph_materialization": False,
        "next_required_step": (
            "Validate route endpoint orientation independently against official municipality polygons for informative Pará origin/destination records before directed graph materialization."
        ),
    }

    pairs.to_csv(OUT / "reciprocal_geometry_orientation_pairs.csv", index=False)
    (OUT / "hydro_geometry_orientation_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(pairs.head(50).to_string(index=False))


if __name__ == "__main__":
    main()
