from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _parse_speed(value: object) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if "," in s or ";" in s or "|" in s:
        return None
    s = s.replace("km/h", "").replace("kmh", "").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def bootstrap_median_ci(values: np.ndarray, rng: np.random.Generator, reps: int = 1000) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return (np.nan, np.nan)
    if n == 1:
        v = float(values[0])
        return (v, v)
    meds = np.empty(reps, dtype=float)
    for i in range(reps):
        sample = rng.choice(values, size=n, replace=True)
        meds[i] = np.median(sample)
    return (float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975)))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--edges", type=Path, default=Path("artifacts/transport_topology/road_edges.csv.gz"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/road_speed_candidate_stability"))
    p.add_argument("--bootstrap-reps", type=int, default=1000)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    edges = pd.read_csv(args.edges, low_memory=False)
    edges["speed_kmh"] = edges["maxspeed_raw"].map(_parse_speed)
    rng = np.random.default_rng(20260821)

    rows = []
    for highway, g in edges.groupby("highway", dropna=False):
        obs = pd.to_numeric(g["speed_kmh"], errors="coerce").dropna().to_numpy(dtype=float)
        total = len(g)
        obs_n = len(obs)
        coverage = obs_n / total if total else 0.0
        length_total_km = pd.to_numeric(g["length_m"], errors="coerce").fillna(0).sum() / 1000.0
        length_obs_km = pd.to_numeric(g.loc[g["speed_kmh"].notna(), "length_m"], errors="coerce").fillna(0).sum() / 1000.0
        length_cov = length_obs_km / length_total_km if length_total_km else 0.0
        if obs_n:
            median = float(np.median(obs))
            ci_low, ci_high = bootstrap_median_ci(obs, rng, args.bootstrap_reps)
            iqr = float(np.quantile(obs, 0.75) - np.quantile(obs, 0.25))
            ci_width = ci_high - ci_low
            ci_rel_width = ci_width / median if median else np.nan
        else:
            median = ci_low = ci_high = iqr = ci_width = ci_rel_width = np.nan
        rows.append({
            "highway": highway,
            "edges_total": int(total),
            "observed_n": int(obs_n),
            "edge_observed_fraction": float(coverage),
            "length_total_km": float(length_total_km),
            "length_observed_fraction": float(length_cov),
            "median_kmh": median,
            "bootstrap_median_ci95_low_kmh": ci_low,
            "bootstrap_median_ci95_high_kmh": ci_high,
            "bootstrap_ci_width_kmh": ci_width,
            "bootstrap_ci_relative_width": ci_rel_width,
            "observed_iqr_kmh": iqr,
            "stability_flag": (
                "no_observation" if obs_n == 0 else
                "very_sparse" if obs_n < 30 else
                "sparse" if obs_n < 100 else
                "empirically_stable_candidate" if (np.isfinite(ci_rel_width) and ci_rel_width <= 0.25) else
                "needs_review"
            ),
        })

    out = pd.DataFrame(rows).sort_values(["observed_n", "edges_total"], ascending=False)
    out.to_csv(args.output_dir / "road_speed_candidate_stability_by_highway.csv", index=False)

    summary = {
        "highway_classes": int(len(out)),
        "classes_with_observations": int((out["observed_n"] > 0).sum()),
        "classes_empirically_stable_candidate": int((out["stability_flag"] == "empirically_stable_candidate").sum()),
        "classes_sparse_or_very_sparse": int(out["stability_flag"].isin(["sparse", "very_sparse"]).sum()),
        "classes_without_observations": int((out["stability_flag"] == "no_observation").sum()),
        "policy": (
            "This audit assesses stability/representativeness of observed class-wise OSM maxspeed medians. "
            "Bootstrap intervals and coverage are diagnostic only. No speed is applied to missing edges here, "
            "and motor-vehicle eligibility/exclusion of non-drivable highway tags remains a separate routing-model decision."
        ),
        "ready_for_road_speed_policy": True,
        "travel_time_assigned": False,
    }
    (args.output_dir / "road_speed_candidate_stability_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
