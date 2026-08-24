from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "artifacts" / "cnefe_osm_street_name_alignment" / "cnefe_osm_street_name_alignment.csv.gz"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "cnefe_osm_alignment_regimes"


def _intersection(means: np.ndarray, variances: np.ndarray, weights: np.ndarray) -> float | None:
    order = np.argsort(means)
    m1, m2 = means[order]
    v1, v2 = variances[order]
    w1, w2 = weights[order]
    a = -1.0 / (2.0 * v1) + 1.0 / (2.0 * v2)
    b = m1 / v1 - m2 / v2
    c = np.log(w1 / np.sqrt(v1)) - np.log(w2 / np.sqrt(v2)) - m1 * m1 / (2.0 * v1) + m2 * m2 / (2.0 * v2)
    roots = np.roots([a, b, c]) if abs(a) > 1e-12 else np.roots([b, c])
    between = [float(r.real) for r in roots if abs(r.imag) < 1e-8 and m1 < r.real < m2]
    return between[0] if len(between) == 1 else None


def fit_two_regime(log_distance: np.ndarray, seed: int = 0) -> dict:
    one = GaussianMixture(n_components=1, random_state=seed, n_init=10).fit(log_distance)
    two = GaussianMixture(n_components=2, random_state=seed, n_init=10).fit(log_distance)
    means = two.means_.ravel()
    variances = two.covariances_.reshape(-1)
    weights = two.weights_.ravel()
    cut_log10 = _intersection(means, variances, weights)
    return {
        "bic_1_component": float(one.bic(log_distance)),
        "bic_2_components": float(two.bic(log_distance)),
        "bic_improvement_2_vs_1": float(one.bic(log_distance) - two.bic(log_distance)),
        "component_means_log10_m": [float(x) for x in means[np.argsort(means)]],
        "component_sd_log10_m": [float(np.sqrt(x)) for x in variances[np.argsort(means)]],
        "component_weights": [float(x) for x in weights[np.argsort(means)]],
        "posterior_equal_intersection_log10_m": cut_log10,
        "posterior_equal_intersection_m": float(10 ** cut_log10) if cut_log10 is not None else None,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--bootstrap", type=int, default=200)
    p.add_argument("--seed", type=int, default=20260824)
    args = p.parse_args()

    df = pd.read_csv(args.input, low_memory=False)
    mask = df["any_nominal_match_same_municipality"].fillna(False).astype(bool)
    distances = pd.to_numeric(df.loc[mask, "distance_to_any_same_name_osm_m"], errors="coerce").dropna().to_numpy(float)
    distances = distances[np.isfinite(distances) & (distances >= 0)]
    if len(distances) < 100:
        raise RuntimeError("Too few nominally aligned origins for regime audit")

    logd = np.log10(np.maximum(distances, 1e-3)).reshape(-1, 1)
    fitted = fit_two_regime(logd, seed=args.seed)

    rng = np.random.default_rng(args.seed)
    cuts: list[float] = []
    bic_gains: list[float] = []
    for b in range(args.bootstrap):
        sample = logd[rng.integers(0, len(logd), len(logd))]
        result = fit_two_regime(sample, seed=args.seed + b + 1)
        if result["posterior_equal_intersection_m"] is not None:
            cuts.append(float(result["posterior_equal_intersection_m"]))
        bic_gains.append(float(result["bic_improvement_2_vs_1"]))

    cut = fitted["posterior_equal_intersection_m"]
    local_count = int((distances <= cut).sum()) if cut is not None else 0
    audit = {
        "nominally_matched_origins_with_distance": int(len(distances)),
        **fitted,
        "origins_in_lower_distance_regime_at_fitted_intersection": local_count,
        "lower_distance_regime_fraction_at_fitted_intersection": float(local_count / len(distances)) if cut is not None else None,
        "bootstrap_replicates_requested": int(args.bootstrap),
        "bootstrap_valid_intersections": int(len(cuts)),
        "bootstrap_intersection_m": {
            "p05": float(np.quantile(cuts, 0.05)) if cuts else None,
            "median": float(np.quantile(cuts, 0.50)) if cuts else None,
            "p95": float(np.quantile(cuts, 0.95)) if cuts else None,
        },
        "bootstrap_bic_improvement_2_vs_1": {
            "p05": float(np.quantile(bic_gains, 0.05)),
            "median": float(np.quantile(bic_gains, 0.50)),
            "p95": float(np.quantile(bic_gains, 0.95)),
        },
        "distance_cutoff_adopted": False,
        "network_connector_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "A two-component Gaussian mixture on log10 distance is used only to test whether the empirical CNEFE-to-same-name-OSM distance distribution contains distinct regimes. "
            "The posterior-equality intersection and bootstrap stability are diagnostic evidence only. No threshold is adopted, no connector is promoted, and no travel time is assigned by this audit."
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "cnefe_osm_alignment_regimes_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
