from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point

SRC = Path("artifacts/hydro_temporal_graph_reference/waterways_with_reference_time.gpkg")
OUT = Path("artifacts/hydro_endpoint_municipality_orientation")
IBGE_ZIP = Path("data/raw/transport/ibge_municipal_boundaries/PA_Municipios_2023.zip")
IBGE_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_2023/UFs/PA/PA_Municipios_2023.zip"
)
IBGE_SHA256 = "0996ffd1b26928dfbd518f67339baa36fd860f50693c1c156f9b4d86fb77c7ad"


def norm(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.strip().lower().split())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_ibge() -> None:
    IBGE_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if not IBGE_ZIP.exists():
        with httpx.stream("GET", IBGE_URL, follow_redirects=True, timeout=120.0) as r:
            r.raise_for_status()
            with IBGE_ZIP.open("wb") as f:
                for chunk in r.iter_bytes(1024 * 1024):
                    f.write(chunk)
    actual = sha256(IBGE_ZIP)
    if actual != IBGE_SHA256:
        raise RuntimeError(f"IBGE municipal boundary SHA256 mismatch: {actual}")


def endpoints(geom) -> tuple[Point, Point]:
    if isinstance(geom, LineString):
        coords = list(geom.coords)
        return Point(coords[0]), Point(coords[-1])
    if isinstance(geom, MultiLineString):
        parts = list(geom.geoms)
        if not parts:
            raise RuntimeError("Empty MultiLineString")
        return Point(list(parts[0].coords)[0]), Point(list(parts[-1].coords)[-1])
    raise RuntimeError(f"Unsupported geometry type: {type(geom).__name__}")


def pick_name_column(munis: gpd.GeoDataFrame) -> str:
    candidates = ["NM_MUN", "NM_MUNICIP", "NOME", "nome", "name"]
    for c in candidates:
        if c in munis.columns:
            return c
    raise RuntimeError(f"Could not identify municipality-name column: {list(munis.columns)}")


def covering_names(point: Point, munis: gpd.GeoDataFrame, name_col: str) -> set[str]:
    # Exact polygon coverage only. No buffer and no distance threshold.
    idx = list(munis.sindex.query(point, predicate="intersects"))
    names: set[str] = set()
    for i in idx:
        geom = munis.geometry.iloc[i]
        if geom.covers(point):
            names.add(norm(munis.iloc[i][name_col]))
    return names


def state_is_pa(v: object) -> bool:
    s = norm(v)
    return s in {"pa", "para"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ensure_ibge()

    routes = gpd.read_file(SRC, layer="waterways_reference_time").reset_index(drop=True)
    required = {
        "origin_municipality", "destination_municipality", "origin_state",
        "destination_state", "geometry", "travel_time_min", "hydro_id"
    }
    missing = required - set(routes.columns)
    if missing:
        raise RuntimeError(f"Missing required route columns: {sorted(missing)}")

    munis = gpd.read_file(f"zip://{IBGE_ZIP}")
    name_col = pick_name_column(munis)
    if routes.crs is None or munis.crs is None:
        raise RuntimeError("Routes and IBGE municipalities must have CRS")
    munis = munis.to_crs(routes.crs)

    rows: list[dict] = []
    for i, r in routes.iterrows():
        origin = norm(r["origin_municipality"])
        dest = norm(r["destination_municipality"])
        pa_both = state_is_pa(r["origin_state"]) and state_is_pa(r["destination_state"])
        self_route = bool(origin and dest and origin == dest)
        p0, p1 = endpoints(r.geometry)

        start_names = covering_names(p0, munis, name_col) if pa_both else set()
        end_names = covering_names(p1, munis, name_col) if pa_both else set()

        if not pa_both:
            cls = "outside_pa_validation_scope"
        elif not origin or not dest:
            cls = "missing_named_endpoint"
        elif self_route:
            # Municipality identity cannot distinguish direction for an A→A record.
            cls = "uninformative_same_municipality"
        else:
            forward = origin in start_names and dest in end_names
            reverse = dest in start_names and origin in end_names
            if forward and not reverse:
                cls = "forward_consistent"
            elif reverse and not forward:
                cls = "reverse_consistent"
            elif forward and reverse:
                cls = "ambiguous_boundary_overlap"
            elif not start_names or not end_names:
                cls = "endpoint_not_covered_by_pa_polygon"
            else:
                cls = "municipality_mismatch"

        rows.append({
            "route_index": int(i),
            "hydro_id": r["hydro_id"],
            "origin_municipality": r["origin_municipality"],
            "destination_municipality": r["destination_municipality"],
            "origin_state": r["origin_state"],
            "destination_state": r["destination_state"],
            "travel_time_min": float(r["travel_time_min"]),
            "start_covering_municipalities": "|".join(sorted(start_names)),
            "end_covering_municipalities": "|".join(sorted(end_names)),
            "orientation_class": cls,
            "directed_geometry_use": (
                "as_stored" if cls == "forward_consistent" else
                "reverse_geometry" if cls == "reverse_consistent" else
                "not_authorized"
            ),
        })

    table = pd.DataFrame(rows)
    counts = table["orientation_class"].value_counts().to_dict()
    forward_n = int(counts.get("forward_consistent", 0))
    reverse_n = int(counts.get("reverse_consistent", 0))
    authorized_n = forward_n + reverse_n
    contradictory_n = reverse_n

    audit = {
        "official_routes_total": int(len(routes)),
        "ibge_source_url": IBGE_URL,
        "ibge_expected_sha256": IBGE_SHA256,
        "ibge_actual_sha256": sha256(IBGE_ZIP),
        "validation_scope": "routes with both declared endpoint states in Para",
        "orientation_class_counts": {str(k): int(v) for k, v in counts.items()},
        "forward_consistent_routes": forward_n,
        "reverse_consistent_routes": reverse_n,
        "route_specific_direction_authorized_count": authorized_n,
        "statewide_geometry_order_validated": False,
        "statewide_geometry_order_assumption_used": False,
        "distance_threshold_used": False,
        "buffer_used": False,
        "same_municipality_routes_directionally_informative": False,
        "automatic_reverse_edge_creation_used": False,
        "scientific_policy": (
            "Route endpoints are checked by exact coverage against the official IBGE 2023 Para municipal polygons. "
            "No buffer or distance cutoff is used. Direction is authorized only route-by-route: forward-consistent records retain stored geometry order and reverse-consistent records may be explicitly reversed to match declared origin→destination. "
            "Same-municipality, uncovered, mismatched, and out-of-scope records remain directionally unresolved."
        ),
        "ready_for_route_specific_directional_materialization": bool(authorized_n > 0),
        "ready_for_statewide_directional_hydro_graph": False,
        "next_required_step": (
            "Materialize only route-specific direction-authorized hydro records, while retaining unresolved records as unavailable for directed temporal routing until additional evidence is available. Quantify coverage before deciding whether this restricted graph is sufficient for the primary analysis."
        ),
    }

    table.to_csv(OUT / "hydro_route_endpoint_orientation.csv", index=False)
    (OUT / "hydro_endpoint_municipality_orientation_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(table["orientation_class"].value_counts().to_string())


if __name__ == "__main__":
    main()
