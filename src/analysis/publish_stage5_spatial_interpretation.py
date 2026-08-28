from __future__ import annotations

"""Publish spatial and interpretive artifacts for the completed Stage-5 SOM.

This step is post-training. It does not retrain the SOM and does not alter the
Stage-4 MCDM ranking. It spatializes the frozen P1..P4 profiles, identifies
representative/extreme municipalities reproducibly, and summarizes the post-hoc
association between SOM profiles and frozen PROMETHEE-II priority.
"""

import io
import json
import zipfile
from pathlib import Path

import httpx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import geopandas as gpd
except ImportError:  # pragma: no cover
    gpd = None

ROOT = Path("results/stage5")
TABLES = ROOT / "tables"
FIGURES = ROOT / "figures"
PROFILES = TABLES / "stage5_som_municipal_profiles.csv"
CHARACTERISTICS = TABLES / "stage5_som_profile_characteristics.csv"
MCDM_SUMMARY = TABLES / "stage5_som_profile_promethee_summary.csv"
MCDM_JOIN = TABLES / "stage5_som_profiles_with_promethee.csv"
AGE = TABLES / "stage5_complete_female_age_candidate.csv"
RACE = TABLES / "stage5_female_race_color_candidates.csv"
LITERACY = TABLES / "stage5_female_literacy_candidate.csv"
INCOME = TABLES / "stage5_income_candidate.csv"
BASE = Path("results/stage3/tables/municipal_analytical_matrix.csv")

IBGE_MUNICIPAL_ZIP = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_2022/UFs/PA/PA_Municipios_2022.zip"
)
EXPECTED = 144

INTERPRET = [
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
LABELS = {
    "criterion__rural_female_share": "Rural female share",
    "socio__female_literacy_rate_15plus": "Female literacy 15+",
    "socio__household_per_capita_income_mean_brl": "Household income pc",
    "socio__female_age_share_15_29": "Women 15–29",
    "socio__female_age_share_30_59": "Women 30–59",
    "socio__female_age_share_60_plus": "Women 60+",
    "socio__female_race_share_branca": "Women branca",
    "socio__female_race_share_preta": "Women preta",
    "socio__female_race_share_parda": "Women parda",
    "socio__female_race_share_amarela": "Women amarela",
    "socio__female_race_share_indigena": "Women indígena",
}


def read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"municipality_code": str}, low_memory=False)
    if "municipality_code" in df.columns:
        df["municipality_code"] = df["municipality_code"].astype(str).str.zfill(7)
    return df


def build_interpretable_matrix() -> pd.DataFrame:
    p = read(PROFILES)
    base = read(BASE)[["municipality_code", "municipality_name", "criterion__rural_female_share"]]
    age = read(AGE)[["municipality_code", "socio__female_age_share_15_29", "socio__female_age_share_30_59", "socio__female_age_share_60_plus"]]
    race = read(RACE)[["municipality_code", "socio__female_race_share_branca", "socio__female_race_share_preta", "socio__female_race_share_parda", "socio__female_race_share_amarela", "socio__female_race_share_indigena"]]
    lit = read(LITERACY)[["municipality_code", "socio__female_literacy_rate_15plus"]]
    inc = read(INCOME)[["municipality_code", "socio__household_per_capita_income_mean_brl"]]
    out = p.merge(base, on=["municipality_code", "municipality_name"], how="left", validate="one_to_one")
    for frame in (age, race, lit, inc):
        out = out.merge(frame, on="municipality_code", how="left", validate="one_to_one")
    if len(out) != EXPECTED or out[INTERPRET].isna().any().any():
        raise RuntimeError("Interpretive matrix failed integrity/missingness check")
    return out


