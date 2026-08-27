from __future__ import annotations

"""Stage 3 pre-MCDM statistical audit.

The audit is diagnostic: it does not delete indicators or run PCA automatically.
When explicit ``criterion__`` columns exist, only those candidate criteria enter
missingness/distribution/correlation/VIF calculations. ``diagnostic__`` support
columns remain in the matrix but cannot create artificial multicollinearity flags.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ID_HINTS = {
    "municipality_id", "municipality_code", "ibge_code", "code_muni",
    "municipio_id", "cod_mun", "cd_mun", "id_municipality",
}
NAME_HINTS = {
    "municipality", "municipality_name", "municipio", "nome_municipio", "nm_mun",
}
META_HINTS = {
    "year", "reference_year", "source_year", "data_year", "reference_date",
    "source", "dataset", "provenance", "timestamp", "date",
}


def _numeric_indicator_columns(df: pd.DataFrame) -> list[str]:
    explicit = [c for c in df.columns if c.startswith("criterion__")]
    if explicit:
        valid = []
        for col in explicit:
            if pd.to_numeric(df[col], errors="coerce").notna().sum() >= 3:
                valid.append(col)
        return valid

    excluded = {c for c in df.columns if c.lower() in ID_HINTS | NAME_HINTS | META_HINTS}
    cols: list[str] = []
    for col in df.columns:
        if col in excluded or col.startswith("diagnostic__"):
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().sum() >= 3:
            cols.append(col)
    return cols


def _vif_matrix(x: pd.DataFrame) -> pd.DataFrame:
    rows = []
    x = x.copy().loc[:, x.nunique(dropna=True) > 1]
    complete = x.dropna()
    if len(complete) < 3:
        return pd.DataFrame(columns=["indicator", "vif", "n_complete"])
    arr = complete.to_numpy(dtype=float)
    for j, col in enumerate(complete.columns):
        y = arr[:, j]
        others = np.delete(arr, j, axis=1)
        if others.shape[1] == 0:
            vif = 1.0
        else:
            design = np.column_stack([np.ones(len(others)), others])
            coef, *_ = np.linalg.lstsq(design, y, rcond=None)
            fitted = design @ coef
            ss_res = float(np.sum((y - fitted) ** 2))
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            r2 = 0.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
            vif = float("inf") if r2 >= 1.0 - 1e-12 else 1.0 / (1.0 - r2)
        rows.append({"indicator": col, "vif": vif, "n_complete": int(len(complete))})
    return pd.DataFrame(rows).sort_values("vif", ascending=False, na_position="last")


def audit(input_path: Path, out_dir: Path, corr_threshold: float = 0.80, vif_threshold: float = 5.0) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path)
    indicators = _numeric_indicator_columns(df)
    if not indicators:
        raise RuntimeError("No numeric candidate indicator columns detected in analytical matrix")

    x = pd.DataFrame({c: pd.to_numeric(df[c], errors="coerce") for c in indicators})
    completeness = pd.DataFrame({
        "indicator": indicators,
        "n_rows": len(df),
        "n_nonmissing": [int(x[c].notna().sum()) for c in indicators],
        "n_missing": [int(x[c].isna().sum()) for c in indicators],
        "missing_fraction": [float(x[c].isna().mean()) for c in indicators],
        "n_unique": [int(x[c].nunique(dropna=True)) for c in indicators],
    }).sort_values(["missing_fraction", "indicator"], ascending=[False, True])

    distribution = x.describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).T.reset_index().rename(columns={"index": "indicator"})
    distribution["zero_fraction"] = [float((x[c] == 0).mean()) for c in distribution["indicator"]]
    distribution["skew"] = [float(x[c].skew()) for c in distribution["indicator"]]

    pearson = x.corr(method="pearson", min_periods=3)
    spearman = x.corr(method="spearman", min_periods=3)
    pairs = []
    for i, a in enumerate(indicators):
        for b in indicators[i + 1:]:
            pr, sr = pearson.loc[a, b], spearman.loc[a, b]
            vals = [abs(pr) if pd.notna(pr) else np.nan, abs(sr) if pd.notna(sr) else np.nan]
            max_abs = np.nanmax(vals)
            if pd.notna(max_abs) and max_abs >= corr_threshold:
                pairs.append({
                    "indicator_a": a, "indicator_b": b,
                    "pearson_r": None if pd.isna(pr) else float(pr),
                    "spearman_rho": None if pd.isna(sr) else float(sr),
                    "max_abs_correlation": float(max_abs), "threshold": corr_threshold,
                })
    redundant_pairs = pd.DataFrame(pairs)
    if not redundant_pairs.empty:
        redundant_pairs = redundant_pairs.sort_values("max_abs_correlation", ascending=False)

    vif = _vif_matrix(x)
    vif_flagged = vif[vif["vif"] >= vif_threshold].copy() if not vif.empty else vif.copy()

    temporal = []
    for col in [c for c in df.columns if c.lower() in META_HINTS]:
        vals = df[col].dropna().astype(str)
        temporal.append({
            "column": col, "n_nonmissing": int(len(vals)), "n_unique": int(vals.nunique()),
            "sample_values": vals.drop_duplicates().head(20).tolist(),
        })

    pca_recommended = bool((not redundant_pairs.empty) or (not vif_flagged.empty))
    pca_reason = (
        "Redundancy/multicollinearity diagnostics exceed configured thresholds; PCA may be used as a sensitivity/diagnostic analysis, not as an automatic replacement of interpretable indicators."
        if pca_recommended else
        "No configured correlation/VIF threshold was exceeded; PCA is not required at this stage."
    )

    completeness.to_csv(out_dir / "indicator_completeness.csv", index=False)
    distribution.to_csv(out_dir / "indicator_distribution.csv", index=False)
    pearson.to_csv(out_dir / "correlation_pearson.csv")
    spearman.to_csv(out_dir / "correlation_spearman.csv")
    redundant_pairs.to_csv(out_dir / "redundant_indicator_pairs.csv", index=False)
    vif.to_csv(out_dir / "vif.csv", index=False)

    summary = {
        "stage": "Stage 3 - pre-MCDM statistical audit",
        "input": str(input_path),
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "candidate_indicators_audited": len(indicators),
        "indicators": indicators,
        "diagnostic_columns_excluded_from_statistics": [c for c in df.columns if c.startswith("diagnostic__")],
        "max_missing_fraction": float(completeness["missing_fraction"].max()),
        "indicators_with_any_missing": int((completeness["n_missing"] > 0).sum()),
        "correlation_threshold_abs": corr_threshold,
        "redundant_pairs_flagged": int(len(redundant_pairs)),
        "vif_threshold": vif_threshold,
        "vif_indicators_flagged": int(len(vif_flagged)),
        "vif_max": None if vif.empty else ("Infinity" if np.isinf(vif["vif"].max()) else float(vif["vif"].max())),
        "temporal_metadata_columns_detected": temporal,
        "pca_recommended_for_diagnostic_or_sensitivity_analysis": pca_recommended,
        "pca_reason": pca_reason,
        "mcdm_ready": False,
        "mcdm_readiness_note": "MCDM readiness must be decided after scientific review of missingness, temporal compatibility, redundancy, scale, sociodemographic inclusion, and weighting/model specification.",
    }
    (out_dir / "stage3_audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--out", type=Path, default=Path("artifacts/stage3_statistical_audit"))
    p.add_argument("--corr-threshold", type=float, default=0.80)
    p.add_argument("--vif-threshold", type=float, default=5.0)
    args = p.parse_args()
    print(json.dumps(audit(args.input, args.out, args.corr_threshold, args.vif_threshold), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
