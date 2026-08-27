from __future__ import annotations

import argparse
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

IBGE_PA_2023 = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_2023/UFs/PA/PA_Municipios_2023.zip"
)


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
        raise RuntimeError(f"Could not identify municipality code column in IBGE layer: {list(gdf.columns)}")
    code_col = code_candidates[0]
    gdf["municipality_code"] = gdf[code_col].astype(str).str.replace(".0", "", regex=False).str.zfill(7)
    if gdf["municipality_code"].nunique() != 144:
        raise RuntimeError(f"Expected 144 Pará municipalities, got {gdf['municipality_code'].nunique()}")
    return gdf[["municipality_code", "geometry"]].copy()


def write_tables(src: pd.DataFrame, out: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    src = src.copy()
    src["municipality_code"] = src["municipality_code"].astype(str).str.zfill(7)

    prom_cols = [
        "municipality_code", "municipality_name", "accessibility_coverage_status",
        "promethee_positive_flow", "promethee_negative_flow", "promethee_net_flow",
        "promethee_rank", "mean_pairwise_comparable_weight_fraction",
        "coverage_limited_rank_flag", "robustness_mean_rank", "robustness_sd_rank",
        "robustness_best_rank", "robustness_worst_rank",
        "robustness_top10_probability", "robustness_top_quartile_probability",
    ]
    prom = src[prom_cols].copy().sort_values("promethee_rank")
    prom["top_10"] = prom["promethee_rank"].le(10)
    prom["top_quartile"] = prom["promethee_rank"].le(36)

    topsis_cols = [
        "municipality_code", "municipality_name", "accessibility_coverage_status",
        "topsis_contrast_score", "topsis_contrast_rank", "coverage_limited_rank_flag",
    ]
    topsis = src[topsis_cols].copy()
    topsis["top_10"] = topsis["topsis_contrast_rank"].le(10)
    topsis["top_quartile"] = topsis["topsis_contrast_rank"].le(36)
    topsis = topsis.sort_values(["topsis_contrast_rank", "municipality_name"], na_position="last")

    tables = out / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    prom.to_csv(tables / "promethee_ii_full_ranking.csv", index=False)
    topsis.to_csv(tables / "topsis_full_ranking.csv", index=False)
    return prom, topsis


def map_rank(gdf: gpd.GeoDataFrame, table: pd.DataFrame, rank_col: str, title: str, stem: str, out: Path) -> None:
    m = gdf.merge(table, on="municipality_code", how="left", validate="one_to_one")
    if len(m) != 144:
        raise RuntimeError("Map join did not retain 144 municipalities")

    fig, ax = plt.subplots(figsize=(10, 9))
    m.plot(
        column=rank_col,
        cmap="viridis_r",
        linewidth=0.35,
        edgecolor="0.45",
        legend=True,
        missing_kwds={"color": "0.92", "edgecolor": "0.25", "hatch": "///", "label": "Sem rank completo"},
        ax=ax,
    )

    top = m[m[rank_col].le(10)].copy()
    top.boundary.plot(ax=ax, linewidth=1.4, edgecolor="black")
    for _, r in top.iterrows():
        p = r.geometry.representative_point()
        ax.text(p.x, p.y, str(int(r[rank_col])), ha="center", va="center", fontsize=7, fontweight="bold")

    limited = m[m["coverage_limited_rank_flag"].fillna(False)].copy()
    if not limited.empty:
        limited.boundary.plot(ax=ax, linewidth=1.5, edgecolor="black", linestyle="--")

    ax.set_title(title, fontsize=13)
    ax.set_axis_off()
    ax.text(
        0.01, 0.01,
        "Números = top-10. Linha tracejada = cobertura limitada.\nMalha municipal: IBGE 2023.",
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
    )
    fig.tight_layout()
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    fig.savefig(figs / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(figs / f"{stem}.svg", bbox_inches="tight")
    plt.close(fig)


def write_readme(out: Path, prom: pd.DataFrame, topsis: pd.DataFrame, metadata: dict) -> None:
    top_prom = prom.head(10)[["promethee_rank", "municipality_name", "promethee_net_flow"]]
    top_top = topsis.dropna(subset=["topsis_contrast_rank"]).head(10)[["topsis_contrast_rank", "municipality_name", "topsis_contrast_score"]]

    lines = [
        "# Stage 4 — MCDM results",
        "",
        "This directory contains the **authoritative corrected** municipal prioritization outputs after the multimodal network correction.",
        "",
        "## Authoritative provenance",
        "",
        f"- Corrected OD workflow run: `{metadata['corrected_od_run']}`",
        f"- Corrected Stage 3/Stage 4 workflow run: `{metadata['stage4_run']}`",
        f"- Source artifact: `{metadata['source_artifact']}`",
        "- PROMETHEE II is the primary MCDM method.",
        "- TOPSIS is an independent contrast method.",
        "- Afuá is retained as a coverage/scope-limited municipality; no synthetic accessibility value is created.",
        "",
        "## Complete tables",
        "",
        "- [PROMETHEE II — full 144-municipality table](tables/promethee_ii_full_ranking.csv)",
        "- [TOPSIS — full 144-municipality table](tables/topsis_full_ranking.csv)",
        "",
        "The TOPSIS table contains all 144 municipalities, but Afuá has no TOPSIS rank because TOPSIS requires a complete criterion vector. This is intentional and should not be imputed.",
        "",
        "## Statewide maps",
        "",
        "### PROMETHEE II",
        "",
        "![PROMETHEE II rank map](figures/promethee_ii_rank_map.png)",
        "",
        "Vector version: [SVG](figures/promethee_ii_rank_map.svg)",
        "",
        "### TOPSIS",
        "",
        "![TOPSIS rank map](figures/topsis_rank_map.png)",
        "",
        "Vector version: [SVG](figures/topsis_rank_map.svg)",
        "",
        "## PROMETHEE II reference top 10",
        "",
        "| Rank | Municipality | Net flow |",
        "|---:|---|---:|",
    ]
    for r in top_prom.itertuples(index=False):
        lines.append(f"| {int(r.promethee_rank)} | {r.municipality_name} | {r.promethee_net_flow:.6f} |")

    lines += [
        "",
        "## TOPSIS contrast top 10",
        "",
        "| Rank | Municipality | TOPSIS score |",
        "|---:|---|---:|",
    ]
    for r in top_top.itertuples(index=False):
        lines.append(f"| {int(r.topsis_contrast_rank)} | {r.municipality_name} | {r.topsis_contrast_score:.6f} |")

    lines += [
        "",
        "## Interpretation",
        "",
        "The maps visualize rank, while the CSV files preserve the method-specific scores and the full municipal ordering. Exact rank should not be interpreted as a deterministic policy truth; the manuscript should report the reference ordering together with weight robustness, PROMETHEE–TOPSIS agreement, and preference/scaling sensitivity.",
        "",
        "The corrected PROMETHEE II and TOPSIS rankings have very high agreement on the 143 complete alternatives (Spearman approximately 0.9984).",
        "",
        "## Reproducibility",
        "",
        "The publication files in this directory are generated by `src/analysis/publish_stage4_results.py` through `.github/workflows/publish-stage4-results.yml`. Municipal geometry is downloaded from the official IBGE 2023 municipal boundary release for Pará.",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ranking", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("results/stage4"))
    args = p.parse_args()

    src = pd.read_csv(args.ranking, dtype={"municipality_code": str}, low_memory=False)
    if len(src) != 144 or src["municipality_code"].nunique() != 144:
        raise RuntimeError("Expected one row for each of the 144 municipalities")

    args.out.mkdir(parents=True, exist_ok=True)
    prom, topsis = write_tables(src, args.out)
    gdf = load_ibge_pa()

    map_rank(gdf, prom, "promethee_rank", "Pará — PROMETHEE II reference ranking", "promethee_ii_rank_map", args.out)
    map_rank(gdf, topsis, "topsis_contrast_rank", "Pará — TOPSIS contrast ranking", "topsis_rank_map", args.out)

    metadata = {
        "corrected_od_run": 33089335405,
        "stage4_run": 33090126353,
        "source_artifact": "stage4-mcdm-corrected-after-network-fix",
        "municipalities": 144,
        "topsis_complete_ranked": int(topsis["topsis_contrast_rank"].notna().sum()),
        "promethee_ranked": int(prom["promethee_rank"].notna().sum()),
        "ibge_boundary_release": "PA_Municipios_2023.zip",
        "ibge_boundary_url": IBGE_PA_2023,
    }
    (args.out / "publication_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(args.out, prom, topsis, metadata)

    if metadata["promethee_ranked"] != 144:
        raise RuntimeError("PROMETHEE publication must rank all 144 rows")
    if metadata["topsis_complete_ranked"] != 143:
        raise RuntimeError("TOPSIS publication must rank exactly 143 complete municipalities")

    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
