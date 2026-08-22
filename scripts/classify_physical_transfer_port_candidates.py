from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

IN = Path("artifacts/antaq_physical_transfer_ports/pa_physical_transfer_port_candidates.csv")
OUT = Path("artifacts/antaq_physical_transfer_port_classification")


def pareto_fronts(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    values = df[cols].to_numpy(dtype=float)
    remaining = set(range(len(df)))
    front = np.full(len(df), np.nan)
    rank = 1
    while remaining:
        current = []
        rem = list(remaining)
        for i in rem:
            vi = values[i]
            dominated = False
            for j in rem:
                if i == j:
                    continue
                vj = values[j]
                if np.all(vj <= vi) and np.any(vj < vi):
                    dominated = True
                    break
            if not dominated:
                current.append(i)
        for i in current:
            front[i] = rank
            remaining.remove(i)
        rank += 1
    return pd.Series(front.astype(int), index=df.index)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(IN)
    for c in ["hydro_distance_m", "road_distance_m"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    valid = df[df["hydro_distance_m"].notna() & df["road_distance_m"].notna()].copy()
    if valid.empty:
        raise RuntimeError("No candidates with both hydro and road distances")

    valid["hydro_percentile"] = valid["hydro_distance_m"].rank(method="average", pct=True)
    valid["road_percentile"] = valid["road_distance_m"].rank(method="average", pct=True)
    valid["mean_empirical_percentile"] = valid[["hydro_percentile", "road_percentile"]].mean(axis=1)
    valid["worst_empirical_percentile"] = valid[["hydro_percentile", "road_percentile"]].max(axis=1)
    valid["pareto_front"] = pareto_fronts(valid, ["hydro_distance_m", "road_distance_m"])

    valid = valid.sort_values(
        ["pareto_front", "worst_empirical_percentile", "mean_empirical_percentile", "hydro_distance_m", "road_distance_m"]
    ).reset_index(drop=True)
    valid["evidence_rank"] = np.arange(1, len(valid) + 1)
    valid["classification_status"] = "candidate_ranked_not_promoted"

    front_counts = valid["pareto_front"].value_counts().sort_index().to_dict()
    top = valid.head(10)[
        ["evidence_rank", "port_index", "port_id", "port_name", "municipality", "hydro_distance_m", "road_distance_m", "pareto_front", "worst_empirical_percentile"]
    ].to_dict(orient="records")

    audit = {
        "candidates_with_both_distances": int(len(valid)),
        "pareto_front_counts": {str(k): int(v) for k, v in front_counts.items()},
        "pareto_front_1_count": int((valid["pareto_front"] == 1).sum()),
        "top_10_by_evidence_rank": top,
        "connector_promoted": False,
        "fixed_distance_threshold_used": False,
        "classification_basis": (
            "Two-objective empirical ranking using hydro-distance and road-distance percentiles plus non-dominated Pareto fronts. "
            "Lower distances are preferred; no externally chosen radius or percentile cutoff is used to promote connectors."
        ),
        "ready_for_candidate_validation": True,
    }

    valid.to_csv(OUT / "pa_physical_transfer_port_ranked_candidates.csv", index=False)
    (OUT / "pa_physical_transfer_port_classification_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
