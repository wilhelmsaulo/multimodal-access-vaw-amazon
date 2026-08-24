from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def main() -> None:
    intersection_path = Path("artifacts/origin_cartographic_topology_intersection/origin_cartographic_topology_intersection.csv.gz")
    composition_path = Path("artifacts/local_access_path_modal_composition/local_access_path_modal_composition.csv.gz")
    output_dir = Path("artifacts/aligned_local_path_modal_composition")

    inter = pd.read_csv(intersection_path, dtype={"origin_id": "string"}, low_memory=False)
    comp = pd.read_csv(composition_path, dtype={"origin_id": "string"}, low_memory=False)

    aligned = inter[
        inter["cartographic_topology_class"].eq("local_alignment_but_physical_local_osm_path_required")
    ].copy()
    x = aligned.merge(comp, on="origin_id", how="left", validate="one_to_one", suffixes=("", "_path"))

    if x["path_highway_classes"].isna().any():
        missing = x.loc[x["path_highway_classes"].isna(), "origin_id"].astype(str).tolist()
        raise RuntimeError(f"Missing reconstructed local path composition for aligned origins: {missing[:10]}")

    x["aligned_local_path_evidence_class"] = "mixed_or_other_local_osm_path"
    x.loc[x["path_uses_track"].fillna(False).astype(bool), "aligned_local_path_evidence_class"] = "track_involved_sensitivity_only"
    x.loc[
        x["path_exclusively_pedestrian_classes"].fillna(False).astype(bool),
        "aligned_local_path_evidence_class",
    ] = "exclusively_pedestrian_osm_path"

    output_dir.mkdir(parents=True, exist_ok=True)
    x.to_csv(output_dir / "aligned_local_path_modal_composition.csv.gz", index=False, compression="gzip")

    counts = x["aligned_local_path_evidence_class"].value_counts().to_dict()
    female = pd.to_numeric(x.get("female_population"), errors="coerce")
    female_by_class = {
        str(k): float(female[x["aligned_local_path_evidence_class"].eq(k)].sum())
        for k in counts
    }
    dist = pd.to_numeric(x["local_osm_path_distance_to_primary_motor_m"], errors="coerce").dropna()
    audit = {
        "aligned_local_path_origins": int(len(x)),
        "evidence_class_counts": {str(k): int(v) for k, v in counts.items()},
        "female_population_by_evidence_class": female_by_class,
        "paths_using_track": int(x["path_uses_track"].fillna(False).astype(bool).sum()),
        "paths_exclusively_pedestrian_classes": int(x["path_exclusively_pedestrian_classes"].fillna(False).astype(bool).sum()),
        "path_distance_m_quantiles": {
            "min": float(dist.min()),
            "median": float(dist.median()),
            "p75": float(dist.quantile(0.75)),
            "p90": float(dist.quantile(0.90)),
            "p95": float(dist.quantile(0.95)),
            "max": float(dist.max()),
        } if not dist.empty else {},
        "walking_speed_assigned": False,
        "track_speed_assigned": False,
        "travel_time_assigned": False,
        "cartographic_alignment_used_as_physical_distance": False,
        "origin_access_temporal_connector_rule_resolved": False,
        "scientific_policy": (
            "The 157 empirically local but physically path-dependent origins are classified using the actual shortest OSM local path to the primary motor graph. "
            "Pedestrian-only paths are separated from paths involving track and from mixed/other classes. Track remains sensitivity-only. "
            "No walking or track speed is assigned and no travel time is created in this classification."
        ),
    }
    (output_dir / "aligned_local_path_modal_composition_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
