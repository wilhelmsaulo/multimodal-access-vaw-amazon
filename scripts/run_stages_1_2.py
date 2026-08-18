from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.accessibility.e2sfca import compare_seasons, e2sfca, exponential_decay
from src.accessibility.spatial_stats import global_moran, local_moran_lisa
from src.analysis.structural_audit import run_structural_audit


def parse_blocks(text: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, cols = chunk.split("=", 1)
        blocks[name.strip()] = [c.strip() for c in cols.split(",") if c.strip()]
    if not blocks:
        raise ValueError("At least one indicator block must be declared.")
    return blocks


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage 1 structural audit and Stage 2 E2SFCA.")
    parser.add_argument("--indicator-table", type=Path, required=True)
    parser.add_argument("--blocks", required=True, help="e.g. transport=walk,road,river;services=health,creas")
    parser.add_argument("--indicator-id", default="origin_id")
    parser.add_argument("--flood-indicator")
    parser.add_argument("--dry-indicator")
    parser.add_argument("--origins", type=Path, required=True)
    parser.add_argument("--services", type=Path, required=True)
    parser.add_argument("--travel", type=Path, required=True)
    parser.add_argument("--neighbors", type=Path)
    parser.add_argument("--threshold", type=float, default=240.0)
    parser.add_argument("--decay-beta", type=float, default=0.01)
    parser.add_argument("--output-dir", type=Path, default=Path("results/tables/stage1_stage2"))
    args = parser.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    indicators = pd.read_csv(args.indicator_table)
    blocks = parse_blocks(args.blocks)
    indicator_columns = [col for cols in blocks.values() for col in cols]
    audit = run_structural_audit(
        indicators,
        indicator_columns,
        blocks,
        id_col=args.indicator_id if args.flood_indicator and args.dry_indicator else None,
        flood_col=args.flood_indicator,
        dry_col=args.dry_indicator,
    )
    audit.spearman.to_csv(out / "stage1_spearman.csv")
    audit.vif.to_csv(out / "stage1_vif.csv", header=True)
    audit.pca_loadings.to_csv(out / "stage1_pca_loadings.csv")
    audit.pca_explained_variance_ratio.to_csv(out / "stage1_pca_explained_variance.csv", header=True)
    audit.block_variance_share.to_csv(out / "stage1_block_variance_share.csv", header=True)
    audit.implicit_indicator_weights.to_csv(out / "stage1_implicit_equal_indicator_weights.csv", header=True)
    audit.equal_block_weights.to_csv(out / "stage1_equal_block_weights.csv", header=True)
    if audit.seasonal_rank_change is not None:
        audit.seasonal_rank_change.to_csv(out / "stage1_seasonal_rank_change.csv", header=True)
        pd.DataFrame({"seasonal_spearman": [audit.seasonal_spearman]}).to_csv(
            out / "stage1_seasonal_spearman.csv", index=False
        )

    origins = pd.read_csv(args.origins, dtype={"origin_id": str})
    services = pd.read_csv(args.services, dtype={"service_id": str})
    travel = pd.read_csv(args.travel, dtype={"origin_id": str, "service_id": str})
    result = e2sfca(
        travel,
        origins,
        services,
        threshold_minutes=args.threshold,
        decay=exponential_decay(args.decay_beta),
    )
    result.service_ratios.to_csv(out / "stage2_service_supply_demand_ratios.csv", index=False)
    result.sector_scores.to_csv(out / "stage2_sector_e2sfca_scores.csv", index=False)

    try:
        seasonal = compare_seasons(result.sector_scores)
    except ValueError:
        seasonal = None
    if seasonal is not None:
        seasonal.to_csv(out / "stage2_flood_dry_comparison.csv", index=False)

    if args.neighbors:
        edges = pd.read_csv(args.neighbors, dtype={"source_id": str, "target_id": str})
        for (scenario, service_type), group in result.sector_scores.groupby(["scenario", "service_type"]):
            values = group.rename(columns={"origin_id": "spatial_id", "e2sfca_score": "value"})
            moran = global_moran(values, edges, id_col="spatial_id", value_col="value")
            lisa = local_moran_lisa(values, edges, id_col="spatial_id", value_col="value")
            stem = f"{scenario}__{service_type}".replace("/", "_").replace(" ", "_")
            pd.DataFrame(
                {
                    "scenario": [scenario],
                    "service_type": [service_type],
                    "moran_i": [moran.moran_i],
                    "expected_i": [moran.expected_i],
                    "pseudo_p_two_sided": [moran.pseudo_p_two_sided],
                }
            ).to_csv(out / f"stage2_global_moran__{stem}.csv", index=False)
            lisa.to_csv(out / f"stage2_lisa__{stem}.csv", index=False)


if __name__ == "__main__":
    main()
