from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

RANDOM_STATE = 20260825
BOOTSTRAPS = 200


def fit3(values: np.ndarray, seed: int) -> GaussianMixture:
    x = np.sqrt(np.maximum(values, 0.0)).reshape(-1, 1)
    return GaussianMixture(n_components=3, random_state=seed, n_init=20, reg_covar=1e-6).fit(x)


def main() -> None:
    access = pd.read_csv("artifacts/service_local_access_primary_motor_audit/service_local_access_to_primary_motor.csv.gz", low_memory=False)
    nominal = pd.read_csv("artifacts/service_osm_street_name_alignment/service_osm_street_name_alignment.csv.gz", low_memory=False)

    direct = access[access["nearest_osm_node_in_primary_motor_graph"]].copy()
    if len(direct) != 227:
        raise RuntimeError(f"Expected 227 direct-primary services, found {len(direct)}")

    direct = direct.merge(
        nominal[["service_id", "any_address_street_match_same_municipality"]],
        on="service_id", how="left", validate="one_to_one"
    )
    direct["any_address_street_match_same_municipality"] = direct["any_address_street_match_same_municipality"].fillna(False).astype(bool)
    distances = pd.to_numeric(direct["distance_to_nearest_primary_motor_node_m"], errors="coerce").to_numpy(float)
    if not np.isfinite(distances).all():
        raise RuntimeError("Direct-primary service distances contain non-finite values")

    x = np.sqrt(np.maximum(distances, 0.0)).reshape(-1, 1)
    bics = {}
    models = {}
    for k in (1, 2, 3):
        gm = GaussianMixture(n_components=k, random_state=RANDOM_STATE, n_init=50, reg_covar=1e-6).fit(x)
        bics[str(k)] = float(gm.bic(x))
        models[k] = gm

    gm = models[3]
    means = gm.means_.ravel()
    local_component = int(np.argmin(means))
    posterior = gm.predict_proba(x)[:, local_component]
    local = gm.predict(x) == local_component

    direct["local_service_regime_posterior"] = posterior
    direct["empirical_local_service_regime"] = local

    controls = direct["any_address_street_match_same_municipality"].to_numpy(bool)
    control_count = int(controls.sum())
    controls_local = int((local & controls).sum())

    rng = np.random.default_rng(RANDOM_STATE)
    boot_local_counts = []
    valid = 0
    for i in range(BOOTSTRAPS):
        idx = rng.integers(0, len(distances), len(distances))
        sample = distances[idx]
        try:
            bgm = fit3(sample, RANDOM_STATE + i + 1)
            bmeans = bgm.means_.ravel()
            bloc = int(np.argmin(bmeans))
            full_pred = bgm.predict(np.sqrt(np.maximum(distances, 0.0)).reshape(-1, 1))
            boot_local_counts.append(int((full_pred == bloc).sum()))
            valid += 1
        except Exception:
            continue

    arr = np.asarray(boot_local_counts, dtype=float)
    audit = {
        "direct_primary_service_count": int(len(direct)),
        "nominal_positive_control_count": control_count,
        "nominal_positive_controls_in_local_regime": controls_local,
        "nominal_positive_control_local_fraction": float(controls_local / control_count) if control_count else None,
        "bic": bics,
        "three_component_bic_gain_over_one": float(bics["1"] - bics["3"]),
        "three_component_bic_gain_over_two": float(bics["2"] - bics["3"]),
        "sqrt_distance_component_means": [float(v) for v in means],
        "local_component": local_component,
        "empirical_local_service_count": int(local.sum()),
        "empirical_nonlocal_service_count": int((~local).sum()),
        "local_distance_m": {
            "min": float(np.min(distances[local])),
            "median": float(np.median(distances[local])),
            "p95": float(np.quantile(distances[local], 0.95)),
            "max": float(np.max(distances[local])),
        },
        "nonlocal_distance_m": {
            "min": float(np.min(distances[~local])),
            "median": float(np.median(distances[~local])),
            "max": float(np.max(distances[~local])),
        },
        "bootstrap_requested": BOOTSTRAPS,
        "bootstrap_valid": int(valid),
        "bootstrap_local_count": {
            "p05": float(np.quantile(arr, 0.05)) if len(arr) else None,
            "median": float(np.median(arr)) if len(arr) else None,
            "p95": float(np.quantile(arr, 0.95)) if len(arr) else None,
        },
        "distance_regime_is_physical_access_cutoff": False,
        "connector_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "Validated service coordinates whose nearest OSM node is already in the primary motor graph are evaluated with a data-derived mixture model on square-root distance. The empirically local component is validated against independent same-address-street/same-municipality controls. The model is not a universal physical-distance cutoff, and this audit alone creates no connector or travel time."
        ),
    }

    outdir = Path("artifacts/service_direct_primary_distance_regimes")
    outdir.mkdir(parents=True, exist_ok=True)
    direct.to_csv(outdir / "service_direct_primary_distance_regimes.csv.gz", index=False, compression="gzip")
    (outdir / "service_direct_primary_distance_regimes_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
