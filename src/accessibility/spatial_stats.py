from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MoranResult:
    moran_i: float
    expected_i: float
    pseudo_p_two_sided: float


def _weight_matrix(ids: pd.Index, edges: pd.DataFrame, source_col: str, target_col: str) -> np.ndarray:
    pos = {str(v): i for i, v in enumerate(ids.astype(str))}
    w = np.zeros((len(ids), len(ids)), dtype=float)
    for row in edges[[source_col, target_col]].itertuples(index=False):
        a, b = str(row[0]), str(row[1])
        if a not in pos or b not in pos or a == b:
            continue
        i, j = pos[a], pos[b]
        w[i, j] = 1.0
        w[j, i] = 1.0
    row_sum = w.sum(axis=1)
    nonzero = row_sum > 0
    w[nonzero] = w[nonzero] / row_sum[nonzero, None]
    return w


def global_moran(
    values: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    id_col: str,
    value_col: str,
    source_col: str = "source_id",
    target_col: str = "target_id",
    permutations: int = 999,
    seed: int = 42,
) -> MoranResult:
    x = values[[id_col, value_col]].dropna().copy()
    x[id_col] = x[id_col].astype(str)
    x = x.drop_duplicates(id_col).sort_values(id_col)
    y = pd.to_numeric(x[value_col], errors="raise").to_numpy(dtype=float)
    if len(y) < 3 or np.isclose(y.var(), 0):
        raise ValueError("Moran's I requires at least three non-constant observations.")
    w = _weight_matrix(x[id_col], edges, source_col, target_col)
    s0 = w.sum()
    if s0 == 0:
        raise ValueError("No valid spatial-neighbor edges for supplied IDs.")
    z = y - y.mean()
    denominator = float(z @ z)

    def _stat(arr: np.ndarray) -> float:
        return float((len(arr) / s0) * ((arr @ w @ arr) / (arr @ arr)))

    observed = _stat(z)
    rng = np.random.default_rng(seed)
    permuted = np.array([_stat(rng.permutation(z)) for _ in range(permutations)])
    extreme = np.sum(np.abs(permuted - permuted.mean()) >= abs(observed - permuted.mean()))
    p = float((extreme + 1) / (permutations + 1))
    return MoranResult(observed, -1.0 / (len(y) - 1), p)


def local_moran_lisa(
    values: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    id_col: str,
    value_col: str,
    source_col: str = "source_id",
    target_col: str = "target_id",
    permutations: int = 999,
    seed: int = 42,
) -> pd.DataFrame:
    x = values[[id_col, value_col]].dropna().copy()
    x[id_col] = x[id_col].astype(str)
    x = x.drop_duplicates(id_col).sort_values(id_col).reset_index(drop=True)
    y = pd.to_numeric(x[value_col], errors="raise").to_numpy(dtype=float)
    if len(y) < 3 or np.isclose(y.var(), 0):
        raise ValueError("LISA requires at least three non-constant observations.")
    z = (y - y.mean()) / y.std(ddof=0)
    w = _weight_matrix(x[id_col], edges, source_col, target_col)
    lag = w @ z
    local_i = z * lag

    quadrant = np.full(len(z), "Not defined", dtype=object)
    quadrant[(z >= 0) & (lag >= 0)] = "High-High"
    quadrant[(z < 0) & (lag < 0)] = "Low-Low"
    quadrant[(z >= 0) & (lag < 0)] = "High-Low"
    quadrant[(z < 0) & (lag >= 0)] = "Low-High"

    rng = np.random.default_rng(seed)
    counts = np.zeros(len(z), dtype=int)
    for _ in range(permutations):
        zp = rng.permutation(z)
        ip = z * (w @ zp)
        counts += (np.abs(ip) >= np.abs(local_i)).astype(int)
    p = (counts + 1) / (permutations + 1)

    out = x.copy()
    out["z_score"] = z
    out["spatial_lag_z"] = lag
    out["local_moran_i"] = local_i
    out["pseudo_p_two_sided"] = p
    out["lisa_cluster"] = quadrant
    out["significant_0_05"] = out["pseudo_p_two_sided"] <= 0.05
    return out
