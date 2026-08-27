from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CRITERIA = [
    "criterion__reachable_service_fraction",
    "criterion__services_within_120_fraction",
    "criterion__nearest_reachable_service_time_min",
    "criterion__median_reachable_service_time_min",
    "criterion__health_specialized_absence",
    "criterion__creas_absence",
    "criterion__specialized_security_absence",
    "criterion__specialized_justice_absence",
    "criterion__rural_female_share",
]

ACCESS_BENEFIT = {
    "criterion__reachable_service_fraction",
    "criterion__services_within_120_fraction",
}
ACCESS_TIME = {
    "criterion__nearest_reachable_service_time_min",
    "criterion__median_reachable_service_time_min",
}
BINARY_DEFICIT = {
    "criterion__health_specialized_absence",
    "criterion__creas_absence",
    "criterion__specialized_security_absence",
    "criterion__specialized_justice_absence",
}
TERRITORIAL = {"criterion__rural_female_share"}

STATUS_COVERAGE_LIMIT = "no_primary_routing_ready_origin"
STATUS_TRUE_UNREACHABLE = "routing_ready_no_reachable_service"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--draws", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260827)
    return parser.parse_args()


def minmax(values: pd.Series) -> pd.Series:
    lo = values.min(skipna=True)
    hi = values.max(skipna=True)
    if pd.isna(lo) or pd.isna(hi):
        return pd.Series(np.nan, index=values.index, dtype=float)
    if np.isclose(hi, lo):
        return pd.Series(0.0, index=values.index, dtype=float)
    return (values - lo) / (hi - lo)


