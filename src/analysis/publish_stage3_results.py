from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import LineString

IBGE_PA_2023 = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_2023/UFs/PA/PA_Municipios_2023.zip"
)
MAP_CRS = 5880
GEO_CRS = 4674

LABELS = {
    "criterion__reachable_service_fraction": "Fração de serviços alcançáveis",
    "criterion__services_within_120_fraction": "Fração de serviços em até 120 min",
    "criterion__nearest_reachable_service_time_min": "Tempo ao serviço alcançável mais próximo (min)",
    "criterion__median_reachable_service_time_min": "Tempo mediano aos serviços alcançáveis (min)",
    "criterion__health_specialized_absence": "Ausência de saúde especializada",
    "criterion__creas_absence": "Ausência de CREAS",
    "criterion__specialized_security_absence": "Ausência de segurança especializada",
    "criterion__specialized_justice_absence": "Ausência de justiça especializada",
    "criterion__rural_female_share": "Proporção de mulheres em área rural",
}


def load_ibge_pa() -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as td:
        zpath = Path(td) / "pa_municipios.zip"
        urllib.request.urlretrieve(IBGE_PA_2023, zpath)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(td)
        shp = next(Path(td).glob("*.shp"))
        gdf = gpd.read_file(shp)
    code_candidates = [c for c in gdf.columns if c.upper() in {"CD_MUN", "CD_MUN7", "GEOCODIGO"}]
    if not code_candidates:
        raise RuntimeError("IBGE municipality code column not found")
    gdf["municipality_code"] = gdf[code_candidates[0]].astype(str).str.replace(".0", "", regex=False).str.zfill(7)
    if gdf["municipality_code"].nunique() != 144:
        raise RuntimeError("Expected 144 Pará municipalities")
    return gdf[["municipality_code", "geometry"]].copy()


def add_north_arrow(ax) -> None:
    ax.annotate("N", xy=(0.94, 0.94), xytext=(0.94, 0.84), xycoords="axes fraction",
                ha="center", va="center", fontsize=12, fontweight="bold",
                arrowprops=dict(facecolor="black", edgecolor="black", width=2.2, headwidth=8))


def add_scale_bar(ax, length_km: int = 200) -> None:
    xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
    length_m = length_km * 1000
    x0 = xmin + 0.07 * (xmax - xmin); y0 = ymin + 0.06 * (ymax - ymin)
    ax.plot([x0, x0 + length_m], [y0, y0], color="black", linewidth=2.5)
    tick = 0.008 * (ymax - ymin)
    ax.plot([x0, x0], [y0 - tick, y0 + tick], color="black", linewidth=1.5)
    ax.plot([x0 + length_m, x0 + length_m], [y0 - tick, y0 + tick], color="black", linewidth=1.5)
    ax.text(x0, y0 + 2.1 * tick, "0", ha="center", va="bottom", fontsize=7)
    ax.text(x0 + length_m, y0 + 2.1 * tick, f"{length_km} km", ha="center", va="bottom", fontsize=7)


def _degree_label(value: float, latitude: bool) -> str:
    hemi = ("N" if value >= 0 else "S") if latitude else ("E" if value >= 0 else "W")
    return f"{abs(value):.0f}°{hemi}"


def add_geographic_graticule(ax, extent) -> None:
    min_lon, min_lat, max_lon, max_lat = extent
    lon_values = list(range(math.ceil(min_lon), math.floor(max_lon) + 1, 2))
    lat_values = list(range(math.ceil(min_lat), math.floor(max_lat) + 1, 2))
    lat_samples = np.linspace(min_lat, max_lat, 81)
    lon_samples = np.linspace(min_lon, max_lon, 81)
    for lon in lon_values:
        line = gpd.GeoSeries([LineString([(lon, lat) for lat in lat_samples])], crs=f"EPSG:{GEO_CRS}").to_crs(epsg=MAP_CRS)
        x, y = line.iloc[0].xy
        ax.plot(x, y, color="0.6", linewidth=0.4, linestyle=":", alpha=0.65, zorder=0)
        ax.text(x[0], y[0], _degree_label(float(lon), False), fontsize=7, ha="center", va="top", clip_on=False)
    for lat in lat_values:
        line = gpd.GeoSeries([LineString([(lon, lat) for lon in lon_samples])], crs=f"EPSG:{GEO_CRS}").to_crs(epsg=MAP_CRS)
        x, y = line.iloc[0].xy
        ax.plot(x, y, color="0.6", linewidth=0.4, linestyle=":", alpha=0.65, zorder=0)
        ax.text(x[0], y[0], _degree_label(float(lat), True), fontsize=7, ha="right", va="center", clip_on=False)


