from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StructuralAuditResult:
    spearman: pd.DataFrame
    vif: pd.Series
    pca_loadings: pd.DataFrame
    pca_explained_variance_ratio: pd.Series
    block_variance_share: pd.Series
    seasonal_spearman: float | None
    seasonal_rank_change: pd.Series | None
    implicit_indicator_weights: pd.Series
    equal_block_weights: pd.Series


def _numeric_complete(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    cols = list(columns)
    x = df[cols].apply(pd.to_numeric, errors="coerce")
    return x.dropna(axis=0, how="any")


def spearman_matrix(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    x = _numeric_complete(df, columns)
    if len(x) < 3:
        raise ValueError("At least three complete observations are required.")
    return x.corr(method="spearman")


def vif_series(df: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    x = _numeric_complete(df, columns).astype(float)
    if len(x) <= len(x.columns):
        raise ValueError("VIF requires more complete observations than variables.")
    z = (x - x.mean()) / x.std(ddof=0).replace(0, np.nan)
    if z.isna().any().any():
        constant = z.columns[z.isna().any()].tolist()
        raise ValueError(f"Constant or invalid variables for VIF: {constant}")
    out: dict[str, float] = {}
    for target in z.columns:
        y = z[target].to_numpy()
        predictors = z.drop(columns=target).to_numpy()
        predictors = np.column_stack([np.ones(len(predictors)), predictors])
        beta, *_ = np.linalg.lstsq(predictors, y, rcond=None)
        fitted = predictors @ beta
        ss_res = float(np.sum((y - fitted) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
        out[target] = np.inf if r2 >= 1.0 - 1e-12 else 1.0 / (1.0 - r2)
    return pd.Series(out, name="VIF").sort_values(ascending=False)


def pca_diagnostics(
    df: pd.DataFrame,
    columns: Iterable[str],
    blocks: Mapping[str, Iterable[str]],
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    cols = list(columns)
    x = _numeric_complete(df, cols).astype(float)
    z = (x - x.mean()) / x.std(ddof=0).replace(0, np.nan)
    if z.isna().any().any():
        raise ValueError("PCA cannot be computed with constant variables.")
    matrix = z.to_numpy()
    _, singular_values, vt = np.linalg.svd(matrix, full_matrices=False)
    eigenvalues = singular_values**2 / max(len(matrix) - 1, 1)
    explained = eigenvalues / eigenvalues.sum()
    component_names = [f"PC{i+1}" for i in range(len(explained))]
    loadings = pd.DataFrame(vt.T, index=cols, columns=component_names)
    explained_s = pd.Series(explained, index=component_names, name="explained_variance_ratio")

    # Block contribution to total standardized variance. This is deliberately simple:
    # each standardized variable contributes unit variance, so a block's share exposes
    # cardinality-driven dominance before any model aggregation.
    valid_blocks: dict[str, list[str]] = {
        name: [c for c in block_cols if c in cols] for name, block_cols in blocks.items()
    }
    total = sum(len(v) for v in valid_blocks.values())
    shares = {
        name: (len(block_cols) / total if total else np.nan)
        for name, block_cols in valid_blocks.items()
    }
    return loadings, explained_s, pd.Series(shares, name="standardized_variance_share")


def seasonal_rank_stability(
    df: pd.DataFrame,
    id_col: str,
    flood_col: str,
    dry_col: str,
    higher_is_worse: bool = True,
) -> tuple[float, pd.Series]:
    x = df[[id_col, flood_col, dry_col]].copy()
    x[flood_col] = pd.to_numeric(x[flood_col], errors="coerce")
    x[dry_col] = pd.to_numeric(x[dry_col], errors="coerce")
    x = x.dropna()
    if len(x) < 3:
        raise ValueError("At least three paired seasonal observations are required.")
    corr = float(x[[flood_col, dry_col]].corr(method="spearman").iloc[0, 1])
    ascending = not higher_is_worse
    flood_rank = x[flood_col].rank(method="average", ascending=ascending)
    dry_rank = x[dry_col].rank(method="average", ascending=ascending)
    change = pd.Series(
        (flood_rank - dry_rank).abs().to_numpy(),
        index=x[id_col].astype(str),
        name="absolute_rank_change",
    ).sort_values(ascending=False)
    return corr, change


def implicit_weight_audit(blocks: Mapping[str, Iterable[str]]) -> tuple[pd.Series, pd.Series]:
    counts = {name: len(list(cols)) for name, cols in blocks.items()}
    total = sum(counts.values())
    if total == 0:
        raise ValueError("At least one indicator is required.")
    equal_indicator = pd.Series(
        {name: count / total for name, count in counts.items()},
        name="implicit_weight_equal_indicator",
    )
    n_blocks = len(counts)
    equal_block = pd.Series(
        {name: 1.0 / n_blocks for name in counts},
        name="declared_weight_equal_block",
    )
    return equal_indicator, equal_block


def run_structural_audit(
    df: pd.DataFrame,
    indicator_columns: Iterable[str],
    blocks: Mapping[str, Iterable[str]],
    *,
    id_col: str | None = None,
    flood_col: str | None = None,
    dry_col: str | None = None,
) -> StructuralAuditResult:
    cols = list(indicator_columns)
    spearman = spearman_matrix(df, cols)
    vif = vif_series(df, cols)
    loadings, explained, block_share = pca_diagnostics(df, cols, blocks)
    implicit, equal_block = implicit_weight_audit(blocks)
    seasonal_corr = None
    seasonal_change = None
    if id_col and flood_col and dry_col:
        seasonal_corr, seasonal_change = seasonal_rank_stability(
            df, id_col=id_col, flood_col=flood_col, dry_col=dry_col
        )
    return StructuralAuditResult(
        spearman=spearman,
        vif=vif,
        pca_loadings=loadings,
        pca_explained_variance_ratio=explained,
        block_variance_share=block_share,
        seasonal_spearman=seasonal_corr,
        seasonal_rank_change=seasonal_change,
        implicit_indicator_weights=implicit,
        equal_block_weights=equal_block,
    )
