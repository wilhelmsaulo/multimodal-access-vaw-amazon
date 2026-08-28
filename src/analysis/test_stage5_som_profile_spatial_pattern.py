from __future__ import annotations

"""Categorical spatial pattern test for frozen Stage-5 SOM macroprofiles.

P1-P4 are nominal categories. This script therefore does not compute Moran's I
on numeric profile IDs. Instead it builds a Queen-contiguity graph from the same
IBGE 2022 Para municipal mesh already used for Stage-5 spatialization and tests:

1. global same-profile neighbor share;
2. Newman's nominal assortativity coefficient on the municipal adjacency graph;
3. profile-specific same-profile join counts.

Inference uses fixed-graph label permutations, which preserve the observed
profile sizes exactly. This is post-training analysis only: no SOM retraining,
profile reclassification, MCDM reranking, or E2SFCA recomputation occurs.
"""

import io
import json
import zipfile
from pathlib import Path

import httpx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import geopandas as gpd
from libpysal.weights import Queen

ROOT = Path("results")
STAGE5 = ROOT / "stage5" / "tables"
OUT = ROOT / "spatial_profile_test"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
PROFILES = STAGE5 / "stage5_som_municipal_profiles.csv"
IBGE_MUNICIPAL_ZIP = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_2022/UFs/PA/PA_Municipios_2022.zip"
)
EXPECTED = 144
N_PERM = 9999
SEED = 20260828


def read_profiles() -> pd.DataFrame:
    df = pd.read_csv(PROFILES, dtype={"municipality_code": str})
    df["municipality_code"] = df["municipality_code"].astype(str).str.zfill(7)
    if len(df) != EXPECTED or df["municipality_code"].nunique() != EXPECTED:
        raise RuntimeError("Expected exactly 144 unique municipal SOM assignments")
    counts = df["som_profile"].value_counts().sort_index().to_dict()
    expected_counts = {1: 30, 2: 33, 3: 53, 4: 28}
    if {int(k): int(v) for k, v in counts.items()} != expected_counts:
        raise RuntimeError(f"Unexpected SOM profile sizes: {counts}")
    return df[["municipality_code", "municipality_name", "som_profile"]].copy()


def get_geometry() -> tuple[gpd.GeoDataFrame, int]:
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        r = client.get(IBGE_MUNICIPAL_ZIP)
        r.raise_for_status()
    if len(r.content) < 100_000:
        raise RuntimeError("IBGE municipal geometry archive is unexpectedly small")
    tmp = Path(".stage5_spatial_profile_ibge_pa")
    tmp.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        zf.extractall(tmp)
    shp = next(tmp.glob("*.shp"))
    geo = gpd.read_file(shp)
    code_candidates = [c for c in geo.columns if c.upper() in {"CD_MUN", "CD_MUNICIP", "CD_GEOCMU"}]
    if not code_candidates:
        code_candidates = [
            c for c in geo.columns
            if "CD_" in c.upper() and geo[c].astype(str).str.match(r"15\d{5}").sum() >= 100
        ]
    if not code_candidates:
        raise RuntimeError(f"Could not identify municipal code field: {list(geo.columns)}")
    geo["municipality_code"] = geo[code_candidates[0]].astype(str).str.extract(r"(\d{7})", expand=False)
    geo = geo[geo["municipality_code"].str.startswith("15", na=False)].copy()
    geo = geo[["municipality_code", "geometry"]].drop_duplicates("municipality_code")
    if len(geo) != EXPECTED:
        raise RuntimeError(f"Expected 144 Para municipal polygons; got {len(geo)}")
    return geo, len(r.content)


def build_edges(gdf: gpd.GeoDataFrame) -> tuple[list[tuple[int, int]], Queen, list[int]]:
    # ids are stable municipality codes, avoiding dependence on row position.
    w = Queen.from_dataframe(gdf, ids=gdf["municipality_code"].tolist(), use_index=False)
    code_to_pos = {c: i for i, c in enumerate(gdf["municipality_code"].tolist())}
    edges = set()
    for a, neighs in w.neighbors.items():
        ia = code_to_pos[a]
        for b in neighs:
            ib = code_to_pos[b]
            if ia != ib:
                edges.add((min(ia, ib), max(ia, ib)))
    edges = sorted(edges)
    islands = [code_to_pos[c] for c in w.islands]
    if not edges:
        raise RuntimeError("Queen graph contains no adjacency edges")
    return edges, w, islands


def adjacency_matrix(labels: np.ndarray, edges: list[tuple[int, int]], profiles=(1, 2, 3, 4)) -> np.ndarray:
    idx = {p: i for i, p in enumerate(profiles)}
    m = np.zeros((len(profiles), len(profiles)), dtype=int)
    for i, j in edges:
        a, b = int(labels[i]), int(labels[j])
        m[idx[a], idx[b]] += 1
        if a != b:
            m[idx[b], idx[a]] += 1
    return m


