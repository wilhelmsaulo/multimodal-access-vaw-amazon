from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd


def main() -> None:
    source = Path("artifacts/aligned_local_path_modal_composition/aligned_local_path_modal_composition.csv.gz")
    output_dir = Path("artifacts/mixed_aligned_local_paths")
    df = pd.read_csv(source, low_memory=False)
    mixed = df[df["aligned_local_path_evidence_class"].eq("mixed_or_other_local_osm_path")].copy()
    if len(mixed) != 109:
        raise RuntimeError(f"Expected 109 mixed aligned local paths, found {len(mixed)}")

    combo_counts = Counter(mixed["path_highway_classes"].fillna("").astype(str))
    token_counts: Counter[str] = Counter()
    for value in mixed["path_highway_classes"].fillna("").astype(str):
        for token in {x for x in value.split("|") if x}:
            token_counts[token] += 1

    motor_like = {"living_street", "residential", "service", "tertiary", "unclassified", "secondary", "primary", "trunk"}
    pedestrian = {"footway", "path", "pedestrian", "steps", "cycleway"}
    sensitivity = {"track"}
    unsupported = {"proposed", "construction", "services", "road", "busway", "corridor", "bridleway", "raceway"}

    def semantic_class(value: str) -> str:
        toks = {x for x in str(value).split("|") if x}
        if toks & sensitivity:
            return "contains_track_sensitivity_only"
        if toks & unsupported:
            return "contains_unsupported_or_incomplete_osm_class"
        if toks and toks <= motor_like:
            return "motor_like_local_path_but_excluded_from_primary_topology"
        if toks and toks <= (motor_like | pedestrian) and (toks & pedestrian) and (toks & motor_like):
            return "pedestrian_motor_mixed_local_path"
        if toks and toks <= pedestrian:
            return "pedestrian_only_should_have_been_classified_separately"
        return "other_or_unknown_local_path"

    mixed["mixed_path_semantic_class"] = mixed["path_highway_classes"].map(semantic_class)
    output_dir.mkdir(parents=True, exist_ok=True)
    mixed.to_csv(output_dir / "mixed_aligned_local_paths.csv.gz", index=False, compression="gzip")

    audit = {
        "mixed_aligned_local_path_origins": int(len(mixed)),
        "semantic_class_counts": {str(k): int(v) for k, v in mixed["mixed_path_semantic_class"].value_counts().to_dict().items()},
        "highway_token_origin_counts": {str(k): int(v) for k, v in token_counts.most_common()},
        "top_path_class_combinations": {str(k): int(v) for k, v in combo_counts.most_common(20)},
        "travel_time_assigned": False,
        "walking_speed_assigned": False,
        "track_speed_assigned": False,
        "motor_speed_assigned_to_nonprimary_path": False,
        "scientific_policy": (
            "The 109 mixed/other aligned local OSM paths are decomposed by actual highway classes before any temporal rule is considered. "
            "No motor or pedestrian speed is assigned merely because a class label appears in a path, and track remains sensitivity-only."
        ),
    }
    (output_dir / "mixed_aligned_local_paths_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
