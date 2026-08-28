from __future__ import annotations

"""Interpret the selected Stage-5 SOM and only then cross-tab with MCDM.

The SOM profiles are descriptive socioeconomic/demographic typologies. Cluster
selection uses silhouette on the selected SOM codebook (k=2..6); no cluster is
labelled as violence risk. The frozen PROMETHEE-II result is joined only after
profile construction and characterization.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("results/stage5/tables")
FIG = Path("results/stage5/figures")
MAPPING = OUT / "stage5_som_selected_mapping.csv"
CODEBOOK = OUT / "stage5_som_selected_codebook.csv"
TRAIN_AUDIT = OUT / "stage5_som_training_audit.json"
BASE = Path("results/stage3/tables/municipal_analytical_matrix.csv")
AGE = OUT / "stage5_complete_female_age_candidate.csv"
RACE = OUT / "stage5_female_race_color_candidates.csv"
LITERACY = OUT / "stage5_female_literacy_candidate.csv"
INCOME = OUT / "stage5_income_candidate.csv"
PROMETHEE = Path("results/stage4/tables/promethee_ii_full_ranking.csv")

INTERPRETABLE = [
    "criterion__rural_female_share",
    "socio__female_literacy_rate_15plus",
    "socio__household_per_capita_income_mean_brl",
    "socio__female_age_share_15_29",
    "socio__female_age_share_30_59",
    "socio__female_age_share_60_plus",
    "socio__female_race_share_branca",
    "socio__female_race_share_preta",
    "socio__female_race_share_parda",
    "socio__female_race_share_amarela",
    "socio__female_race_share_indigena",
]


def kmeans(x: np.ndarray, k: int, seed: int, n_init: int = 100, max_iter: int = 300) -> tuple[np.ndarray, np.ndarray, float]:
    master = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        rng = np.random.default_rng(int(master.integers(0, 2**32 - 1)))
        centers = x[rng.choice(len(x), size=k, replace=False)].copy()
        labels = np.zeros(len(x), dtype=int)
        for __ in range(max_iter):
            d2 = np.square(x[:, None, :] - centers[None, :, :]).sum(axis=2)
            new_labels = d2.argmin(axis=1)
            new_centers = centers.copy()
            for j in range(k):
                members = x[new_labels == j]
                if len(members):
                    new_centers[j] = members.mean(axis=0)
                else:
                    new_centers[j] = x[rng.integers(0, len(x))]
            if np.array_equal(new_labels, labels) and np.allclose(new_centers, centers):
                labels, centers = new_labels, new_centers
                break
            labels, centers = new_labels, new_centers
        inertia = float(np.square(x - centers[labels]).sum())
        if best is None or inertia < best[2]:
            best = (labels.copy(), centers.copy(), inertia)
    assert best is not None
    return best


def silhouette(x: np.ndarray, labels: np.ndarray) -> float:
    d = np.linalg.norm(x[:, None, :] - x[None, :, :], axis=2)
    unique = np.unique(labels)
    vals = []
    for i in range(len(x)):
        own = labels[i]
        same = np.where(labels == own)[0]
        same = same[same != i]
        a = float(d[i, same].mean()) if len(same) else 0.0
        b = min(float(d[i, labels == other].mean()) for other in unique if other != own)
        vals.append(0.0 if max(a, b) == 0 else (b - a) / max(a, b))
    return float(np.mean(vals))


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"municipality_code": str}, low_memory=False)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    train = json.load(open(TRAIN_AUDIT, encoding="utf-8"))
    mapping = read(MAPPING)
    codebook = pd.read_csv(CODEBOOK)
    features = train["features"]
    gr, gc = train["selected_grid"]
    if len(mapping) != 144 or len(codebook) != gr * gc:
        raise RuntimeError("Selected SOM mapping/codebook integrity failure")

    # ---- 1. Build profiles without looking at MCDM ----
    xnodes = codebook[features].to_numpy(float)
    selection_rows = []
    candidates = {}
    occupancy = mapping.groupby(["som_bmu_row", "som_bmu_col"]).size().rename("municipality_count").reset_index()
    occupied_set = set(zip(occupancy.som_bmu_row.astype(int), occupancy.som_bmu_col.astype(int)))

    for k in range(2, 7):
        labels, centers, inertia = kmeans(xnodes, k, seed=20260828 + k)
        sil_nodes = silhouette(xnodes, labels)
        node_lab = {(int(r.som_row), int(r.som_col)): int(labels[i]) for i, r in codebook.iterrows()}
        mun_labels = np.array([node_lab[(int(r.som_bmu_row), int(r.som_bmu_col))] for r in mapping.itertuples()])
        counts = pd.Series(mun_labels).value_counts()
        min_mun = int(counts.min())
        selection_rows.append({"k": k, "silhouette_nodes": sil_nodes, "inertia": inertia, "min_municipalities_per_profile": min_mun})
        candidates[k] = (labels, centers, node_lab, mun_labels)

    selection = pd.DataFrame(selection_rows)
    eligible = selection[selection.min_municipalities_per_profile >= 8].copy()
    if eligible.empty:
        eligible = selection.copy()
    chosen_k = int(eligible.sort_values(["silhouette_nodes", "min_municipalities_per_profile"], ascending=[False, False]).iloc[0].k)
    node_labels, centers, node_lab, mun_labels = candidates[chosen_k]

    # Re-number profiles deterministically by mean first codebook coordinate to
    # keep IDs stable, without attaching substantive/normative ordering.
    center_order = np.argsort(centers[:, 0])
    remap = {old: new + 1 for new, old in enumerate(center_order)}
    node_profile = np.array([remap[int(v)] for v in node_labels], dtype=int)
    municipal_profile = np.array([remap[int(v)] for v in mun_labels], dtype=int)

    node_assign = codebook[["som_row", "som_col"]].copy()
    node_assign["som_profile"] = node_profile
    node_assign = node_assign.merge(occupancy, left_on=["som_row", "som_col"], right_on=["som_bmu_row", "som_bmu_col"], how="left")
    node_assign["municipality_count"] = node_assign["municipality_count"].fillna(0).astype(int)
    node_assign = node_assign.drop(columns=["som_bmu_row", "som_bmu_col"])
    node_assign.to_csv(OUT / "stage5_som_node_profiles.csv", index=False)

    profiles = mapping.copy()
    profiles["som_profile"] = municipal_profile

    # Join original interpretable variables for description, still no MCDM.
    base = read(BASE)[["municipality_code", "criterion__rural_female_share"]]
    age = read(AGE)[["municipality_code", "socio__female_age_share_15_29", "socio__female_age_share_30_59", "socio__female_age_share_60_plus"]]
    race = read(RACE)[["municipality_code", "socio__female_race_share_branca", "socio__female_race_share_preta", "socio__female_race_share_parda", "socio__female_race_share_amarela", "socio__female_race_share_indigena"]]
    literacy = read(LITERACY)[["municipality_code", "socio__female_literacy_rate_15plus"]]
    income = read(INCOME)[["municipality_code", "socio__household_per_capita_income_mean_brl"]]
    descriptive = profiles
    for block in [base, age, race, literacy, income]:
        descriptive = descriptive.merge(block, on="municipality_code", how="left", validate="one_to_one")
    if descriptive[INTERPRETABLE].isna().any().any():
        raise RuntimeError("Interpretable profile matrix contains missing values")

    overall = descriptive[INTERPRETABLE].mean()
    sd = descriptive[INTERPRETABLE].std(ddof=0).replace(0, np.nan)
    means = descriptive.groupby("som_profile")[INTERPRETABLE].mean()
    zmeans = (means - overall) / sd
    sizes = descriptive.groupby("som_profile").size().rename("municipality_count")
    profile_summary = means.copy()
    profile_summary.insert(0, "municipality_count", sizes)
    profile_summary.to_csv(OUT / "stage5_som_profile_characteristics.csv")
    zmeans.to_csv(OUT / "stage5_som_profile_standardized_characteristics.csv")
    profiles.to_csv(OUT / "stage5_som_municipal_profiles.csv", index=False)
    selection.to_csv(OUT / "stage5_som_profile_k_selection.csv", index=False)

    # ---- 2. Only now join frozen MCDM for exploratory cross-tab ----
    prom = read(PROMETHEE)[["municipality_code", "promethee_rank", "promethee_net_flow", "top_10", "top_quartile", "robustness_top_quartile_probability"]]
    cross = profiles[["municipality_code", "municipality_name", "som_profile"]].merge(prom, on="municipality_code", how="left", validate="one_to_one")
    if cross["promethee_rank"].isna().any():
        raise RuntimeError("PROMETHEE cross-tab join failed")
    cross.to_csv(OUT / "stage5_som_profiles_with_promethee.csv", index=False)
    cross_summary = cross.groupby("som_profile", as_index=False).agg(
        municipality_count=("municipality_code", "size"),
        promethee_rank_median=("promethee_rank", "median"),
        promethee_rank_mean=("promethee_rank", "mean"),
        promethee_net_flow_mean=("promethee_net_flow", "mean"),
        top10_count=("top_10", "sum"),
        top_quartile_count=("top_quartile", "sum"),
        top_quartile_share=("top_quartile", "mean"),
        mean_robust_top_quartile_probability=("robustness_top_quartile_probability", "mean"),
    )
    cross_summary.to_csv(OUT / "stage5_som_profile_promethee_summary.csv", index=False)

    # Component-plane figure for the selected SOM. These planes are the frozen
    # standardized training dimensions; interpret raw profile means alongside.
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 5, figsize=(18, 7), constrained_layout=True)
    for ax, feature in zip(axes.flat, features):
        grid = np.full((gr, gc), np.nan)
        for r in codebook.itertuples():
            grid[int(r.som_row), int(r.som_col)] = getattr(r, feature)
        im = ax.imshow(grid, aspect="equal")
        ax.set_title(feature.replace("profile__", "").replace("socio__", "").replace("criterion__", ""), fontsize=9)
        ax.set_xticks(range(gc)); ax.set_yticks(range(gr))
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle("Stage 5 SOM component planes — standardized profile dimensions")
    fig.savefig(FIG / "stage5_som_component_planes.png", dpi=200)
    plt.close(fig)

    # Profile grid shows selected macroprofiles and occupancy.
    profile_grid = np.zeros((gr, gc), dtype=int)
    occ_grid = np.zeros((gr, gc), dtype=int)
    for r in node_assign.itertuples():
        profile_grid[int(r.som_row), int(r.som_col)] = int(r.som_profile)
        occ_grid[int(r.som_row), int(r.som_col)] = int(r.municipality_count)
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(profile_grid, aspect="equal")
    for rr in range(gr):
        for cc in range(gc):
            ax.text(cc, rr, f"P{profile_grid[rr,cc]}\nn={occ_grid[rr,cc]}", ha="center", va="center", fontsize=8)
    ax.set_title("Selected SOM macroprofiles and municipality occupancy")
    ax.set_xticks(range(gc)); ax.set_yticks(range(gr))
    fig.colorbar(im, ax=ax, label="Profile ID")
    fig.tight_layout()
    fig.savefig(FIG / "stage5_som_profile_map.png", dpi=200)
    plt.close(fig)

    audit = {
        "stage": "Stage 5 SOM profile interpretation and post-hoc MCDM cross-tab",
        "selected_grid": [gr, gc],
        "profile_k_candidates": selection_rows,
        "profile_k_eligibility_rule": "prefer solutions with at least 8 municipalities per profile; among eligible choose highest node-codebook silhouette",
        "selected_profile_count": chosen_k,
        "selected_silhouette": float(selection.loc[selection.k == chosen_k, "silhouette_nodes"].iloc[0]),
        "profile_sizes": {str(int(k)): int(v) for k, v in sizes.items()},
        "profile_labels": "P1..Pk are neutral mathematical identifiers, not ordinal risk classes",
        "interpretation_variables": INTERPRETABLE,
        "mcdm_cross_tab_performed_after_profile_construction": True,
        "mcdm_feedback_to_som_or_ranking": False,
        "promethee_cross_tab_fields": ["promethee_rank", "promethee_net_flow", "top_10", "top_quartile", "robustness_top_quartile_probability"],
        "outputs": {
            "component_planes": "results/stage5/figures/stage5_som_component_planes.png",
            "profile_map": "results/stage5/figures/stage5_som_profile_map.png",
            "profile_characteristics": "results/stage5/tables/stage5_som_profile_characteristics.csv",
            "promethee_summary": "results/stage5/tables/stage5_som_profile_promethee_summary.csv",
        },
    }
    (OUT / "stage5_som_interpretation_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