def same_edge_share(labels: np.ndarray, edges: list[tuple[int, int]]) -> float:
    return float(np.mean([labels[i] == labels[j] for i, j in edges]))


def assortativity_nominal(labels: np.ndarray, edges: list[tuple[int, int]], profiles=(1, 2, 3, 4)) -> float:
    idx = {p: i for i, p in enumerate(profiles)}
    m = np.zeros((len(profiles), len(profiles)), dtype=float)
    # Directed representation of each undirected edge for Newman's mixing matrix.
    for i, j in edges:
        a, b = idx[int(labels[i])], idx[int(labels[j])]
        m[a, b] += 1.0
        m[b, a] += 1.0
    e = m / m.sum()
    a = e.sum(axis=1)
    expected = float(np.sum(a * a))
    denom = 1.0 - expected
    if denom <= 0:
        return float("nan")
    return float((np.trace(e) - expected) / denom)


def join_counts(labels: np.ndarray, edges: list[tuple[int, int]], profiles=(1, 2, 3, 4)) -> np.ndarray:
    out = np.zeros(len(profiles), dtype=int)
    idx = {p: i for i, p in enumerate(profiles)}
    for i, j in edges:
        if labels[i] == labels[j]:
            out[idx[int(labels[i])]] += 1
    return out


def holm_adjust(pvals: np.ndarray) -> np.ndarray:
    pvals = np.asarray(pvals, dtype=float)
    m = len(pvals)
    order = np.argsort(pvals)
    adj_sorted = np.empty(m, dtype=float)
    running = 0.0
    for rank, oi in enumerate(order):
        val = (m - rank) * pvals[oi]
        running = max(running, val)
        adj_sorted[rank] = min(1.0, running)
    out = np.empty(m, dtype=float)
    for rank, oi in enumerate(order):
        out[oi] = adj_sorted[rank]
    return out


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    profiles = read_profiles()
    geo, source_bytes = get_geometry()
    g = geo.merge(profiles, on="municipality_code", how="left", validate="one_to_one")
    if g["som_profile"].isna().any():
        raise RuntimeError("Spatial join left municipalities without SOM profile")

    # Sort by municipality code so labels and edge positions are deterministic.
    g = g.sort_values("municipality_code").reset_index(drop=True)
    edges, w, island_positions = build_edges(g)
    labels = g["som_profile"].astype(int).to_numpy()
    rng = np.random.default_rng(SEED)

    obs_same = same_edge_share(labels, edges)
    obs_r = assortativity_nominal(labels, edges)
    obs_joins = join_counts(labels, edges)

    perm_same = np.empty(N_PERM, dtype=float)
    perm_r = np.empty(N_PERM, dtype=float)
    perm_joins = np.empty((N_PERM, 4), dtype=int)
    for b in range(N_PERM):
        pl = rng.permutation(labels)
        perm_same[b] = same_edge_share(pl, edges)
        perm_r[b] = assortativity_nominal(pl, edges)
        perm_joins[b, :] = join_counts(pl, edges)

    global_rows = []
    for name, observed, null in (
        ("same_profile_neighbor_share", obs_same, perm_same),
        ("nominal_assortativity", obs_r, perm_r),
    ):
        p_upper = (1 + int(np.sum(null >= observed))) / (N_PERM + 1)
        sd = float(np.std(null, ddof=1))
        z = (float(observed) - float(np.mean(null))) / sd if sd > 0 else np.nan
        global_rows.append({
            "statistic": name,
            "observed": float(observed),
            "permutation_mean": float(np.mean(null)),
            "permutation_sd": sd,
            "standardized_difference_z": float(z),
            "permutation_p_upper": float(p_upper),
            "permutations": N_PERM,
            "alternative": "greater spatial similarity/assortment than random label allocation",
        })
    global_df = pd.DataFrame(global_rows)
    global_df.to_csv(TABLES / "stage5_som_spatial_global_test.csv", index=False)

    join_rows = []
    raw_p = []
    for k, profile in enumerate((1, 2, 3, 4)):
        null = perm_joins[:, k].astype(float)
        observed = int(obs_joins[k])
        mean = float(np.mean(null))
        sd = float(np.std(null, ddof=1))
        p_upper = (1 + int(np.sum(null >= observed))) / (N_PERM + 1)
        raw_p.append(p_upper)
        join_rows.append({
            "som_profile": profile,
            "municipalities": int(np.sum(labels == profile)),
            "observed_same_profile_edges": observed,
            "permutation_mean_same_profile_edges": mean,
            "permutation_sd": sd,
            "enrichment_ratio_observed_over_null_mean": float(observed / mean) if mean > 0 else np.nan,
            "standardized_difference_z": float((observed - mean) / sd) if sd > 0 else np.nan,
            "permutation_p_upper_raw": float(p_upper),
        })
    adj = holm_adjust(np.array(raw_p))
    for row, p_adj in zip(join_rows, adj):
        row["permutation_p_holm_4_profiles"] = float(p_adj)
        row["significant_holm_0_05"] = bool(p_adj < 0.05)
    join_df = pd.DataFrame(join_rows)
    join_df.to_csv(TABLES / "stage5_som_spatial_profile_join_tests.csv", index=False)

    # Observed nominal edge mixing table. Diagonal counts are same-profile edges;
    # off-diagonal cells are symmetric counts of between-profile adjacencies.
    mix = adjacency_matrix(labels, edges)
    mix_df = pd.DataFrame(mix, index=["P1", "P2", "P3", "P4"], columns=["P1", "P2", "P3", "P4"])
    mix_df.index.name = "profile_from"
    mix_df.to_csv(TABLES / "stage5_som_spatial_profile_adjacency_matrix.csv")

    # Municipality degree table helps audit the contiguity graph and islands.
    degrees = {str(k): len(v) for k, v in w.neighbors.items()}
    deg_df = g[["municipality_code", "municipality_name", "som_profile"]].copy()
    deg_df["queen_neighbor_count"] = deg_df["municipality_code"].map(degrees).fillna(0).astype(int)
    deg_df["queen_island"] = deg_df["municipality_code"].isin(set(w.islands))
    deg_df.to_csv(TABLES / "stage5_som_spatial_queen_graph_municipalities.csv", index=False)

    # Publication figure 1: null distribution for global assortativity.
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.hist(perm_r, bins=40, alpha=0.85)
    ax.axvline(obs_r, linewidth=2, linestyle="--", label=f"Observed r = {obs_r:.3f}")
    ax.set_xlabel("Nominal assortativity under profile-label permutations")
    ax.set_ylabel("Frequency")
    ax.set_title("Spatial assortment of SOM profiles on Queen-contiguity graph")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "stage5_som_spatial_assortativity_permutation.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIGURES / "stage5_som_spatial_assortativity_permutation.pdf", bbox_inches="tight")
    plt.close(fig)

    # Publication figure 2: observed vs null profile-specific joins.
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    x = np.arange(4)
    means = perm_joins.mean(axis=0)
    sds = perm_joins.std(axis=0, ddof=1)
    ax.errorbar(x, means, yerr=sds, fmt="o", capsize=5, label="Permutation mean +/- 1 SD")
    ax.scatter(x, obs_joins, marker="D", s=65, label="Observed same-profile edges")
    ax.set_xticks(x, ["P1", "P2", "P3", "P4"])
    ax.set_ylabel("Same-profile Queen-contiguity edges")
    ax.set_xlabel("SOM macroprofile")
    ax.set_title("Observed profile adjacency versus random spatial allocation")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "stage5_som_spatial_profile_join_enrichment.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIGURES / "stage5_som_spatial_profile_join_enrichment.pdf", bbox_inches="tight")
    plt.close(fig)

    audit = {
        "stage": "Stage 5 categorical spatial profile test",
        "spatial_source": "IBGE Malha Municipal Digital 2022 - Para",
        "spatial_source_url": IBGE_MUNICIPAL_ZIP,
        "spatial_source_bytes": source_bytes,
        "municipalities": int(len(g)),
        "profile_sizes": {f"P{k}": int(np.sum(labels == k)) for k in (1, 2, 3, 4)},
        "profile_ids_treated_as_nominal": True,
        "numeric_morans_i_on_profile_ids_used": False,
        "contiguity": "Queen",
        "undirected_edge_count": int(len(edges)),
        "island_count": int(len(w.islands)),
        "island_municipality_codes": sorted(map(str, w.islands)),
        "permutations": N_PERM,
        "seed": SEED,
        "permutation_rule": "shuffle frozen P1-P4 labels over the fixed Queen graph; profile sizes therefore remain exactly preserved",
        "global_test_alternative": "more same-profile neighboring/assortative structure than expected under random label allocation",
        "profile_specific_multiple_testing": "Holm correction across four profile-specific same-profile join-count tests",
        "som_retrained": False,
        "profiles_reclassified": False,
        "mcdm_changed": False,
        "e2sfca_changed": False,
        "outputs": [
            "results/spatial_profile_test/tables/stage5_som_spatial_global_test.csv",
            "results/spatial_profile_test/tables/stage5_som_spatial_profile_join_tests.csv",
            "results/spatial_profile_test/tables/stage5_som_spatial_profile_adjacency_matrix.csv",
            "results/spatial_profile_test/tables/stage5_som_spatial_queen_graph_municipalities.csv",
            "results/spatial_profile_test/figures/stage5_som_spatial_assortativity_permutation.png",
            "results/spatial_profile_test/figures/stage5_som_spatial_assortativity_permutation.pdf",
            "results/spatial_profile_test/figures/stage5_som_spatial_profile_join_enrichment.png",
            "results/spatial_profile_test/figures/stage5_som_spatial_profile_join_enrichment.pdf",
        ],
    }
    (TABLES / "stage5_som_spatial_profile_test_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(global_df.to_string(index=False))
    print(join_df.to_string(index=False))


if __name__ == "__main__":
    main()