def build_need_scores(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    scores = pd.DataFrame(index=frame.index)
    scaling: dict[str, dict] = {}

    for col in ACCESS_BENEFIT:
        raw = pd.to_numeric(frame[col], errors="coerce")
        scores[col] = 1.0 - raw
        scaling[col] = {"transform": "1 - observed fraction", "direction": "higher = greater priority need"}

    for col in ACCESS_TIME:
        raw = pd.to_numeric(frame[col], errors="coerce")
        observed = raw[raw.notna()]
        scaled = minmax(raw)
        true_unreachable = frame["accessibility_coverage_status"].eq(STATUS_TRUE_UNREACHABLE)
        coverage_limit = frame["accessibility_coverage_status"].eq(STATUS_COVERAGE_LIMIT)
        # A tested municipality with no finite route is ordinally worse than every finite time,
        # but no synthetic number of minutes is created. Coverage limitations remain missing.
        scaled.loc[true_unreachable] = 1.0
        scaled.loc[coverage_limit] = np.nan
        scores[col] = scaled
        scaling[col] = {
            "transform": "min-max among finite observed times; tested-unreachable assigned worst normalized state=1; coverage-limit remains NA",
            "observed_min": float(observed.min()),
            "observed_max": float(observed.max()),
            "direction": "higher = greater priority need",
            "synthetic_minutes_created": False,
        }

    for col in BINARY_DEFICIT:
        scores[col] = pd.to_numeric(frame[col], errors="coerce")
        scaling[col] = {"transform": "identity binary deficit", "direction": "1 = greater priority need"}

    for col in TERRITORIAL:
        scores[col] = pd.to_numeric(frame[col], errors="coerce")
        scaling[col] = {"transform": "identity proportion", "direction": "higher = greater territorial exposure"}

    scores = scores[CRITERIA].clip(lower=0.0, upper=1.0)
    return scores, scaling


def preference_tensor(scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # P[j,a,b] = degree to which a is preferred to b on criterion j.
    # Linear V-shape on the locked [0,1] need scale, p=1, q=0.
    n, k = scores.shape
    pref = np.zeros((k, n, n), dtype=np.float32)
    avail = np.zeros((k, n, n), dtype=np.float32)
    for j in range(k):
        x = scores[:, j]
        valid = np.isfinite(x)
        joint = valid[:, None] & valid[None, :]
        diff = x[:, None] - x[None, :]
        pref[j] = np.where(joint, np.maximum(diff, 0.0), 0.0).astype(np.float32)
        avail[j] = joint.astype(np.float32)
    return pref, avail


def promethee_flows(pref: np.ndarray, avail: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    numerator = np.tensordot(weights, pref, axes=(0, 0))
    denominator = np.tensordot(weights, avail, axes=(0, 0))
    pi = np.divide(numerator, denominator, out=np.zeros_like(numerator, dtype=float), where=denominator > 0)
    np.fill_diagonal(pi, 0.0)
    n = pi.shape[0]
    pos = pi.sum(axis=1) / (n - 1)
    neg = pi.sum(axis=0) / (n - 1)
    net = pos - neg
    comparable_weight = denominator.copy()
    np.fill_diagonal(comparable_weight, np.nan)
    mean_comparable = np.nanmean(comparable_weight, axis=1)
    return pos, neg, net, mean_comparable


def ranks_desc(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(method="min", ascending=False).astype(int).to_numpy()


def topsis_contrast(scores: np.ndarray, weights: np.ndarray, coverage_limit_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # TOPSIS contrast is intentionally restricted to alternatives with complete transformed scores.
    complete = np.isfinite(scores).all(axis=1) & ~coverage_limit_mask
    out_score = np.full(scores.shape[0], np.nan, dtype=float)
    out_rank = np.full(scores.shape[0], np.nan, dtype=float)
    x = scores[complete]
    w = weights / weights.sum()
    weighted = x * w
    ideal = w  # all need scores = 1
    anti = np.zeros_like(w)
    d_ideal = np.linalg.norm(weighted - ideal, axis=1)
    d_anti = np.linalg.norm(weighted - anti, axis=1)
    closeness = np.divide(d_anti, d_ideal + d_anti, out=np.zeros_like(d_anti), where=(d_ideal + d_anti) > 0)
    out_score[complete] = closeness
    out_rank[complete] = ranks_desc(closeness)
    return out_score, out_rank


def monte_carlo(pref: np.ndarray, avail: np.ndarray, reference_net: np.ndarray, draws: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = reference_net.size
    ref_rank = ranks_desc(reference_net)
    rank_sum = np.zeros(n, dtype=float)
    rank_sq_sum = np.zeros(n, dtype=float)
    rank_min = np.full(n, np.inf)
    rank_max = np.zeros(n, dtype=float)
    top10 = np.zeros(n, dtype=int)
    top_quartile = np.zeros(n, dtype=int)
    top_quartile_n = int(np.ceil(n / 4))
    spearman = np.empty(draws, dtype=float)

    flat_pref = pref.reshape(pref.shape[0], -1).astype(np.float64)
    flat_avail = avail.reshape(avail.shape[0], -1).astype(np.float64)
    batch = 200
    done = 0
    while done < draws:
        b = min(batch, draws - done)
        weights = rng.dirichlet(np.ones(pref.shape[0]), size=b)
        numer = weights @ flat_pref
        denom = weights @ flat_avail
        pair = np.divide(numer, denom, out=np.zeros_like(numer), where=denom > 0).reshape(b, n, n)
        idx = np.arange(n)
        pair[:, idx, idx] = 0.0
        net = pair.sum(axis=2) / (n - 1) - pair.sum(axis=1) / (n - 1)
        for i in range(b):
            r = ranks_desc(net[i])
            rank_sum += r
            rank_sq_sum += r * r
            rank_min = np.minimum(rank_min, r)
            rank_max = np.maximum(rank_max, r)
            top10 += (r <= 10)
            top_quartile += (r <= top_quartile_n)
            spearman[done + i] = pd.Series(r).corr(pd.Series(ref_rank), method="spearman")
        done += b

    mean = rank_sum / draws
    var = np.maximum(rank_sq_sum / draws - mean * mean, 0.0)
    return {
        "mean_rank": mean,
        "sd_rank": np.sqrt(var),
        "best_rank": rank_min.astype(int),
        "worst_rank": rank_max.astype(int),
        "top10_probability": top10 / draws,
        "top_quartile_probability": top_quartile / draws,
        "spearman": spearman,
    }


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(args.matrix, dtype={"municipality_code": "string"})
    if len(frame) != 144 or frame["municipality_code"].nunique() != 144:
        raise ValueError("Expected exactly 144 unique municipalities")
    missing_cols = [c for c in CRITERIA + ["accessibility_coverage_status"] if c not in frame.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    scores_df, scaling = build_need_scores(frame)
    scores = scores_df.to_numpy(dtype=float)
    pref, avail = preference_tensor(scores)
    weights = np.full(len(CRITERIA), 1.0 / len(CRITERIA), dtype=float)
    pos, neg, net, mean_comp = promethee_flows(pref, avail, weights)
    rank = ranks_desc(net)

    coverage_limit = frame["accessibility_coverage_status"].eq(STATUS_COVERAGE_LIMIT).to_numpy()
    topsis_score, topsis_rank = topsis_contrast(scores, weights, coverage_limit)

    robust = monte_carlo(pref, avail, net, args.draws, args.seed)

    out = frame[["municipality_code", "municipality_name", "accessibility_coverage_status"]].copy()
    out["promethee_positive_flow"] = pos
    out["promethee_negative_flow"] = neg
    out["promethee_net_flow"] = net
    out["promethee_rank"] = rank
    out["mean_pairwise_comparable_weight_fraction"] = mean_comp
    out["coverage_limited_rank_flag"] = coverage_limit
    out["topsis_contrast_score"] = topsis_score
    out["topsis_contrast_rank"] = topsis_rank
    for key in ["mean_rank", "sd_rank", "best_rank", "worst_rank", "top10_probability", "top_quartile_probability"]:
        out[f"robustness_{key}"] = robust[key]
    out = out.sort_values(["promethee_rank", "municipality_code"])
    out.to_csv(args.out / "promethee_reference_ranking.csv", index=False)

    transformed = frame[["municipality_code", "municipality_name", "accessibility_coverage_status"]].copy()
    transformed = pd.concat([transformed, scores_df], axis=1)
    transformed.to_csv(args.out / "mcdm_need_scaled_matrix.csv", index=False)

    pd.DataFrame({"criterion": CRITERIA, "reference_weight": weights}).to_csv(
        args.out / "reference_weights.csv", index=False
    )

    spearman = robust["spearman"]
    top = out.head(15)[["municipality_code", "municipality_name", "promethee_rank", "promethee_net_flow", "robustness_mean_rank", "robustness_top10_probability"]]
    summary = {
        "method_primary": "PROMETHEE II",
        "preference_function": "linear V-shape on [0,1] priority-need scale with q=0 and p=1",
        "reference_weights": "equal criterion weights (1/9 each)",
        "macro_weight_totals_reference": {"access": 4/9, "institutional": 4/9, "territorial_rurality": 1/9},
        "structural_missing_policy": {
            "Afua": "coverage-limited access criteria remain unavailable and are excluded pairwise with weight renormalization over mutually observed criteria; rank flagged coverage-limited",
            "Colares_and_Santa_Cruz_do_Arari": "observed reachability fractions remain zero; missing travel times are treated as ordinal tested-unreachable/worst normalized time state, without creating synthetic minutes",
        },
        "topsis_role": "contrast only; coverage-limited alternatives with incomplete transformed scores are excluded from TOPSIS ranking",
        "robustness": {
            "draws": args.draws,
            "seed": args.seed,
            "weight_distribution": "Dirichlet(1,...,1) over nine criteria",
            "spearman_vs_reference_median": float(np.median(spearman)),
            "spearman_vs_reference_p05": float(np.quantile(spearman, 0.05)),
            "spearman_vs_reference_p95": float(np.quantile(spearman, 0.95)),
        },
        "coverage_limited_alternatives": int(coverage_limit.sum()),
        "top15_reference": top.to_dict(orient="records"),
        "scaling": scaling,
        "ranking_is_final_policy_decision": False,
        "note": "This is the first locked Stage 4 reference/robustness execution. Further method/scale sensitivity may be added before manuscript-level finalization.",
    }
    (args.out / "stage4_mcdm_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Stage 4 MCDM execution summary",
        "",
        "Primary method: PROMETHEE II.",
        "",
        "Reference weights: equal across the nine locked candidate criteria (1/9 each).",
        "",
        f"Robustness: {args.draws:,} Dirichlet weight draws, seed {args.seed}.",
        "",
        f"Median Spearman against reference ranking: {np.median(spearman):.4f} (5th–95th percentile {np.quantile(spearman,0.05):.4f}–{np.quantile(spearman,0.95):.4f}).",
        "",
        "Afuá is retained with a coverage-limited rank flag and no fabricated access penalty. Colares and Santa Cruz do Arari retain observed zero reachability; tested-unreachable travel-time states are ordered worse than finite observed times without assigning synthetic minutes.",
        "",
        "## Reference top 15",
        "",
        top.to_markdown(index=False),
        "",
        "The reference ranking is an analytical baseline, not yet the manuscript-final policy result.",
    ]
    (args.out / "stage4_mcdm_summary.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()
