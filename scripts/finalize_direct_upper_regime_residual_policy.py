from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def main() -> None:
    src = Path("artifacts/direct_upper_regime_residuals/direct_upper_regime_residuals.csv.gz")
    df = pd.read_csv(src, low_memory=False)
    if len(df) != 1765:
        raise RuntimeError(f"Expected 1765 direct upper-regime residuals, found {len(df)}")

    hydro = df["residual_priority_class"].eq("hydro_priority_for_evidence_review")
    road = df["residual_priority_class"].eq("road_priority_for_evidence_review")
    if int(hydro.sum()) != 257 or int(road.sum()) != 1508:
        raise RuntimeError(f"Unexpected partition hydro={int(hydro.sum())}, road={int(road.sum())}")

    out = df[["origin_id", "municipality_code", "municipality_name", "female_population",
              "distance_to_road_m_evidence", "distance_to_waterway_m",
              "attachment_evidence_group", "residual_priority_class"]].copy()
    out["primary_attachment_status"] = "unresolved_excluded_from_primary_routing"
    out["sensitivity_role"] = out["residual_priority_class"].map({
        "hydro_priority_for_evidence_review": "hydro_priority_residual_for_sensitivity_or_future_evidence",
        "road_priority_for_evidence_review": "road_priority_residual_for_sensitivity_or_future_evidence",
    })
    out["connector_promoted"] = False
    out["travel_time_assigned"] = False
    out["nearest_snap_used_as_primary_connector"] = False

    outdir = Path("artifacts/direct_upper_regime_residual_policy")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "direct_upper_regime_residual_policy.csv.gz", index=False, compression="gzip")

    audit = {
        "direct_upper_regime_residual_count": int(len(out)),
        "female_population": float(pd.to_numeric(out["female_population"], errors="coerce").fillna(0).sum()),
        "hydro_priority_residual_count": int(hydro.sum()),
        "road_priority_residual_count": int(road.sum()),
        "primary_attachment_resolved_count": 0,
        "primary_attachment_unresolved_count": int(len(out)),
        "nearest_snap_used_as_primary_connector": False,
        "proximity_used_to_assign_mode": False,
        "connector_promoted": False,
        "travel_time_assigned": False,
        "primary_policy": (
            "Direct-primary origins outside the empirically supported local cartographic regime remain unresolved and are excluded from primary routing rather than attached by an unsupported nearest-network snap. "
            "Road-versus-waterway proximity is retained only as a residual-review/sensitivity label. This conservative exclusion and its represented female population must be reported as a coverage limitation and evaluated in sensitivity analysis."
        ),
    }
    (outdir / "direct_upper_regime_residual_policy_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
