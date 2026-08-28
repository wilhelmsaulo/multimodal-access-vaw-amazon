from __future__ import annotations

"""Publish a reproducible visual/documentation bundle for the corrected Stage-2 network.

The temporal graph artifacts intentionally store node identities and impedances, not a
full cartographic node table.  For visualization only, numeric OSM node coordinates are
reattached from the pinned Geofabrik Norte snapshot that was current immediately before
the authoritative road-time build.  Publication is allowed only when every numeric node
used by the corrected final road graph is found in that snapshot.  No topology, travel
time, speed, waiting time, or routing result is recomputed by this script.
"""

import argparse
import json
import math
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from pyproj import Transformer
from shapely.geometry import LineString

IBGE_PA_2023 = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_2023/UFs/PA/PA_Municipios_2023.zip"
)
MAP_CRS = 5880  # SIRGAS 2000 / Brazil Polyconic; metric.
GEO_CRS = 4674  # SIRGAS 2000 geographic coordinates.
EXPECTED_OSM_SNAPSHOT = "norte-260824.osm.pbf"


def load_ibge_pa() -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as td:
        zpath = Path(td) / "pa_municipios.zip"
        urllib.request.urlretrieve(IBGE_PA_2023, zpath)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(td)
        shp = next(Path(td).glob("*.shp"))
        gdf = gpd.read_file(shp)
    return gdf.to_crs(epsg=GEO_CRS)


def read_first_gpkg(path: Path) -> gpd.GeoDataFrame:
    layers = gpd.list_layers(path)
    if len(layers) == 0:
        raise RuntimeError(f"No layers in {path}")
    return gpd.read_file(path, layer=str(layers.iloc[0]["name"]))


def collect_numeric_road_nodes(road_path: Path) -> set[int]:
    ids: set[int] = set()
    for c in pd.read_csv(
        road_path,
        usecols=["from_node", "to_node"],
        dtype=str,
        chunksize=500_000,
    ):
        for col in ["from_node", "to_node"]:
            s = c[col].dropna().astype(str)
            numeric = s[s.str.fullmatch(r"\d+")]
            ids.update(pd.to_numeric(numeric, errors="raise").astype("int64").tolist())
    return ids


def extract_osm_coordinates(pbf: Path, needed: set[int]) -> dict[int, tuple[float, float]]:
    import osmium

    found: dict[int, tuple[float, float]] = {}

    class Handler(osmium.SimpleHandler):
        def node(self, n):
            node_id = int(n.id)
            if node_id in needed and n.location.valid():
                found[node_id] = (float(n.location.lon), float(n.location.lat))

    Handler().apply_file(str(pbf), locations=False)
    return found


