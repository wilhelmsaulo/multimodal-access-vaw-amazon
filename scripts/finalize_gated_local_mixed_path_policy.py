from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PRIMARY_EXCLUDED_CLASSES = {"proposed", "construction"}


def main() -> None:
    src = Path("artifacts/gated_local_mixed_path_restrictions/gated_local_mixed_path_restrictions.csv.gz")
    df = pd.read_csv(src, low_memory=False)
    if len(df) != 286:
        raise RuntimeError(f"Expected 286 audited gated mixed paths, found {len(df)}")

    restricted = df[df["audit_reason"].eq("explicit_access_or_motor_vehicle_restriction")].copy()
    unsupported = df[df["audit_reason"].eq("contains_unsupported_or_other_osm_class")].copy()

    if len(restricted) != 282:
        raise RuntimeError(f"Expected 282 explicitly restricted paths, found {len(restricted)}")
    if len(unsupported) != 4:
        raise RuntimeError(f"Expected 4 unsupported paths, found {len(unsupported)}")

    classes = set()
    for value in unsupported["unsupported_classes"].fillna("").astype(str):
        classes.update(x for x in value.split("|") if x)
    if not classes or not classes.issubset(PRIMARY_EXCLUDED_CLASSES):
        raise RuntimeError(f"Unexpected unsupported classes: {sorted(classes)}")

    unsupported["final_primary_policy"] = "exclude_nonoperational_osm_class_from_primary_routing"
    restricted["final_primary_policy"] = "exclude_explicitly_restricted_access_from_primary_routing"
    out = pd.concat([restricted, unsupported], ignore_index=True)
    out["travel_time_assigned"] = False
    out["connector_promoted"] = False

    outdir = Path("artifacts/gated_local_mixed_path_final_policy")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "gated_local_mixed_path_final_policy.csv.gz", index=False, compression="gzip")

    audit = {
        "audited_mixed_path_count": int(len(df)),
        "explicitly_restricted_excluded_count": int(len(restricted)),
        "nonoperational_osm_class_excluded_count": int(len(unsupported)),
        "nonoperational_class_counts": {str(k): int(v) for k, v in unsupported["unsupported_classes"].value_counts().to_dict().items()},
        "all_286_primary_policy_resolved": bool(len(out) == 286),
        "restricted_edges_promoted": False,
        "proposed_or_construction_promoted": False,
        "connector_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "All 286 empirically gated local mixed/other paths are closed for the primary analysis without introducing a new speed or distance rule. "
            "Paths containing explicit access=no/private or motor_vehicle=no/private restrictions remain excluded. The four remaining paths use only OSM highway=proposed or highway=construction, which are not treated as operational transport infrastructure in the primary routing graph. "
            "No connector or travel time is assigned to either group; track remains sensitivity-only under the separately locked policy."
        ),
    }
    (outdir / "gated_local_mixed_path_final_policy_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
