from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

SNAPS = Path("artifacts/spatial_transfer_snap_rule/validated_spatial_snap_anchors.csv")
OUT = Path("artifacts/spatial_snap_sensitivity")


def as_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().eq("true")


def scenario_row(name: str, active: pd.DataFrame, total: int) -> dict:
    hydro_ids = active["hydro_id"].astype(str).tolist() if len(active) else []
    return {
        "scenario": name,
        "active_anchor_count": int(len(active)),
        "active_anchor_share": float(len(active) / total) if total else 0.0,
        "distinct_hydro_route_count": int(active["hydro_id"].nunique()) if len(active) else 0,
        "anchor_names": "|".join(active["port_name"].astype(str).tolist()),
        "hydro_ids": "|".join(hydro_ids),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    snaps = pd.read_csv(SNAPS)
    if len(snaps) != 3:
        raise RuntimeError(f"Expected 3 validated snaps, got {len(snaps)}")

    required = {
        "anchor_id",
        "port_name",
        "hydro_id",
        "spatial_snap_eligible",
        "snap_distance_is_travel_distance",
        "spatial_distance_threshold_used",
        "zero_time_transfer_adopted",
        "distance_to_time_conversion_used",
        "routing_enabled",
    }
    missing = required.difference(snaps.columns)
    if missing:
        raise RuntimeError(f"Missing snap columns: {sorted(missing)}")

    if not as_bool(snaps["spatial_snap_eligible"]).all():
        raise RuntimeError("All three validated anchors must be spatial-snap eligible")
    for c in (
        "snap_distance_is_travel_distance",
        "spatial_distance_threshold_used",
        "zero_time_transfer_adopted",
        "distance_to_time_conversion_used",
        "routing_enabled",
    ):
        if as_bool(snaps[c]).any():
            raise RuntimeError(f"Upstream safeguard violated: {c}")

    snaps = snaps.sort_values("evidence_rank").reset_index(drop=True)
    total = len(snaps)
    scenarios: list[dict] = []
    scenarios.append(scenario_row("no_spatial_snaps", snaps.iloc[0:0], total))
    scenarios.append(scenario_row("all_validated_spatial_snaps", snaps, total))

    for _, row in snaps.iterrows():
        only = snaps[snaps["anchor_id"] == row["anchor_id"]]
        scenarios.append(scenario_row(f"only_{row['port_name']}", only, total))

    for _, row in snaps.iterrows():
        leave = snaps[snaps["anchor_id"] != row["anchor_id"]]
        scenarios.append(scenario_row(f"leave_out_{row['port_name']}", leave, total))

    scen = pd.DataFrame(scenarios)
    scen.to_csv(OUT / "spatial_snap_structural_sensitivity_scenarios.csv", index=False)

    unique_route_per_anchor = bool(snaps["hydro_id"].nunique() == len(snaps))
    leave_out = scen[scen["scenario"].str.startswith("leave_out_")].copy()
    leave_out_expected = bool(
        (leave_out["active_anchor_count"] == total - 1).all()
        and (leave_out["distinct_hydro_route_count"] == total - 1).all()
    )
    individual_validation_independent = bool(
        as_bool(snaps["spatial_snap_eligible"]).all() and leave_out_expected
    )

    audit = {
        "validated_anchor_count": total,
        "anchor_names": snaps["port_name"].astype(str).tolist(),
        "distinct_hydro_routes": int(snaps["hydro_id"].nunique()),
        "each_anchor_maps_to_distinct_hydro_route": unique_route_per_anchor,
        "scenario_count": int(len(scen)),
        "leave_one_out_scenarios_count": int(len(leave_out)),
        "leave_one_out_structure_expected": leave_out_expected,
        "individual_spatial_validation_independent_of_other_front1_anchors": individual_validation_independent,
        "spatial_snap_sensitivity_complete": True,
        "spatial_snap_rule_retained_after_sensitivity": bool(individual_validation_independent),
        "universal_distance_cutoff_used": False,
        "snap_distance_interpreted_as_travel_distance": False,
        "temporal_connector_impedance_resolved": False,
        "zero_time_transfer_adopted": False,
        "distance_to_time_conversion_used": False,
        "routing_enabled": False,
        "interpretation": (
            "Structural jackknife scenarios remove each validated spatial anchor in turn and also examine single-anchor and no-snap cases. "
            "The exercise tests whether the spatial rule is mechanically dependent on one front-1 anchor; it does not estimate travel-time effects or claim network-wide OD robustness."
        ),
        "next_required_step": (
            "Define the temporal treatment of the cartographic topology alignment without converting snap distance to travel time; "
            "waiting remains excluded and must be reported as a limitation."
        ),
    }
    (OUT / "spatial_snap_sensitivity_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(scen.to_string(index=False))


if __name__ == "__main__":
    main()