def terminal_coordinates(
    splits: pd.DataFrame,
    coords: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    forward = Transformer.from_crs(GEO_CRS, MAP_CRS, always_xy=True)
    inverse = Transformer.from_crs(MAP_CRS, GEO_CRS, always_xy=True)
    out: dict[str, tuple[float, float]] = {}
    for r in splits.itertuples(index=False):
        u, v = str(r.source_u), str(r.source_v)
        if u not in coords or v not in coords:
            raise RuntimeError(f"Source road nodes unavailable for terminal {r.port_name}")
        x1, y1 = forward.transform(*coords[u])
        x2, y2 = forward.transform(*coords[v])
        f = float(r.projection_fraction_u_to_v)
        x = x1 + f * (x2 - x1)
        y = y1 + f * (y2 - y1)
        lon, lat = inverse.transform(x, y)
        out[str(r.terminal_node_id)] = (float(lon), float(lat))
    return out


def degree_label(value: float, latitude: bool) -> str:
    hemi = ("N" if value >= 0 else "S") if latitude else ("E" if value >= 0 else "W")
    decimals = 0 if abs(value - round(value)) < 1e-9 else 1
    return f"{abs(value):.{decimals}f}°{hemi}"


def graticule_step(span: float) -> float:
    if span > 8:
        return 2.0
    if span > 3:
        return 1.0
    if span > 1:
        return 0.5
    if span > 0.4:
        return 0.2
    return 0.1


def add_geographic_graticule(ax, extent: tuple[float, float, float, float]) -> None:
    min_lon, min_lat, max_lon, max_lat = extent
    lon_step = graticule_step(max_lon - min_lon)
    lat_step = graticule_step(max_lat - min_lat)
    lon_values = np.arange(math.ceil(min_lon / lon_step) * lon_step, max_lon + 1e-9, lon_step)
    lat_values = np.arange(math.ceil(min_lat / lat_step) * lat_step, max_lat + 1e-9, lat_step)
    forward = Transformer.from_crs(GEO_CRS, MAP_CRS, always_xy=True)

    lat_samples = np.linspace(min_lat, max_lat, 80)
    lon_samples = np.linspace(min_lon, max_lon, 80)
    for lon in lon_values:
        xs, ys = forward.transform(np.full_like(lat_samples, lon), lat_samples)
        ax.plot(xs, ys, linewidth=0.35, linestyle=":", alpha=0.45, color="0.45", zorder=0)
        ax.text(xs[0], ys[0], degree_label(float(lon), False), fontsize=6.5, ha="center", va="top", clip_on=False)
    for lat in lat_values:
        xs, ys = forward.transform(lon_samples, np.full_like(lon_samples, lat))
        ax.plot(xs, ys, linewidth=0.35, linestyle=":", alpha=0.45, color="0.45", zorder=0)
        ax.text(xs[0], ys[0], degree_label(float(lat), True), fontsize=6.5, ha="right", va="center", clip_on=False)


def add_north_arrow(ax) -> None:
    ax.annotate(
        "N",
        xy=(0.94, 0.95), xytext=(0.94, 0.86),
        xycoords="axes fraction",
        ha="center", va="center",
        fontsize=12, fontweight="bold",
        arrowprops=dict(facecolor="black", edgecolor="black", width=2.1, headwidth=8),
        zorder=20,
    )


def add_scale_bar(ax, length_km: int) -> None:
    xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
    length_m = length_km * 1000.0
    x0 = xmin + 0.06 * (xmax - xmin)
    y0 = ymin + 0.055 * (ymax - ymin)
    tick = 0.007 * (ymax - ymin)
    ax.plot([x0, x0 + length_m], [y0, y0], linewidth=2.5, color="black", solid_capstyle="butt", zorder=20)
    for x in [x0, x0 + length_m]:
        ax.plot([x, x], [y0 - tick, y0 + tick], linewidth=1.4, color="black", zorder=20)
    ax.text(x0, y0 + 2 * tick, "0", fontsize=7, ha="center", va="bottom")
    ax.text(x0 + length_m, y0 + 2 * tick, f"{length_km} km", fontsize=7, ha="center", va="bottom")


def projected_extent(extent_geo: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = extent_geo
    t = Transformer.from_crs(GEO_CRS, MAP_CRS, always_xy=True)
    corners = [(min_lon, min_lat), (min_lon, max_lat), (max_lon, min_lat), (max_lon, max_lat)]
    xy = [t.transform(x, y) for x, y in corners]
    xs, ys = zip(*xy)
    return min(xs), min(ys), max(xs), max(ys)


def plot_road_network(
    ax,
    road_path: Path,
    coords: dict[str, tuple[float, float]],
    *,
    geographic_bbox: tuple[float, float, float, float] | None = None,
    linewidth: float = 0.07,
    alpha: float = 0.28,
) -> int:
    forward = Transformer.from_crs(GEO_CRS, MAP_CRS, always_xy=True)
    count = 0
    for c in pd.read_csv(
        road_path,
        usecols=["from_node", "to_node", "edge_role"],
        dtype=str,
        chunksize=250_000,
    ):
        # Evidence-backed ferry/passenger patches are overlaid separately.
        c = c[~c["edge_role"].eq("evidence_backed_reopened_transfer")].copy()
        if c.empty:
            continue
        from_xy = c["from_node"].map(coords)
        to_xy = c["to_node"].map(coords)
        ok = from_xy.notna() & to_xy.notna()
        if not ok.any():
            continue
        c = c.loc[ok]
        fxy = from_xy.loc[ok]
        txy = to_xy.loc[ok]
        lon1 = np.fromiter((p[0] for p in fxy), dtype=float, count=len(fxy))
        lat1 = np.fromiter((p[1] for p in fxy), dtype=float, count=len(fxy))
        lon2 = np.fromiter((p[0] for p in txy), dtype=float, count=len(txy))
        lat2 = np.fromiter((p[1] for p in txy), dtype=float, count=len(txy))
        if geographic_bbox is not None:
            min_lon, min_lat, max_lon, max_lat = geographic_bbox
            keep = (
                (np.maximum(lon1, lon2) >= min_lon) & (np.minimum(lon1, lon2) <= max_lon)
                & (np.maximum(lat1, lat2) >= min_lat) & (np.minimum(lat1, lat2) <= max_lat)
            )
            if not keep.any():
                continue
            lon1, lat1, lon2, lat2 = lon1[keep], lat1[keep], lon2[keep], lat2[keep]
        x1, y1 = forward.transform(lon1, lat1)
        x2, y2 = forward.transform(lon2, lat2)
        seg = np.stack([np.column_stack([x1, y1]), np.column_stack([x2, y2])], axis=1)
        ax.add_collection(LineCollection(seg, linewidths=linewidth, alpha=alpha, colors="0.25", rasterized=True, zorder=2))
        count += len(seg)
    return count


def correction_table(audit: dict) -> pd.DataFrame:
    rows = []
    for p in audit["patches"]:
        rows.append({
            "name": p["name"],
            "from_node": str(p["from_node"]),
            "to_node": str(p["to_node"]),
            "travel_time_min": float(p["travel_time_min"]),
            "mode": p["mode"],
            "edge_role": p["edge_role"],
            "evidence": p["evidence"],
            "bidirectional": bool(p["bidirectional"]),
            "waiting_time_included": bool(p["waiting_time_included"]),
        })
    return pd.DataFrame(rows)


def correction_lines(corrections: pd.DataFrame, coords: dict[str, tuple[float, float]]) -> gpd.GeoDataFrame:
    rows = []
    for r in corrections.itertuples(index=False):
        if r.from_node not in coords or r.to_node not in coords:
            raise RuntimeError(f"Correction endpoints unavailable: {r.name}")
        rows.append({**r._asdict(), "geometry": LineString([coords[r.from_node], coords[r.to_node]])})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{GEO_CRS}")


def plot_statewide(
    road_path: Path,
    coords: dict[str, tuple[float, float]],
    hydro: gpd.GeoDataFrame,
    municipalities: gpd.GeoDataFrame,
    splits: pd.DataFrame,
    corr_gdf: gpd.GeoDataFrame,
    out: Path,
) -> int:
    fig, ax = plt.subplots(figsize=(12, 10.5))
    muni_m = municipalities.to_crs(epsg=MAP_CRS)
    muni_m.boundary.plot(ax=ax, linewidth=0.22, color="0.72", zorder=1)
    road_segments = plot_road_network(ax, road_path, coords, linewidth=0.055, alpha=0.22)
    hydro.to_crs(epsg=MAP_CRS).plot(ax=ax, linewidth=0.75, color="tab:blue", alpha=0.75, zorder=3)
    corr_gdf.to_crs(epsg=MAP_CRS).plot(ax=ax, linewidth=2.3, color="tab:red", linestyle="--", zorder=7)

    term_rows = []
    for r in splits.itertuples(index=False):
        lon, lat = coords[str(r.terminal_node_id)]
        term_rows.append({"port_name": r.port_name, "geometry": gpd.points_from_xy([lon], [lat])[0]})
    terminals = gpd.GeoDataFrame(term_rows, geometry="geometry", crs=f"EPSG:{GEO_CRS}").to_crs(epsg=MAP_CRS)
    terminals.plot(ax=ax, marker="o", markersize=25, facecolor="white", edgecolor="black", linewidth=0.9, zorder=8)

    extent_geo = tuple(municipalities.total_bounds.tolist())
    add_geographic_graticule(ax, extent_geo)
    add_north_arrow(ax)
    add_scale_bar(ax, 200)
    ax.set_title("Pará — rede temporal multimodal corrigida da Stage 2", fontsize=14, pad=12)
    ax.legend(handles=[
        Line2D([0], [0], color="0.25", linewidth=1.2, label="Rede rodoviária primária OSM"),
        Line2D([0], [0], color="tab:blue", linewidth=2, label="Topologia hidroviária validada"),
        Line2D([0], [0], color="tab:red", linewidth=2, linestyle="--", label="Transferências reabertas com evidência"),
        Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="white", markeredgecolor="black", label="Terminais intermodais validados"),
        Line2D([0], [0], color="0.72", linewidth=0.8, label="Limites municipais IBGE"),
    ], loc="lower right", frameon=True, title="Legenda", fontsize=8)
    ax.set_axis_off()
    ax.text(
        0.01, 0.006,
        "Fontes: grafo temporal corrigido (2026); OSM/Geofabrik snapshot 24-08-2026 para geometria dos nós; "
        "topologia hidroviária validada (2026); IBGE, malha municipal 2023.\n"
        "Projeção: SIRGAS 2000 / Brazil Polyconic (EPSG:5880). Coordenadas: SIRGAS 2000 (EPSG:4674).",
        transform=ax.transAxes, fontsize=7.2, va="bottom",
    )
    fig.tight_layout()
    fig.savefig(out / "figures/statewide_multimodal_network.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    return road_segments


def plot_correction(
    name: str,
    road_path: Path,
    coords: dict[str, tuple[float, float]],
    hydro: gpd.GeoDataFrame,
    municipalities: gpd.GeoDataFrame,
    corr_row: pd.Series,
    out_path: Path,
) -> None:
    a = coords[str(corr_row["from_node"])]
    b = coords[str(corr_row["to_node"])]
    min_lon, max_lon = min(a[0], b[0]), max(a[0], b[0])
    min_lat, max_lat = min(a[1], b[1]), max(a[1], b[1])
    pad_lon = max(0.12, 0.18 * max(max_lon - min_lon, 0.1))
    pad_lat = max(0.12, 0.18 * max(max_lat - min_lat, 0.1))
    bbox = (min_lon-pad_lon, min_lat-pad_lat, max_lon+pad_lon, max_lat+pad_lat)
    pext = projected_extent(bbox)

    fig, ax = plt.subplots(figsize=(10, 8))
    muni = municipalities.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    muni.to_crs(epsg=MAP_CRS).boundary.plot(ax=ax, linewidth=0.6, color="0.65", zorder=1)
    plot_road_network(ax, road_path, coords, geographic_bbox=bbox, linewidth=0.16, alpha=0.40)
    h = hydro.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    if not h.empty:
        h.to_crs(epsg=MAP_CRS).plot(ax=ax, linewidth=1.1, color="tab:blue", alpha=0.85, zorder=3)
    line = gpd.GeoDataFrame(
        [{"geometry": LineString([a,b])}], geometry="geometry", crs=f"EPSG:{GEO_CRS}"
    ).to_crs(epsg=MAP_CRS)
    line.plot(ax=ax, linewidth=3, linestyle="--", color="tab:red", zorder=6)
    pts = gpd.GeoDataFrame(
        {"node": [str(corr_row["from_node"]), str(corr_row["to_node"])],
         "geometry": gpd.points_from_xy([a[0], b[0]], [a[1], b[1]])},
        geometry="geometry", crs=f"EPSG:{GEO_CRS}",
    ).to_crs(epsg=MAP_CRS)
    pts.plot(ax=ax, markersize=42, marker="o", facecolor="white", edgecolor="black", linewidth=1.1, zorder=7)
    for r in pts.itertuples(index=False):
        ax.annotate(r.node, xy=(r.geometry.x, r.geometry.y), xytext=(4, 5), textcoords="offset points", fontsize=7)

    ax.set_xlim(pext[0], pext[2]); ax.set_ylim(pext[1], pext[3])
    add_geographic_graticule(ax, bbox)
    add_north_arrow(ax)
    scale = 50 if max(max_lon-min_lon, max_lat-min_lat) > 1 else 10
    add_scale_bar(ax, scale)
    ax.set_title(f"{name} — correção de transferência da rede", fontsize=13, pad=10)
    ax.legend(handles=[
        Line2D([0], [0], color="0.25", linewidth=1.2, label="Rede rodoviária"),
        Line2D([0], [0], color="tab:blue", linewidth=2, label="Topologia hidroviária"),
        Line2D([0], [0], color="tab:red", linestyle="--", linewidth=2.5, label=f"Transferência ({float(corr_row['travel_time_min']):g} min)"),
        Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="white", markeredgecolor="black", label="Nós exatos do grafo"),
    ], loc="lower right", title="Legenda", fontsize=8)
    ax.set_axis_off()
    ax.text(
        0.01, 0.006,
        f"Fonte: artefato de correção da Stage 2 (2026). Evidência: {corr_row['evidence']}.\n"
        "Geometria rodoviária: OSM/Geofabrik snapshot 24-08-2026; limites: IBGE 2023. "
        "EPSG:5880; coordenadas EPSG:4674.",
        transform=ax.transAxes, fontsize=7, va="bottom",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def write_readme(out: Path, metadata: dict, corrections: pd.DataFrame, splits: pd.DataFrame) -> None:
    lines = [
        "# Stage 2 — corrected multimodal temporal network",
        "",
        "This directory documents the **authoritative corrected Stage-2 network** used to rebuild the final OD matrix. The publication step does not recompute routing or travel times; it only attaches cartographic coordinates to the already-frozen node identities for visualization.",
        "",
        "## Authoritative provenance",
        "",
        f"- Frozen backbone run: `{metadata['frozen_backbone_run_id']}`",
        f"- Corrected backbone/OD run: `{metadata['corrected_network_run_id']}`",
        f"- Corrected backbone artifact: `{metadata['corrected_backbone_artifact']}`",
        f"- Hydro topology run: `{metadata['hydro_topology_run_id']}`",
        f"- Terminal split run: `{metadata['terminal_split_run_id']}`",
        f"- Cartographic OSM snapshot: `{metadata['osm_snapshot_file']}`",
        f"- Final numeric road-node coordinate coverage: **{metadata['road_node_coordinate_coverage_fraction']:.6f}**",
        "",
        "## Network construction flow",
        "",
        "```mermaid",
        "flowchart LR",
        "    A[OSM road topology] --> B[Conservative motor-road graph]",
        "    B --> C[Validated road travel times]",
        "    D[Hydro topology + temporal evidence] --> E[Validated hydro temporal graph]",
        "    F[Validated terminals] --> G[Structural road-edge splits]",
        "    C --> H[Frozen multimodal backbone]",
        "    E --> H",
        "    G --> H",
        "    H --> I[Bounded evidence-backed correction]",
        "    I --> J[Corrected reference OD]",
        "```",
        "",
        "## Figures",
        "",
        "### Statewide corrected multimodal network",
        "",
        "![Statewide multimodal network](figures/statewide_multimodal_network.png)",
        "",
        "### Colares transfer correction",
        "",
        "![Colares correction](figures/colares_transfer_correction.png)",
        "",
        "### Belém–Santa Cruz do Arari transfer correction",
        "",
        "![Santa Cruz correction](figures/santa_cruz_transfer_correction.png)",
        "",
        "All maps include title, legend, cartographic scale, North arrow, geographic latitude/longitude graticule, source/year and CRS information.",
        "",
        "## Validated original road–hydro terminals",
        "",
        "| Port | Terminal node | Hydro node |",
        "|---|---|---|",
    ]
    for r in splits.itertuples(index=False):
        lines.append(f"| {r.port_name} | `{r.terminal_node_id}` | `{r.hydro_node_id}` |")
    lines += [
        "",
        "## Bounded transfer corrections",
        "",
        "| Correction | Mode | Time (min) | Endpoint nodes |",
        "|---|---|---:|---|",
    ]
    for r in corrections.itertuples(index=False):
        lines.append(f"| {r.name} | {r.mode} | {r.travel_time_min:g} | `{r.from_node}` ↔ `{r.to_node}` |")
    lines += [
        "",
        "Afuá receives **no synthetic edge**. Its missing surface-access evidence remains a model-scope/coverage limitation and is not represented as real-world isolation.",
        "",
        "## Cartographic reconstruction safeguard",
        "",
        "The final temporal road edge table contains node IDs and travel-time impedance but no full coordinate table. For publication only, coordinates are reattached from the pinned historical Geofabrik Norte OSM snapshot that was current immediately before the authoritative terrestrial-time workflow. The publisher fails unless every numeric road node in the final corrected graph is present. Synthetic intermodal terminal coordinates are reproduced from the exact source OSM road segment and the locked projection fraction used during the original road-edge split.",
        "",
        "This coordinate attachment does **not** change edge membership, direction, impedance, speed, waiting time or OD results.",
        "",
        "## Tables",
        "",
        "- [`network_component_summary.csv`](tables/network_component_summary.csv)",
        "- [`validated_transfer_terminals.csv`](tables/validated_transfer_terminals.csv)",
        "- [`bounded_transfer_corrections.csv`](tables/bounded_transfer_corrections.csv)",
        "- [`cartographic_node_validation.csv`](tables/cartographic_node_validation.csv)",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--backbone-dir", type=Path, required=True)
    p.add_argument("--hydro-dir", type=Path, required=True)
    p.add_argument("--terminal-dir", type=Path, required=True)
    p.add_argument("--osm-pbf", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("results/stage2_network"))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "tables").mkdir(exist_ok=True)
    (args.out / "figures").mkdir(exist_ok=True)

    if args.osm_pbf.name != EXPECTED_OSM_SNAPSHOT:
        raise RuntimeError(f"Expected pinned OSM snapshot {EXPECTED_OSM_SNAPSHOT}, got {args.osm_pbf.name}")

    road_path = args.backbone_dir / "final_road_directed_edges.csv.gz"
    hydro_path = args.backbone_dir / "final_hydro_directed_edges.csv.gz"
    corrected_audit = json.loads((args.backbone_dir / "corrected_backbone_audit.json").read_text(encoding="utf-8"))
    splits = pd.read_csv(args.terminal_dir / "intermodal_terminal_road_edge_splits.csv", dtype=str)

    numeric_ids = collect_numeric_road_nodes(road_path)
    osm_coords = extract_osm_coordinates(args.osm_pbf, numeric_ids)
    missing = sorted(numeric_ids - set(osm_coords))
    coverage = len(osm_coords) / len(numeric_ids) if numeric_ids else 0.0
    validation = pd.DataFrame([{
        "osm_snapshot": args.osm_pbf.name,
        "numeric_final_road_nodes_requested": len(numeric_ids),
        "numeric_final_road_nodes_found": len(osm_coords),
        "missing_numeric_final_road_nodes": len(missing),
        "coverage_fraction": coverage,
        "complete_match": len(missing) == 0,
    }])
    validation.to_csv(args.out / "tables/cartographic_node_validation.csv", index=False)
    if missing:
        raise RuntimeError(f"Pinned OSM snapshot does not reproduce all final road nodes; missing {len(missing)} nodes, sample={missing[:20]}")

    coords: dict[str, tuple[float, float]] = {str(k): v for k, v in osm_coords.items()}
    coords.update(terminal_coordinates(splits, coords))

    corrections = correction_table(corrected_audit)
    corr_gdf = correction_lines(corrections, coords)

    hydro_gpkg = args.hydro_dir / "hydro_topology_edges.gpkg"
    hydro = read_first_gpkg(hydro_gpkg).to_crs(epsg=GEO_CRS)
    municipalities = load_ibge_pa()

    road_segments_rendered = plot_statewide(road_path, coords, hydro, municipalities, splits, corr_gdf, args.out)
    for _, r in corrections.iterrows():
        if r["name"].startswith("Colares"):
            stem = "colares_transfer_correction.png"
            title = "Colares–Penhalonga"
        else:
            stem = "santa_cruz_transfer_correction.png"
            title = "Belém–Santa Cruz do Arari"
        plot_correction(title, road_path, coords, hydro, municipalities, r, args.out / "figures" / stem)

    hydro_audit = json.loads((args.hydro_dir / "hydro_topology_with_validated_snaps_audit.json").read_text(encoding="utf-8"))
    component_rows = [
        {"component": "corrected_road_directed_edges", "count": int(corrected_audit["corrected_road_directed_edges"]), "source": "corrected backbone"},
        {"component": "added_evidence_backed_directed_edges", "count": int(corrected_audit["added_directed_edges"]), "source": "bounded correction"},
        {"component": "hydro_final_directed_edges", "count": int(pd.read_csv(hydro_path).shape[0]), "source": "corrected backbone"},
        {"component": "validated_original_intermodal_terminals", "count": int(len(splits)), "source": "terminal split audit"},
        {"component": "numeric_road_nodes_with_coordinates", "count": int(len(osm_coords)), "source": args.osm_pbf.name},
    ]
    pd.DataFrame(component_rows).to_csv(args.out / "tables/network_component_summary.csv", index=False)
    splits.to_csv(args.out / "tables/validated_transfer_terminals.csv", index=False)
    corrections.to_csv(args.out / "tables/bounded_transfer_corrections.csv", index=False)

    metadata = {
        "stage": "Stage 2 corrected multimodal temporal network publication",
        "frozen_backbone_run_id": 32920014705,
        "corrected_network_run_id": 33089335405,
        "corrected_backbone_artifact": "pa-corrected-multimodal-backbone",
        "hydro_topology_run_id": 32868022260,
        "terminal_split_run_id": 32907985189,
        "osm_snapshot_file": args.osm_pbf.name,
        "osm_snapshot_role": "cartographic coordinate reattachment only",
        "road_node_coordinate_coverage_fraction": coverage,
        "road_nodes_missing_from_snapshot": len(missing),
        "road_segments_rendered_statewide_directed": int(road_segments_rendered),
        "map_crs": "EPSG:5880 — SIRGAS 2000 / Brazil Polyconic",
        "geographic_crs": "EPSG:4674 — SIRGAS 2000",
        "cartographic_elements": ["title", "legend", "scale_bar", "north_arrow", "geographic_coordinates", "source_and_year", "crs"],
        "routing_recomputed": False,
        "travel_times_changed": False,
        "new_speed_assumption_used": False,
        "waiting_time_added": False,
        "afua_synthetic_edge_added": False,
        "hydro_audit_file": "hydro_topology_with_validated_snaps_audit.json",
    }
    (args.out / "publication_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(args.out, metadata, corrections, splits)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