def map_indicator(boundaries: gpd.GeoDataFrame, matrix: pd.DataFrame, col: str, out: Path) -> None:
    geo = boundaries.merge(matrix[["municipality_code", col]], on="municipality_code", how="left", validate="one_to_one").to_crs(epsg=GEO_CRS)
    extent = tuple(geo.total_bounds.tolist())
    m = geo.to_crs(epsg=MAP_CRS)
    fig, ax = plt.subplots(figsize=(11, 9.5))
    m.plot(column=col, cmap="viridis", linewidth=0.35, edgecolor="0.45", legend=True,
           legend_kwds={"label": LABELS.get(col, col), "shrink": 0.72},
           missing_kwds={"color": "0.92", "edgecolor": "0.25", "hatch": "///"}, ax=ax)
    add_geographic_graticule(ax, extent)
    add_north_arrow(ax); add_scale_bar(ax)
    ax.set_title(f"Pará — {LABELS.get(col, col)}", fontsize=14, pad=12)
    ax.set_axis_off()
    ax.text(0.01, 0.005,
            "Fonte: matriz municipal corrigida Stage 3 (2026); malha municipal IBGE 2023.\n"
            "Projeção: SIRGAS 2000 / Brazil Polyconic (EPSG:5880); coordenadas geográficas: SIRGAS 2000 (EPSG:4674).",
            transform=ax.transAxes, fontsize=7.5, va="bottom")
    fig.tight_layout()
    fig.savefig(out / f"{col}.png", dpi=300, bbox_inches="tight")
    fig.savefig(out / f"{col}.svg", bbox_inches="tight")
    plt.close(fig)


def heatmap(corr: pd.DataFrame, title: str, path: Path) -> None:
    labels = [LABELS.get(c, c.replace("criterion__", "")) for c in corr.columns]
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(corr.to_numpy(float), vmin=-1, vmax=1, cmap="coolwarm")
    ax.set_xticks(range(len(labels)), labels=labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)), labels=labels, fontsize=8)
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="Correlação")
    fig.tight_layout(); fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)


