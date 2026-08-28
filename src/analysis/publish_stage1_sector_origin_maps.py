from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm
from matplotlib.patches import Patch

from publish_stage3_results import (
    GEO_CRS,
    MAP_CRS,
    add_geographic_graticule,
    add_north_arrow,
    add_scale_bar,
)


def finish_map(ax, extent, title: str, source: str) -> None:
    add_geographic_graticule(ax, extent)
    add_north_arrow(ax)
    add_scale_bar(ax)
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_axis_off()
    ax.text(
        0.01, 0.005,
        source + "\nProjeção: SIRGAS 2000 / Brazil Polyconic (EPSG:5880); coordenadas: SIRGAS 2000 (EPSG:4674).",
        transform=ax.transAxes, fontsize=7.2, va="bottom",
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--census-gpkg", type=Path, required=True)
    p.add_argument("--endpoints", type=Path, required=True)
    p.add_argument("--reachability", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("results/stage1_sector_origins"))
    args = p.parse_args()
    out = args.out
    figures = out / "figures"
    tables = out / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    sectors = gpd.read_file(args.census_gpkg)
    if len(sectors) != 16714 or sectors["CD_SETOR"].astype(str).nunique() != 16714:
        raise RuntimeError("Expected 16,714 unique Pará Census 2022 sectors")
    sectors["sector_id"] = sectors["CD_SETOR"].astype(str)
    sectors["female_population"] = pd.to_numeric(sectors["female_population"], errors="coerce")
    sectors["sector_situation"] = sectors["SITUACAO"].astype(str).str.strip().str.lower().map(
        lambda x: "Urbano" if "urban" in x else ("Rural" if "rural" in x else "Não classificado")
    )
    endpoints = pd.read_csv(args.endpoints, dtype={"origin_id": str})
    reach = pd.read_csv(args.reachability, dtype={"origin_id": str})
    if len(endpoints) != 12673 or endpoints["origin_id"].nunique() != 12673:
        raise RuntimeError("Expected 12,673 frozen routing-ready origins")
    if len(reach) != 12673 or reach["origin_id"].nunique() != 12673:
        raise RuntimeError("Expected reachability summaries for all routing-ready origins")
    reachable = set(reach.loc[pd.to_numeric(reach["reachable_services"], errors="raise") > 0, "origin_id"])
    zero = set(reach.loc[pd.to_numeric(reach["reachable_services"], errors="raise") == 0, "origin_id"])
    ready = set(endpoints["origin_id"])
    if reachable & zero or reachable | zero != ready:
        raise RuntimeError("Reachability classes do not partition routing-ready origins")

    sectors["access_status"] = "Não avaliado — sem origem primária pronta"
    sectors.loc[sectors["sector_id"].isin(zero), "access_status"] = "Sem serviço alcançável na rede de referência"
    sectors.loc[sectors["sector_id"].isin(reachable), "access_status"] = "Com serviço alcançável na rede de referência"
    summary = (
        sectors.groupby("access_status", as_index=False)
        .agg(sectors=("sector_id", "size"), female_population=("female_population", "sum"))
    )
    summary.to_csv(tables / "sector_access_status_summary.csv", index=False)
    situation = sectors.groupby("sector_situation", as_index=False).agg(
        sectors=("sector_id", "size"), female_population=("female_population", "sum")
    )
    situation.to_csv(tables / "sector_distribution_summary.csv", index=False)
    pd.DataFrame({
        "metric": ["sectors", "routing_ready_origins", "female_population_observed", "female_population_missing_sectors"],
        "value": [len(sectors), len(ready), float(sectors["female_population"].sum()), int(sectors["female_population"].isna().sum())],
    }).to_csv(tables / "sector_origin_audit.csv", index=False)

    geo = sectors.to_crs(epsg=GEO_CRS)
    extent = tuple(geo.total_bounds.tolist())
    m = geo.to_crs(epsg=MAP_CRS)

    # 1. Spatial distribution of sectors, with one representative point per sector.
    points = m.copy()
    points.geometry = points.geometry.representative_point()
    colors = {"Urbano": "#0072B2", "Rural": "#E69F00", "Não classificado": "#999999"}
    fig, ax = plt.subplots(figsize=(11, 9.5))
    m.dissolve().boundary.plot(ax=ax, color="#555555", linewidth=0.6, zorder=1)
    for label, color in colors.items():
        d = points[points["sector_situation"] == label]
        if len(d):
            ax.scatter(d.geometry.x, d.geometry.y, s=3.2, c=color, alpha=0.55, linewidths=0, label=f"{label} (n={len(d):,})", zorder=2)
    ax.legend(loc="lower right", fontsize=8, framealpha=0.96)
    finish_map(ax, extent, "Pará — distribuição dos setores censitários de 2022", "Fonte: IBGE, Censo Demográfico 2022.")
    fig.tight_layout(); fig.savefig(figures / "census_sector_distribution.png", dpi=300, bbox_inches="tight"); plt.close(fig)

    # 2. Female population per sector; zeros/missing are not silently transformed.
    fig, ax = plt.subplots(figsize=(11, 9.5))
    positive = m[m["female_population"] > 0]
    vmax = max(float(positive["female_population"].quantile(0.995)), 1.0)
    m.plot(ax=ax, color="#E6E6E6", edgecolor="none", zorder=1)
    positive.plot(
        ax=ax, column="female_population", cmap="viridis", norm=LogNorm(vmin=1, vmax=vmax),
        linewidth=0, legend=True, legend_kwds={"label": "População feminina por setor (escala logarítmica)", "shrink": 0.72}, zorder=2,
    )
    m.dissolve().boundary.plot(ax=ax, color="#555555", linewidth=0.6, zorder=3)
    finish_map(ax, extent, "Pará — população feminina por setor censitário", "Fonte: IBGE, Censo Demográfico 2022; valores ausentes/suprimidos não foram imputados.")
    fig.tight_layout(); fig.savefig(figures / "female_population_by_sector.png", dpi=300, bbox_inches="tight"); plt.close(fig)

    # 3. Actual reference-network status, preserving the coverage-limited class.
    status_colors = {
        "Com serviço alcançável na rede de referência": "#009E73",
        "Sem serviço alcançável na rede de referência": "#D55E00",
        "Não avaliado — sem origem primária pronta": "#BDBDBD",
    }
    fig, ax = plt.subplots(figsize=(11, 9.5))
    for status, color in status_colors.items():
        d = m[m["access_status"] == status]
        d.plot(ax=ax, color=color, edgecolor="none", linewidth=0, zorder=1)
    m.dissolve().boundary.plot(ax=ax, color="#555555", linewidth=0.6, zorder=2)
    handles = [Patch(facecolor=c, label=f"{s} (n={(m['access_status']==s).sum():,})") for s, c in status_colors.items()]
    ax.legend(handles=handles, loc="lower right", fontsize=7.5, framealpha=0.96)
    finish_map(ax, extent, "Pará — situação de acesso dos setores na rede de referência", "Fontes: IBGE Censo 2022; endpoints congelados e matriz OD multimodal corrigida (2026).")
    fig.tight_layout(); fig.savefig(figures / "sector_reference_network_access.png", dpi=300, bbox_inches="tight"); plt.close(fig)

    readme = [
        "# Item 3 — origens por setor censitário", "",
        "O pacote representa os 16.714 setores censitários do Pará e preserva separadamente três situações: setor com ao menos um serviço alcançável, setor roteável sem serviço alcançável e setor não avaliado por ausência de origem primária pronta. A terceira classe não é interpretada como inacessibilidade.", "",
        "## Figuras", "",
        "![Distribuição dos setores](figures/census_sector_distribution.png)", "",
        "![População feminina](figures/female_population_by_sector.png)", "",
        "![Situação de acesso](figures/sector_reference_network_access.png)", "",
        "## Tabelas", "",
        "- [Resumo da distribuição setorial](tables/sector_distribution_summary.csv)",
        "- [Resumo da situação de acesso](tables/sector_access_status_summary.csv)",
        "- [Auditoria das origens](tables/sector_origin_audit.csv)", "",
    ]
    (out / "README.md").write_text("\n".join(readme), encoding="utf-8")
    metadata = {
        "item": 3,
        "status": "authoritative_published_visualization",
        "census_sector_run": 32170796657,
        "routing_endpoint_run": 32945266691,
        "corrected_od_run": 33089335405,
        "sectors": 16714,
        "routing_ready_origins": 12673,
        "map_crs": "EPSG:5880",
        "geographic_crs": "EPSG:4674",
        "coverage_limited_class_preserved": True,
    }
    (out / "publication_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
