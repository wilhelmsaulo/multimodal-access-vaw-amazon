"""Publish publication-quality diagnostics from the frozen Stage-5 SOM.

All panels are computed directly from the selected 5x5 SOM codebook and the
frozen BMU/profile mapping. No retraining, reclassification, or MCDM feedback
occurs in this module.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "results" / "stage5" / "tables"
FIGS = ROOT / "results" / "stage5" / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

CODEBOOK_PATH = TABLES / "stage5_som_selected_codebook.csv"
NODE_PATH = TABLES / "stage5_som_node_profiles.csv"
MAPPING_PATH = TABLES / "stage5_som_municipal_profiles.csv"

FEATURE_LABELS = {
    "criterion__rural_female_share": "Rural female share",
    "socio__female_literacy_rate_15plus": "Female literacy 15+",
    "socio__household_per_capita_income_mean_brl": "Household per-capita income",
    "profile__female_age_ilr_1": "Age ILR1",
    "profile__female_age_ilr_2": "Age ILR2",
    "profile__female_age_ilr_3": "Age ILR3",
    "profile__female_race_ilr_1": "Race/color ILR1",
    "profile__female_race_ilr_2": "Race/color ILR2",
    "profile__female_race_ilr_3": "Race/color ILR3",
    "profile__female_race_ilr_4": "Race/color ILR4",
}

# Fixed categorical palette solely for consistent profile identity across figures.
PROFILE_COLORS = ["#2A9D8F", "#F28E2B", "#4E79A7", "#8F63B8"]


def _load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    cb = pd.read_csv(CODEBOOK_PATH)
    nodes = pd.read_csv(NODE_PATH)
    mapping = pd.read_csv(MAPPING_PATH)
    features = [c for c in cb.columns if c not in {"som_row", "som_col"}]
    assert cb.shape[0] == 25
    assert len(features) == 10
    assert len(mapping) == 144
    assert int(nodes["municipality_count"].sum()) == 144
    assert set(nodes["som_profile"].astype(int)) == {1, 2, 3, 4}
    return cb, nodes, mapping, features


def _cube(cb: pd.DataFrame, features: list[str]) -> np.ndarray:
    arr = np.full((5, 5, len(features)), np.nan, dtype=float)
    for row in cb.itertuples(index=False):
        r = int(row.som_row)
        c = int(row.som_col)
        for k, f in enumerate(features):
            arr[r, c, k] = float(getattr(row, f))
    assert np.isfinite(arr).all()
    return arr


def _matrix_from_nodes(nodes: pd.DataFrame, value: str) -> np.ndarray:
    out = np.full((5, 5), np.nan)
    for row in nodes.itertuples(index=False):
        out[int(row.som_row), int(row.som_col)] = float(getattr(row, value))
    assert np.isfinite(out).all()
    return out


def _umatrix(codebook: np.ndarray) -> np.ndarray:
    """Average Euclidean codebook distance to valid Moore (8-neighbor) cells."""
    rows, cols, _ = codebook.shape
    u = np.zeros((rows, cols), dtype=float)
    for r in range(rows):
        for c in range(cols):
            ds = []
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols:
                        ds.append(np.linalg.norm(codebook[r, c] - codebook[rr, cc]))
            u[r, c] = float(np.mean(ds))
    return u


def _grid(ax) -> None:
    ax.set_xticks(range(5), labels=range(1, 6))
    ax.set_yticks(range(5), labels=range(1, 6))
    ax.set_xlabel("SOM column")
    ax.set_ylabel("SOM row")
    ax.set_xticks(np.arange(-0.5, 5, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 5, 1), minor=True)
    ax.grid(which="minor", linewidth=1.0, color="white")
    ax.tick_params(which="minor", bottom=False, left=False)


def _profile_boundaries(ax, p: np.ndarray, linewidth: float = 2.2) -> None:
    for r in range(5):
        for c in range(5):
            if c < 4 and p[r, c] != p[r, c + 1]:
                ax.plot([c + 0.5, c + 0.5], [r - 0.5, r + 0.5], color="black", lw=linewidth)
            if r < 4 and p[r, c] != p[r + 1, c]:
                ax.plot([c - 0.5, c + 0.5], [r + 0.5, r + 0.5], color="black", lw=linewidth)


def _annotate_profile_centers(ax, p: np.ndarray, color: str = "black") -> None:
    for profile in range(1, 5):
        coords = np.argwhere(p == profile)
        rr, cc = coords.mean(axis=0)
        ax.text(cc, rr, f"P{profile}", ha="center", va="center", fontsize=14,
                fontweight="bold", color=color,
                bbox=dict(boxstyle="round,pad=0.18", facecolor="white", alpha=0.72, edgecolor="none"))


def _save(fig, stem: str) -> None:
    fig.savefig(FIGS / f"{stem}.png", dpi=320, bbox_inches="tight")
    fig.savefig(FIGS / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    cb, nodes, mapping, features = _load()
    cube = _cube(cb, features)
    u = _umatrix(cube)
    hits = _matrix_from_nodes(nodes, "municipality_count").astype(int)
    profiles = _matrix_from_nodes(nodes, "som_profile").astype(int)

    pd.DataFrame([
        {"som_row": r, "som_col": c, "u_matrix_mean_neighbor_distance": u[r, c],
         "municipality_count": int(hits[r, c]), "som_profile": int(profiles[r, c])}
        for r in range(5) for c in range(5)
    ]).to_csv(TABLES / "stage5_som_real_node_diagnostics.csv", index=False)

    # 1) U-matrix.
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(u, cmap="viridis", origin="upper")
    _grid(ax)
    _profile_boundaries(ax, profiles)
    _annotate_profile_centers(ax, profiles, color="black")
    ax.set_title("Real U-Matrix — selected Stage-5 SOM (5×5)\nMean codebook distance to adjacent neurons")
    cbx = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbx.set_label("Mean Euclidean neighbor distance")
    fig.tight_layout()
    _save(fig, "stage5_som_real_umatrix")

    # 2) Hits / BMU occupancy.
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(hits, cmap="Greys", origin="upper")
    _grid(ax)
    _profile_boundaries(ax, profiles)
    for r in range(5):
        for c in range(5):
            ax.text(c, r, str(hits[r, c]), ha="center", va="center", fontsize=12, fontweight="bold",
                    color="white" if hits[r, c] > hits.max() * 0.55 else "black")
    ax.set_title("BMU occupancy — municipalities per SOM neuron\nTotal municipalities = 144")
    cbx = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbx.set_label("Municipality count")
    fig.tight_layout()
    _save(fig, "stage5_som_real_hits")

    # 3) Macroprofiles on actual SOM lattice.
    cmap_profiles = ListedColormap(PROFILE_COLORS)
    norm_profiles = BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5], cmap_profiles.N)
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    ax.imshow(profiles, cmap=cmap_profiles, norm=norm_profiles, origin="upper")
    _grid(ax)
    _profile_boundaries(ax, profiles)
    _annotate_profile_centers(ax, profiles, color="black")
    for r in range(5):
        for c in range(5):
            ax.text(c, r + 0.28, f"n={hits[r,c]}", ha="center", va="center", fontsize=7, color="black")
    ax.set_title("Four neutral macroprofiles on the selected SOM lattice")
    ax.legend(handles=[Patch(facecolor=PROFILE_COLORS[i-1], label=f"P{i}") for i in range(1, 5)],
              loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False)
    fig.tight_layout()
    _save(fig, "stage5_som_real_macroprofiles")

    # 4) Ten real component planes. Codebook values are already in frozen standardized SOM space.
    vmin = float(np.nanmin(cube))
    vmax = float(np.nanmax(cube))
    limit = max(abs(vmin), abs(vmax))
    fig, axes = plt.subplots(2, 5, figsize=(15.5, 6.6), constrained_layout=True)
    last_im = None
    for k, (ax, f) in enumerate(zip(axes.flat, features), start=1):
        last_im = ax.imshow(cube[:, :, k-1], cmap="coolwarm", vmin=-limit, vmax=limit, origin="upper")
        ax.set_title(f"{k}. {FEATURE_LABELS[f]}", fontsize=9.2)
        ax.set_xticks(range(5), labels=range(1, 6), fontsize=7)
        ax.set_yticks(range(5), labels=range(1, 6), fontsize=7)
        ax.set_xticks(np.arange(-0.5, 5, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 5, 1), minor=True)
        ax.grid(which="minor", linewidth=0.7, color="white")
        ax.tick_params(which="minor", bottom=False, left=False)
        _profile_boundaries(ax, profiles, linewidth=1.0)
    cbar = fig.colorbar(last_im, ax=axes, orientation="horizontal", fraction=0.05, pad=0.08, shrink=0.72)
    cbar.set_label("Neuron codebook value in frozen standardized SOM space (low ← 0 → high)")
    fig.suptitle("Real SOM component planes — 10 frozen Stage-5 dimensions", fontsize=15, fontweight="bold")
    _save(fig, "stage5_som_real_component_planes")

    # 5) Consolidated publication-style diagnostic panel.
    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(3, 5, height_ratios=[1.05, 1.05, 1.45], hspace=0.42, wspace=0.4)

    ax_u = fig.add_subplot(gs[0:2, 0:2])
    im_u = ax_u.imshow(u, cmap="viridis", origin="upper")
    _grid(ax_u)
    _profile_boundaries(ax_u, profiles)
    _annotate_profile_centers(ax_u, profiles)
    ax_u.set_title("A  U-Matrix (real codebook distances)", loc="left", fontweight="bold")
    cbu = fig.colorbar(im_u, ax=ax_u, fraction=0.045, pad=0.04)
    cbu.set_label("Neighbor distance", fontsize=8)

    ax_h = fig.add_subplot(gs[0, 2:])
    im_h = ax_h.imshow(hits, cmap="Greys", origin="upper")
    ax_h.set_xticks(range(5), labels=range(1, 6))
    ax_h.set_yticks(range(5), labels=range(1, 6))
    ax_h.set_xticks(np.arange(-0.5, 5, 1), minor=True)
    ax_h.set_yticks(np.arange(-0.5, 5, 1), minor=True)
    ax_h.grid(which="minor", color="white", linewidth=0.8)
    ax_h.tick_params(which="minor", bottom=False, left=False)
    _profile_boundaries(ax_h, profiles, linewidth=1.5)
    for r in range(5):
        for c in range(5):
            ax_h.text(c, r, str(hits[r,c]), ha="center", va="center", fontsize=9,
                      fontweight="bold", color="white" if hits[r,c] > hits.max()*0.55 else "black")
    ax_h.set_title("B  BMU hits: municipalities per neuron (n=144)", loc="left", fontweight="bold")

    ax_p = fig.add_subplot(gs[1, 2:])
    ax_p.imshow(profiles, cmap=cmap_profiles, norm=norm_profiles, origin="upper")
    ax_p.set_xticks(range(5), labels=range(1, 6))
    ax_p.set_yticks(range(5), labels=range(1, 6))
    ax_p.set_xticks(np.arange(-0.5, 5, 1), minor=True)
    ax_p.set_yticks(np.arange(-0.5, 5, 1), minor=True)
    ax_p.grid(which="minor", color="white", linewidth=0.8)
    ax_p.tick_params(which="minor", bottom=False, left=False)
    _profile_boundaries(ax_p, profiles, linewidth=1.7)
    _annotate_profile_centers(ax_p, profiles)
    ax_p.set_title("C  Four macroprofiles on the actual SOM lattice", loc="left", fontweight="bold")
    ax_p.legend(handles=[Patch(facecolor=PROFILE_COLORS[i-1], label=f"P{i}") for i in range(1,5)],
                ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.28), frameon=False)

    sub = gs[2, :].subgridspec(2, 5, hspace=0.38, wspace=0.25)
    ims = []
    for k, f in enumerate(features):
        ax = fig.add_subplot(sub[k//5, k%5])
        im = ax.imshow(cube[:,:,k], cmap="coolwarm", vmin=-limit, vmax=limit, origin="upper")
        ims.append(im)
        ax.set_title(f"{k+1}. {FEATURE_LABELS[f]}", fontsize=8.5)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xticks(np.arange(-0.5, 5, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 5, 1), minor=True)
        ax.grid(which="minor", linewidth=0.55, color="white")
        ax.tick_params(which="minor", bottom=False, left=False)
        _profile_boundaries(ax, profiles, linewidth=0.75)
    fig.suptitle("Stage 5 — Real SOM diagnostics for Pará municipalities\nSelected 5×5 SOM, seed 5; all values derived from frozen model outputs",
                 fontsize=17, fontweight="bold", y=0.99)
    fig.text(0.5, 0.02, "D  Component planes: codebook values in the standardized training space. Black lines mark macroprofile boundaries.",
             ha="center", fontsize=10)
    _save(fig, "stage5_som_real_diagnostic_panel")

    audit = {
        "stage": "Stage 5 real SOM diagnostics",
        "source_codebook": str(CODEBOOK_PATH.relative_to(ROOT)),
        "source_node_profiles": str(NODE_PATH.relative_to(ROOT)),
        "source_municipal_mapping": str(MAPPING_PATH.relative_to(ROOT)),
        "selected_grid": [5, 5],
        "selected_seed": 5,
        "municipalities": int(len(mapping)),
        "neurons": int(cb.shape[0]),
        "features": features,
        "feature_count": len(features),
        "u_matrix_definition": "mean Euclidean distance from each codebook vector to all valid Moore-neighborhood (8-neighbor) codebook vectors",
        "component_plane_scale": "frozen standardized SOM codebook values; shared symmetric color scale across all ten planes",
        "hits_definition": "count of municipalities whose selected-model BMU is each neuron",
        "macroprofiles": {str(int(k)): int(v) for k, v in mapping["som_profile"].value_counts().sort_index().items()},
        "model_retrained": False,
        "profile_reclassification_performed": False,
        "mcdm_feedback": False,
        "all_visual_values_computed_from_frozen_som": True,
        "outputs": [
            "results/stage5/tables/stage5_som_real_node_diagnostics.csv",
            "results/stage5/figures/stage5_som_real_umatrix.png",
            "results/stage5/figures/stage5_som_real_umatrix.pdf",
            "results/stage5/figures/stage5_som_real_hits.png",
            "results/stage5/figures/stage5_som_real_hits.pdf",
            "results/stage5/figures/stage5_som_real_macroprofiles.png",
            "results/stage5/figures/stage5_som_real_macroprofiles.pdf",
            "results/stage5/figures/stage5_som_real_component_planes.png",
            "results/stage5/figures/stage5_som_real_component_planes.pdf",
            "results/stage5/figures/stage5_som_real_diagnostic_panel.png",
            "results/stage5/figures/stage5_som_real_diagnostic_panel.pdf",
        ],
    }
    (TABLES / "stage5_som_real_visual_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