def representative_table(df: pd.DataFrame) -> pd.DataFrame:
    z = (df[INTERPRET] - df[INTERPRET].mean()) / df[INTERPRET].std(ddof=0)
    rows = []
    for profile, idx in df.groupby("som_profile").groups.items():
        sub = z.loc[idx]
        centroid = sub.mean(axis=0).to_numpy(float)
        dist = np.linalg.norm(sub.to_numpy(float) - centroid, axis=1)
        order = np.argsort(dist)
        for kind, positions in (("representative", order[:3]), ("extreme", order[::-1][:3])):
            for rank, pos in enumerate(positions, 1):
                i = sub.index[pos]
                rows.append({
                    "som_profile": int(profile),
                    "selection_type": kind,
                    "within_type_rank": rank,
                    "municipality_code": df.loc[i, "municipality_code"],
                    "municipality_name": df.loc[i, "municipality_name"],
                    "standardized_distance_to_profile_centroid": float(dist[pos]),
                })
    return pd.DataFrame(rows).sort_values(["som_profile", "selection_type", "within_type_rank"])


def profile_signatures(df: pd.DataFrame) -> pd.DataFrame:
    global_mean = df[INTERPRET].mean()
    global_sd = df[INTERPRET].std(ddof=0).replace(0, np.nan)
    prof = df.groupby("som_profile")[INTERPRET].mean()
    z = (prof - global_mean) / global_sd
    rows = []
    for profile in z.index:
        vals = z.loc[profile].sort_values()
        for direction, items in (("lower", vals.head(3)), ("higher", vals.tail(3).sort_values(ascending=False))):
            for rank, (feature, value) in enumerate(items.items(), 1):
                rows.append({
                    "som_profile": int(profile),
                    "direction": direction,
                    "rank": rank,
                    "feature": feature,
                    "feature_label": LABELS[feature],
                    "z_difference_from_state_mean": float(value),
                })
    return pd.DataFrame(rows)


def get_geometry():
    if gpd is None:
        raise RuntimeError("geopandas is required for spatial artifact publication")
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        r = client.get(IBGE_MUNICIPAL_ZIP)
        r.raise_for_status()
    if len(r.content) < 100_000:
        raise RuntimeError("IBGE municipal geometry archive is unexpectedly small")
    tmp = Path(".stage5_ibge_pa")
    tmp.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        zf.extractall(tmp)
    shp = next(tmp.glob("*.shp"))
    geo = gpd.read_file(shp)
    code_candidates = [c for c in geo.columns if c.upper() in {"CD_MUN", "CD_MUNICIP", "CD_GEOCMU"}]
    if not code_candidates:
        code_candidates = [c for c in geo.columns if "CD_" in c.upper() and geo[c].astype(str).str.match(r"15\d{5}").sum() >= 100]
    if not code_candidates:
        raise RuntimeError(f"Could not identify municipal code field in IBGE geometry: {list(geo.columns)}")
    geo["municipality_code"] = geo[code_candidates[0]].astype(str).str.extract(r"(\d{7})", expand=False)
    geo = geo[geo["municipality_code"].str.startswith("15", na=False)].copy()
    if geo["municipality_code"].nunique() != EXPECTED:
        raise RuntimeError(f"Expected 144 polygons; got {geo['municipality_code'].nunique()}")
    return geo[["municipality_code", "geometry"]], len(r.content)


