from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture


def fit_intersection(model: GaussianMixture) -> float | None:
    means = model.means_.ravel()
    vars_ = model.covariances_.reshape(-1)
    weights = model.weights_.ravel()
    order = np.argsort(means)
    m1, m2 = means[order]
    v1, v2 = vars_[order]
    w1, w2 = weights[order]
    # Solve equality of the two weighted Gaussian densities in log10(distance) space.
    a = 1.0 / (2.0 * v2) - 1.0 / (2.0 * v1)
    b = m1 / v1 - m2 / v2
    c = (m2 * m2) / (2.0 * v2) - (m1 * m1) / (2.0 * v1) + np.log((w1 / np.sqrt(v1)) / (w2 / np.sqrt(v2)))
    roots = np.roots([a, b, c]) if abs(a) > 1e-12 else np.roots([b, c])
    real = [float(r.real) for r in roots if abs(r.imag) < 1e-8 and m1 < r.real < m2]
    return real[0] if real else None


def q(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0}
    return {
        "n": int(len(x)),
        "min_m": float(np.min(x)),
        "median_m": float(np.median(x)),
        "p90_m": float(np.quantile(x, .90)),
        "p95_m": float(np.quantile(x, .95)),
        "p99_m": float(np.quantile(x, .99)),
        "max_m": float(np.max(x)),
    }


def main() -> None:
    ev = pd.read_csv("artifacts/origin_network_access_evidence/origin_network_access_evidence.csv.gz", low_memory=False)
    inter = pd.read_csv("artifacts/origin_cartographic_topology_intersection/origin_cartographic_topology_intersection.csv.gz", low_memory=False)
    keep = ["origin_id", "origin_cartographic_topology_class"]
    x = ev.merge(inter[keep], on="origin_id", how="left", validate="one_to_one")
    direct = x[x["origin_access_evidence_class"].eq("nearest_local_osm_node_in_primary_motor_graph")].copy()
    if len(direct) != 14306:
        raise ValueError(f"Expected 14306 direct-primary origins, found {len(direct)}")

    d = pd.to_numeric(direct["distance_to_road_m"], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(d) & (d > 0)
    z = np.log10(d[ok]).reshape(-1, 1)
    if len(z) < 100:
        raise ValueError("Too few valid direct-primary road distances")

    g1 = GaussianMixture(n_components=1, random_state=20260825, n_init=10).fit(z)
    g2 = GaussianMixture(n_components=2, random_state=20260825, n_init=20).fit(z)
    bic1 = float(g1.bic(z)); bic2 = float(g2.bic(z))
    inter_log = fit_intersection(g2)
    inter_m = float(10 ** inter_log) if inter_log is not None else None

    means = g2.means_.ravel(); order = np.argsort(means)
    lower_component = int(order[0])
    posterior = g2.predict_proba(z)[:, lower_component]
    labels = np.full(len(direct), np.nan)
    labels[np.flatnonzero(ok)] = posterior
    direct["lower_distance_regime_posterior"] = labels
    direct["empirical_lower_distance_regime"] = direct["lower_distance_regime_posterior"] >= 0.5

    control = direct["origin_cartographic_topology_class"].eq("local_alignment_and_primary_motor_topology")
    unvalidated = ~control
    lower = direct["empirical_lower_distance_regime"].fillna(False)

    rng = np.random.default_rng(20260825)
    boot_intersections = []
    boot_bic_gain = []
    valid_z = z.ravel()
    for _ in range(200):
        sample = rng.choice(valid_z, size=len(valid_z), replace=True).reshape(-1, 1)
        b1 = GaussianMixture(n_components=1, random_state=int(rng.integers(1, 2**31-1)), n_init=3).fit(sample)
        b2 = GaussianMixture(n_components=2, random_state=int(rng.integers(1, 2**31-1)), n_init=5).fit(sample)
        bi = fit_intersection(b2)
        if bi is not None:
            boot_intersections.append(10 ** bi)
            boot_bic_gain.append(b1.bic(sample) - b2.bic(sample))

    outdir = Path("artifacts/direct_primary_origin_distance_regimes")
    outdir.mkdir(parents=True, exist_ok=True)
    direct[["origin_id", "distance_to_road_m", "lower_distance_regime_posterior", "empirical_lower_distance_regime", "origin_cartographic_topology_class"]].to_csv(
        outdir / "direct_primary_origin_distance_regimes.csv.gz", index=False, compression="gzip"
    )

    audit = {
        "direct_primary_origin_count": int(len(direct)),
        "valid_distance_count": int(ok.sum()),
        "distance_metric": "distance_to_nearest_OSM_road_geometry_m",
        "bic_one_component": bic1,
        "bic_two_component": bic2,
        "bic_improvement_two_over_one": float(bic1 - bic2),
        "component_means_log10_m": [float(means[i]) for i in order],
        "component_weights": [float(g2.weights_[i]) for i in order],
        "posterior_intersection_m": inter_m,
        "lower_regime_count": int(lower.sum()),
        "lower_regime_fraction": float(lower.mean()),
        "positive_control_count": int(control.sum()),
        "positive_controls_in_lower_regime": int((control & lower).sum()),
        "positive_control_lower_regime_fraction": float((control & lower).sum() / control.sum()),
        "unvalidated_direct_count": int(unvalidated.sum()),
        "unvalidated_direct_in_lower_regime": int((unvalidated & lower).sum()),
        "unvalidated_direct_lower_regime_fraction": float((unvalidated & lower).sum() / unvalidated.sum()),
        "positive_control_distance": q(pd.to_numeric(direct.loc[control, "distance_to_road_m"], errors="coerce").to_numpy()),
        "unvalidated_lower_regime_distance": q(pd.to_numeric(direct.loc[unvalidated & lower, "distance_to_road_m"], errors="coerce").to_numpy()),
        "bootstrap_valid_intersections": int(len(boot_intersections)),
        "bootstrap_intersection_m": {
            "p05": float(np.quantile(boot_intersections, .05)) if boot_intersections else None,
            "median": float(np.median(boot_intersections)) if boot_intersections else None,
            "p95": float(np.quantile(boot_intersections, .95)) if boot_intersections else None,
        },
        "bootstrap_bic_gain": {
            "p05": float(np.quantile(boot_bic_gain, .05)) if boot_bic_gain else None,
            "median": float(np.median(boot_bic_gain)) if boot_bic_gain else None,
            "p95": float(np.quantile(boot_bic_gain, .95)) if boot_bic_gain else None,
        },
        "posterior_boundary_hardcoded": False,
        "distance_regime_is_routing_cutoff": False,
        "connector_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "A two-component Gaussian mixture is fitted to log10 distance from direct-primary origin points to the nearest OSM road geometry. "
            "The posterior intersection is estimated from the data and bootstrapped, then checked against independently validated nominal/topological positive controls. "
            "This is a cartographic-regime diagnostic only: the intersection is not a statewide routing cutoff, and no connector or travel time is materialized by this audit."
        ),
    }
    (outdir / "direct_primary_origin_distance_regimes_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
