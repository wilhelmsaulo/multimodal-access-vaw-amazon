from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

from publish_stage3_results import (
    GEO_CRS,
    MAP_CRS,
    add_geographic_graticule,
    add_north_arrow,
    add_scale_bar,
    load_ibge_pa,
)


STYLE = {
    "health": ("Saúde especializada", "#0072B2", "o"),
    "creas": ("CREAS", "#009E73", "s"),
    "specialized_security": ("Segurança especializada", "#D55E00", "^"),
    "specialized_justice": ("Justiça especializada", "#CC79A7", "D"),
}


def physical_sites(services: pd.DataFrame) -> pd.DataFrame:
    required = {
        "service_id", "service_name", "service_type", "provider_source",
        "municipality_code", "latitude", "longitude", "reference_date",
        "validation_status",
    }
    missing = required - set(services.columns)
    if missing:
        raise RuntimeError(f"Missing service columns: {sorted(missing)}")
    services = services.copy()
    services["latitude"] = pd.to_numeric(services["latitude"], errors="coerce")
    services["longitude"] = pd.to_numeric(services["longitude"], errors="coerce")
    services = services.dropna(subset=["latitude", "longitude"])
    services = services[
        services["latitude"].between(-10, 3)
        & services["longitude"].between(-60, -45)
        & services["service_type"].isin(STYLE)
    ].copy()
    # Multiple court secretariats can occupy the same validated physical site.
    # The map represents physical opportunities, while the audit table preserves
    # how many functional records each point consolidates.
    grouped = []
    keys = ["service_type", "latitude", "longitude"]
    for _, d in services.groupby(keys, sort=False, dropna=False):
        row = d.iloc[0].copy()
        row["functional_records"] = len(d)
        row["service_ids"] = " | ".join(sorted(d["service_id"].astype(str)))
        row["service_names"] = " | ".join(sorted(d["service_name"].astype(str)))
        grouped.append(row)
    sites = pd.DataFrame(grouped)
    expected = {"health": 71, "creas": 138, "specialized_security": 21, "specialized_justice": 6}
    observed = sites["service_type"].value_counts().to_dict()
    if observed != expected or len(sites) != 236:
        raise RuntimeError(f"Unexpected physical-site universe: {observed}; total={len(sites)}")
    return sites


def plot_map(boundaries: gpd.GeoDataFrame, sites: pd.DataFrame, types: list[str], title: str, path: Path) -> None:
    base_geo = boundaries.to_crs(epsg=GEO_CRS)
    extent = tuple(base_geo.total_bounds.tolist())
    base = base_geo.to_crs(epsg=MAP_CRS)
    points = gpd.GeoDataFrame(
        sites,
        geometry=gpd.points_from_xy(sites["longitude"], sites["latitude"]),
        crs=f"EPSG:{GEO_CRS}",
    ).to_crs(epsg=MAP_CRS)

    fig, ax = plt.subplots(figsize=(11, 9.5))
    base.plot(ax=ax, color="#F3F1EA", edgecolor="#666666", linewidth=0.35, zorder=1)
    add_geographic_graticule(ax, extent)
    for service_type in types:
        label, color, marker = STYLE[service_type]
        d = points[points["service_type"] == service_type]
        ax.scatter(
            d.geometry.x, d.geometry.y, s=34 if len(types) == 1 else 25,
            c=color, marker=marker, edgecolors="white", linewidths=0.45,
            alpha=0.90, label=f"{label} (n={len(d)})", zorder=3,
        )
    add_north_arrow(ax)
    add_scale_bar(ax)
    ax.set_title(title, fontsize=14, pad=12)
    ax.legend(loc="lower right", frameon=True, framealpha=0.96, fontsize=8)
    ax.set_axis_off()
    ax.text(
        0.01, 0.005,
        "Fontes: CNES (jul. 2026); MDS/SAGI (ago. 2026); PCPA/SEGUP e TJPA (ago. 2026); malha IBGE 2023.\n"
        "Projeção: SIRGAS 2000 / Brazil Polyconic (EPSG:5880); coordenadas: SIRGAS 2000 (EPSG:4674).",
        transform=ax.transAxes, fontsize=7.2, va="bottom",
    )
    fig.tight_layout()
    fig.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("results/stage1_services"))
    args = parser.parse_args()
    out = args.out
    figures = out / "figures"
    tables = out / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(args.inventory, dtype={"municipality_code": str}, low_memory=False)
    sites = physical_sites(raw)
    sites.drop(columns="geometry", errors="ignore").to_csv(tables / "validated_physical_service_sites.csv", index=False)
    summary = (
        sites.groupby("service_type", as_index=False)
        .agg(physical_sites=("service_id", "size"), functional_records=("functional_records", "sum"))
    )
    summary["label"] = summary["service_type"].map(lambda x: STYLE[x][0])
    summary.to_csv(tables / "service_site_summary.csv", index=False)

    boundaries = load_ibge_pa()
    plot_map(boundaries, sites, list(STYLE), "Pará — equipamentos e serviços de resposta à VCM", figures / "all_service_sites")
    for service_type, (label, _, _) in STYLE.items():
        plot_map(boundaries, sites, [service_type], f"Pará — {label}", figures / f"service_sites__{service_type}")

    readme = [
        "# Item 1 — equipamentos e serviços", "",
        "Este pacote publica os 236 locais físicos validados usados na camada institucional do estudo. Registros funcionais que compartilham exatamente o mesmo local físico e tipo de serviço são representados por um único ponto; a tabela de auditoria preserva essa consolidação.", "",
        "## Mapas", "",
        "![Todos os serviços](figures/all_service_sites.png)", "",
        "- [Saúde especializada](figures/service_sites__health.png)",
        "- [CREAS](figures/service_sites__creas.png)",
        "- [Segurança especializada](figures/service_sites__specialized_security.png)",
        "- [Justiça especializada](figures/service_sites__specialized_justice.png)", "",
        "Versões SVG editáveis acompanham todos os mapas.", "",
        "## Tabelas", "",
        "- [Inventário cartográfico dos locais físicos](tables/validated_physical_service_sites.csv)",
        "- [Resumo por tipo](tables/service_site_summary.csv)", "",
        "## Limite interpretativo", "",
        "Os pontos representam oportunidades físicas validadas, não capacidade, qualidade, produtividade ou utilização efetiva dos serviços.", "",
    ]
    (out / "README.md").write_text("\n".join(readme), encoding="utf-8")
    metadata = {
        "item": 1,
        "status": "authoritative_published_visualization",
        "source_service_inventory_run": 33021740349,
        "source_artifact": "service-inventory-pa",
        "functional_records": int(summary["functional_records"].sum()),
        "physical_sites": int(summary["physical_sites"].sum()),
        "physical_sites_by_type": dict(zip(summary["service_type"], summary["physical_sites"].astype(int))),
        "map_crs": "EPSG:5880",
        "geographic_crs": "EPSG:4674",
        "cartographic_elements": ["title", "legend", "scale", "north_arrow", "geographic_coordinates", "source_year", "projection_and_crs"],
    }
    (out / "publication_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
