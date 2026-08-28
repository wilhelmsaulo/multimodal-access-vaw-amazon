from __future__ import annotations

"""Train and select Stage-5 SOMs across multiple grids and random seeds.

Selection is metric-driven: quantization error, topographic error and mapping
stability across seeds. The SOM is descriptive profiling only and never feeds
back into Stage-4 MCDM ranking.
"""

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("results/stage5/tables")
MATRIX = OUT / "stage5_som_final_standardized_matrix.csv"
GATE = OUT / "stage5_final_feature_gate.json"
GRID_SIZES = [(5, 5), (6, 6), (7, 7)]
SEEDS = list(range(10))
ITERATIONS = 6000
ALPHA_START, ALPHA_END = 0.50, 0.05
SIGMA_END = 0.70


def grid_coords(rows: int, cols: int) -> np.ndarray:
    return np.array([(r, c) for r in range(rows) for c in range(cols)], dtype=float)


def train_som(x: np.ndarray, rows: int, cols: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    coords = grid_coords(rows, cols)
    n_units = len(coords)
    # Initialize from observed profiles with small noise for reproducibility and
    # better support than arbitrary hypercube initialization.
    idx = rng.choice(len(x), size=n_units, replace=n_units > len(x))
    weights = x[idx].copy() + rng.normal(0, 0.05, size=(n_units, x.shape[1]))
    sigma_start = max(rows, cols) / 2.0

    for t in range(ITERATIONS):
        frac = t / max(1, ITERATIONS - 1)
        alpha = ALPHA_START * (ALPHA_END / ALPHA_START) ** frac
        sigma = sigma_start * (SIGMA_END / sigma_start) ** frac
        sample = x[rng.integers(0, len(x))]
        d2 = np.square(weights - sample).sum(axis=1)
        bmu = int(np.argmin(d2))
        gd2 = np.square(coords - coords[bmu]).sum(axis=1)
        h = np.exp(-gd2 / (2.0 * sigma * sigma))[:, None]
        weights += alpha * h * (sample - weights)
    return weights


def bmus(x: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d2 = np.square(x[:, None, :] - weights[None, :, :]).sum(axis=2)
    order = np.argsort(d2, axis=1)[:, :2]
    return order[:, 0], order[:, 1]


def metrics(x: np.ndarray, weights: np.ndarray, rows: int, cols: int) -> tuple[float, float, np.ndarray]:
    coords = grid_coords(rows, cols)
    first, second = bmus(x, weights)
    qe = float(np.linalg.norm(x - weights[first], axis=1).mean())
    delta = np.abs(coords[first] - coords[second])
    # Rectangular lattice: horizontal, vertical and diagonal immediate cells
    # are treated as topological neighbors (Chebyshev distance <= 1).
    adjacent = delta.max(axis=1) <= 1.0
    te = float((~adjacent).mean())
    return qe, te, first


def pairwise_map_distances(bmu_idx: np.ndarray, rows: int, cols: int) -> np.ndarray:
    coords = grid_coords(rows, cols)[bmu_idx]
    pairs = np.array(list(combinations(range(len(coords)), 2)), dtype=int)
    d = np.linalg.norm(coords[pairs[:, 0]] - coords[pairs[:, 1]], axis=1)
    return d / max(1.0, np.sqrt((rows - 1) ** 2 + (cols - 1) ** 2))


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = pd.Series(a).rank(method="average").to_numpy(float)
    rb = pd.Series(b).rank(method="average").to_numpy(float)
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> None:
    gate = json.load(open(GATE, encoding="utf-8"))
    if gate.get("som_training_authorized") is not True:
        raise RuntimeError("Stage-5 final feature gate has not authorized SOM training")

    df = pd.read_csv(MATRIX, dtype={"municipality_code": str})
    features = gate["final_features"]
    if len(df) != 144 or df[features].isna().any().any():
        raise RuntimeError("Frozen SOM matrix failed integrity check")
    x = df[features].to_numpy(float)

    records: list[dict] = []
    maps: dict[tuple[int, int, int], np.ndarray] = {}
    distance_vectors: dict[tuple[int, int, int], np.ndarray] = {}
    weights_store: dict[tuple[int, int, int], np.ndarray] = {}

    for rows, cols in GRID_SIZES:
        for seed in SEEDS:
            w = train_som(x, rows, cols, seed)
            qe, te, bm = metrics(x, w, rows, cols)
            key = (rows, cols, seed)
            maps[key] = bm
            weights_store[key] = w
            distance_vectors[key] = pairwise_map_distances(bm, rows, cols)
            records.append({"grid_rows": rows, "grid_cols": cols, "seed": seed, "quantization_error": qe, "topographic_error": te})

    runs = pd.DataFrame(records)

    # Mapping stability is based on Spearman agreement of all pairwise municipal
    # grid distances across seeds. This is invariant to rotations/reflections of
    # a rectangular SOM and therefore avoids penalizing equivalent maps.
    stability_rows = []
    per_seed_stability: dict[tuple[int, int, int], float] = {}
    for rows, cols in GRID_SIZES:
        keys = [(rows, cols, s) for s in SEEDS]
        corr_matrix = np.eye(len(keys))
        for i, j in combinations(range(len(keys)), 2):
            r = spearman(distance_vectors[keys[i]], distance_vectors[keys[j]])
            corr_matrix[i, j] = corr_matrix[j, i] = r
        mean_seed = (corr_matrix.sum(axis=1) - 1) / (len(keys) - 1)
        for key, st in zip(keys, mean_seed):
            per_seed_stability[key] = float(st)
        vals = corr_matrix[np.triu_indices(len(keys), k=1)]
        stability_rows.append({
            "grid_rows": rows, "grid_cols": cols,
            "mapping_stability_mean_spearman": float(vals.mean()),
            "mapping_stability_median_spearman": float(np.median(vals)),
            "mapping_stability_min_spearman": float(vals.min()),
        })
    stability = pd.DataFrame(stability_rows)
    runs["seed_mapping_stability"] = [per_seed_stability[(int(r.grid_rows), int(r.grid_cols), int(r.seed))] for r in runs.itertuples()]

    summary = runs.groupby(["grid_rows", "grid_cols"], as_index=False).agg(
        qe_median=("quantization_error", "median"),
        qe_mean=("quantization_error", "mean"),
        qe_sd=("quantization_error", "std"),
        te_median=("topographic_error", "median"),
        te_mean=("topographic_error", "mean"),
        te_sd=("topographic_error", "std"),
    ).merge(stability, on=["grid_rows", "grid_cols"], validate="one_to_one")

    # Normalize criteria across candidate grids; lower QE/TE is better, higher
    # stability is better. Equal weights avoid introducing an unreported visual
    # preference for larger maps.
    for col in ["qe_median", "te_median"]:
        lo, hi = summary[col].min(), summary[col].max()
        summary[f"norm_{col}"] = 0.0 if hi == lo else (summary[col] - lo) / (hi - lo)
    stcol = "mapping_stability_median_spearman"
    lo, hi = summary[stcol].min(), summary[stcol].max()
    summary["norm_instability"] = 0.0 if hi == lo else (hi - summary[stcol]) / (hi - lo)
    summary["selection_score"] = (summary["norm_qe_median"] + summary["norm_te_median"] + summary["norm_instability"]) / 3.0
    summary = summary.sort_values(["selection_score", "qe_median", "te_median"]).reset_index(drop=True)
    selected_grid = summary.iloc[0]
    gr, gc = int(selected_grid.grid_rows), int(selected_grid.grid_cols)

    candidates = runs[(runs.grid_rows == gr) & (runs.grid_cols == gc)].copy()
    # Within selected grid, choose a representative stable seed: minimize
    # normalized QE + TE + instability relative to other seeds.
    for col in ["quantization_error", "topographic_error"]:
        lo, hi = candidates[col].min(), candidates[col].max()
        candidates[f"norm_{col}"] = 0.0 if hi == lo else (candidates[col] - lo) / (hi - lo)
    lo, hi = candidates.seed_mapping_stability.min(), candidates.seed_mapping_stability.max()
    candidates["norm_instability"] = 0.0 if hi == lo else (hi - candidates.seed_mapping_stability) / (hi - lo)
    candidates["representative_score"] = (candidates.norm_quantization_error + candidates.norm_topographic_error + candidates.norm_instability) / 3.0
    chosen = candidates.sort_values(["representative_score", "quantization_error"]).iloc[0]
    seed = int(chosen.seed)
    chosen_key = (gr, gc, seed)
    chosen_bmu = maps[chosen_key]
    coords = grid_coords(gr, gc)[chosen_bmu].astype(int)

    mapping = df[["municipality_code", "municipality_name"]].copy()
    mapping["som_grid_rows"] = gr
    mapping["som_grid_cols"] = gc
    mapping["som_seed"] = seed
    mapping["som_bmu_row"] = coords[:, 0]
    mapping["som_bmu_col"] = coords[:, 1]
    mapping["som_bmu_index"] = chosen_bmu
    mapping.to_csv(OUT / "stage5_som_selected_mapping.csv", index=False)

    weights = pd.DataFrame(weights_store[chosen_key], columns=features)
    wc = grid_coords(gr, gc).astype(int)
    weights.insert(0, "som_col", wc[:, 1])
    weights.insert(0, "som_row", wc[:, 0])
    weights.to_csv(OUT / "stage5_som_selected_codebook.csv", index=False)

    runs.to_csv(OUT / "stage5_som_training_runs.csv", index=False)
    summary.to_csv(OUT / "stage5_som_grid_selection.csv", index=False)
    candidates.sort_values("representative_score").to_csv(OUT / "stage5_som_selected_grid_seed_selection.csv", index=False)

    audit = {
        "stage": "Stage 5 SOM multi-grid multi-seed training and selection",
        "municipalities": 144,
        "feature_count": len(features),
        "features": features,
        "candidate_grids": [list(x) for x in GRID_SIZES],
        "seeds_per_grid": len(SEEDS),
        "total_models": len(runs),
        "iterations_per_model": ITERATIONS,
        "metrics": ["quantization_error", "topographic_error", "pairwise-distance mapping stability across seeds"],
        "topographic_neighbor_definition": "Chebyshev grid distance <= 1 (horizontal, vertical or diagonal immediate cell)",
        "mapping_stability_definition": "Spearman correlation of all pairwise municipal BMU distances, normalized by grid diagonal; invariant to rotations/reflections",
        "grid_selection": "equal-weight normalized median QE, median TE and median mapping instability",
        "selected_grid": [gr, gc],
        "selected_grid_selection_score": float(selected_grid.selection_score),
        "selected_grid_qe_median": float(selected_grid.qe_median),
        "selected_grid_te_median": float(selected_grid.te_median),
        "selected_grid_mapping_stability_median_spearman": float(selected_grid.mapping_stability_median_spearman),
        "selected_seed": seed,
        "selected_seed_quantization_error": float(chosen.quantization_error),
        "selected_seed_topographic_error": float(chosen.topographic_error),
        "selected_seed_mapping_stability": float(chosen.seed_mapping_stability),
        "selection_not_visual": True,
        "analytical_role": "descriptive socioeconomic/demographic profiling; no feedback into Stage-4 MCDM",
        "next_action": "Interpret selected SOM component planes / municipal profiles and only then cross-tab profiles with frozen PROMETHEE-II priority results.",
    }
    (OUT / "stage5_som_training_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