def barplot(df: pd.DataFrame, x: str, y: str, title: str, ylabel: str, path: Path, threshold: float | None = None) -> None:
    d = df.copy()
    d[x] = d[x].map(lambda v: LABELS.get(v, str(v).replace("criterion__", "")))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(d[x], d[y])
    if threshold is not None:
        ax.axvline(threshold, linestyle="--", linewidth=1, label=f"limiar = {threshold:g}")
        ax.legend()
    ax.set_title(title); ax.set_xlabel(ylabel); ax.invert_yaxis()
    fig.tight_layout(); fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--artifact-root", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("results/stage3"))
    args = p.parse_args()
    out = args.out; tables = out / "tables"; figs = out / "figures"; maps = figs / "criterion_maps"
    tables.mkdir(parents=True, exist_ok=True); maps.mkdir(parents=True, exist_ok=True)

    root = args.artifact_root
    matrix_path = root / "stage3_sociodemographic" / "municipal_analytical_matrix_with_sociospatial_candidate.csv"
    audit_dir = root / "stage3_final_audit"
    special_path = root / "special_municipality_audit" / "special_municipality_audit.csv"
    matrix = pd.read_csv(matrix_path, dtype={"municipality_code": str}, low_memory=False)
    matrix["municipality_code"] = matrix["municipality_code"].astype(str).str.zfill(7)
    if len(matrix) != 144 or matrix["municipality_code"].nunique() != 144:
        raise RuntimeError("Stage 3 matrix must contain 144 municipalities")

    shutil.copy2(matrix_path, tables / "municipal_analytical_matrix.csv")
    for name in ["indicator_completeness.csv", "indicator_distribution.csv", "correlation_pearson.csv", "correlation_spearman.csv", "redundant_indicator_pairs.csv", "vif.csv", "stage3_audit_summary.json"]:
        shutil.copy2(audit_dir / name, tables / name)
    shutil.copy2(special_path, tables / "special_municipality_audit.csv")

    pearson = pd.read_csv(audit_dir / "correlation_pearson.csv", index_col=0)
    spearman = pd.read_csv(audit_dir / "correlation_spearman.csv", index_col=0)
    vif = pd.read_csv(audit_dir / "vif.csv")
    completeness = pd.read_csv(audit_dir / "indicator_completeness.csv")
    heatmap(pearson, "Stage 3 — matriz de correlação de Pearson", figs / "correlation_pearson.png")
    heatmap(spearman, "Stage 3 — matriz de correlação de Spearman", figs / "correlation_spearman.png")
    barplot(vif, "indicator", "vif", "Stage 3 — VIF dos critérios", "VIF", figs / "vif.png", 5.0)
    barplot(completeness, "indicator", "missing_fraction", "Stage 3 — fração de dados ausentes", "Fração ausente", figs / "missingness.png")

    boundaries = load_ibge_pa()
    criteria = [c for c in matrix.columns if c.startswith("criterion__")]
    for col in criteria:
        map_indicator(boundaries, matrix, col, maps)

    summary = json.loads((audit_dir / "stage3_audit_summary.json").read_text(encoding="utf-8"))
    readme = [
        "# Stage 3 — municipal analytical matrix and statistical audit", "",
        "This directory permanently publishes the authoritative corrected Stage-3 outputs used by Stage 4.", "",
        "## Provenance", "",
        "- Authoritative run: `33090126353`", "- Source artifact: `stage3-corrected-after-network-fix`", "- Municipalities: 144", "",
        "## Tables", "",
        "- [Municipal analytical matrix](tables/municipal_analytical_matrix.csv)",
        "- [Indicator completeness](tables/indicator_completeness.csv)",
        "- [Indicator distributions](tables/indicator_distribution.csv)",
        "- [Pearson correlation matrix](tables/correlation_pearson.csv)",
        "- [Spearman correlation matrix](tables/correlation_spearman.csv)",
        "- [VIF](tables/vif.csv)",
        "- [Redundancy flags](tables/redundant_indicator_pairs.csv)",
        "- [Special-municipality audit](tables/special_municipality_audit.csv)", "",
        "## Figures", "",
        "![Pearson](figures/correlation_pearson.png)", "",
        "![Spearman](figures/correlation_spearman.png)", "",
        "![VIF](figures/vif.png)", "",
        "![Missingness](figures/missingness.png)", "",
        "## Criterion maps", "",
        "Each of the nine MCDM criteria has a statewide map under [`figures/criterion_maps/`](figures/criterion_maps/). Final maps include title, legend, scale, north arrow, latitude/longitude graticule, source/year and CRS information.", "",
        "## Audit conclusion", "",
        f"- redundant pairs at |r|/|rho| >= 0.80: **{summary['redundant_pairs_flagged']}**",
        f"- VIF indicators >= 5: **{summary['vif_indicators_flagged']}**",
        f"- maximum VIF: **{summary['vif_max']}**",
        f"- PCA recommended: **{summary['pca_recommended_for_diagnostic_or_sensitivity_analysis']}**", "",
    ]
    (out / "README.md").write_text("\n".join(readme), encoding="utf-8")
    (out / "publication_metadata.json").write_text(json.dumps({
        "stage3_run": 33090126353,
        "source_artifact": "stage3-corrected-after-network-fix",
        "municipalities": 144,
        "criteria": criteria,
        "ibge_boundary_release": "PA_Municipios_2023.zip",
        "map_crs": "EPSG:5880",
        "geographic_crs": "EPSG:4674",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