def plot_profile_map(geo, profiles: pd.DataFrame):
    g = geo.merge(profiles[["municipality_code", "som_profile"]], on="municipality_code", validate="one_to_one")
    fig, ax = plt.subplots(figsize=(9, 10))
    g.plot(column="som_profile", categorical=True, legend=True, ax=ax, edgecolor="white", linewidth=0.25)
    ax.set_title("Stage 5 SOM socioeconomic/demographic profiles — Pará")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(FIGURES / "stage5_som_profiles_pará_map.png", dpi=220, bbox_inches="tight")
    fig.savefig(FIGURES / "stage5_som_profiles_para_map.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_characteristic_heatmap(df: pd.DataFrame):
    global_mean = df[INTERPRET].mean()
    global_sd = df[INTERPRET].std(ddof=0).replace(0, np.nan)
    z = (df.groupby("som_profile")[INTERPRET].mean() - global_mean) / global_sd
    fig, ax = plt.subplots(figsize=(12, 5.8))
    im = ax.imshow(z.to_numpy(), aspect="auto")
    ax.set_yticks(range(len(z.index)), [f"P{x}" for x in z.index])
    ax.set_xticks(range(len(INTERPRET)), [LABELS[x] for x in INTERPRET], rotation=55, ha="right")
    ax.set_title("Profile characteristics relative to Pará municipal mean (z-score)")
    fig.colorbar(im, ax=ax, label="Standardized difference")
    fig.tight_layout()
    fig.savefig(FIGURES / "stage5_som_profile_characteristics_heatmap.png", dpi=220, bbox_inches="tight")
    fig.savefig(FIGURES / "stage5_som_profile_characteristics_heatmap.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_mcdm_panel(summary: pd.DataFrame):
    s = summary.sort_values("som_profile")
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.bar([f"P{x}" for x in s["som_profile"]], s["top_quartile_share"] * 100)
    ax.set_ylabel("Municipalities in PROMETHEE-II top quartile (%)")
    ax.set_xlabel("SOM profile")
    ax.set_ylim(0, max(55, float((s["top_quartile_share"] * 100).max()) + 5))
    ax.set_title("Post-hoc association: SOM profiles × frozen MCDM priority")
    for i, v in enumerate(s["top_quartile_share"] * 100):
        ax.text(i, float(v) + 1, f"{v:.1f}%", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(FIGURES / "stage5_som_mcdm_profile_association.png", dpi=220, bbox_inches="tight")
    fig.savefig(FIGURES / "stage5_som_mcdm_profile_association.pdf", bbox_inches="tight")
    plt.close(fig)


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    df = build_interpretable_matrix()
    reps = representative_table(df)
    reps.to_csv(TABLES / "stage5_som_profile_representative_extreme_municipalities.csv", index=False)
    sig = profile_signatures(df)
    sig.to_csv(TABLES / "stage5_som_profile_signatures.csv", index=False)

    summary = pd.read_csv(MCDM_SUMMARY)
    joined = read(MCDM_JOIN)
    overlap = pd.crosstab(joined["som_profile"], joined["top_quartile"], margins=True)
    overlap.to_csv(TABLES / "stage5_som_promethee_top_quartile_crosstab.csv")

    geo, source_bytes = get_geometry()
    plot_profile_map(geo, df)
    plot_characteristic_heatmap(df)
    plot_mcdm_panel(summary)

    audit = {
        "stage": "Stage 5 post-training spatial and interpretive artifact publication",
        "municipalities": int(df["municipality_code"].nunique()),
        "som_profiles": sorted(map(int, df["som_profile"].unique())),
        "profile_labels_are_neutral": True,
        "representative_rule": "three municipalities nearest to each profile centroid in globally standardized 11-variable interpretable space",
        "extreme_rule": "three municipalities farthest from each profile centroid in the same standardized interpretable space",
        "signature_rule": "three highest and three lowest profile mean z-differences relative to all Pará municipalities",
        "spatial_source": "IBGE Malha Municipal Digital 2022 — Pará",
        "spatial_source_url": IBGE_MUNICIPAL_ZIP,
        "spatial_source_bytes": source_bytes,
        "spatial_polygon_count": int(geo["municipality_code"].nunique()),
        "mcdm_cross_tab_role": "post-hoc descriptive association only; no feedback into SOM training or Stage-4 ranking",
        "artifacts": {
            "map_png": "results/stage5/figures/stage5_som_profiles_pará_map.png",
            "map_pdf": "results/stage5/figures/stage5_som_profiles_para_map.pdf",
            "characteristics_png": "results/stage5/figures/stage5_som_profile_characteristics_heatmap.png",
            "characteristics_pdf": "results/stage5/figures/stage5_som_profile_characteristics_heatmap.pdf",
            "mcdm_association_png": "results/stage5/figures/stage5_som_mcdm_profile_association.png",
            "mcdm_association_pdf": "results/stage5/figures/stage5_som_mcdm_profile_association.pdf",
            "representative_extreme_table": "results/stage5/tables/stage5_som_profile_representative_extreme_municipalities.csv",
            "profile_signatures": "results/stage5/tables/stage5_som_profile_signatures.csv",
            "top_quartile_crosstab": "results/stage5/tables/stage5_som_promethee_top_quartile_crosstab.csv",
        },
    }
    (TABLES / "stage5_spatial_interpretation_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
