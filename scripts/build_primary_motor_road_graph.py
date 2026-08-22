from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PRIMARY_MOTOR_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service",
}

SENSITIVITY_ONLY_CLASSES = {"track"}

EXCLUDED_NON_MOTOR_CLASSES = {
    "path", "footway", "cycleway", "pedestrian", "steps", "bridleway", "corridor",
    "busway", "bus_stop", "raceway", "construction", "proposed", "rest_area",
    "crossing", "emergency_access_point", "dummy", "services",
}

RESTRICTED_VALUES = {"no", "private"}


def _norm(x: object) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip().lower()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--edges", type=Path, default=Path("artifacts/transport_topology/road_edges.csv.gz"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/primary_motor_road_graph"))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.edges, low_memory=False)
    for c in ["highway", "access", "motor_vehicle"]:
        if c not in df.columns:
            df[c] = None

    highway = df["highway"].map(_norm)
    access = df["access"].map(_norm)
    motor_vehicle = df["motor_vehicle"].map(_norm)

    primary_class = highway.isin(PRIMARY_MOTOR_CLASSES)
    sensitivity_class = highway.isin(SENSITIVITY_ONLY_CLASSES)
    explicitly_restricted = access.isin(RESTRICTED_VALUES) | motor_vehicle.isin(RESTRICTED_VALUES)

    primary = df[primary_class & ~explicitly_restricted].copy()
    sensitivity = df[sensitivity_class & ~explicitly_restricted].copy()
    excluded = df[~(primary_class | sensitivity_class) | explicitly_restricted].copy()

    primary.to_csv(args.output_dir / "primary_motor_edges.csv.gz", index=False, compression="gzip")
    sensitivity.to_csv(args.output_dir / "track_sensitivity_edges.csv.gz", index=False, compression="gzip")

    total_length = float(pd.to_numeric(df["length_m"], errors="coerce").fillna(0).sum() / 1000)
    primary_length = float(pd.to_numeric(primary["length_m"], errors="coerce").fillna(0).sum() / 1000)
    sensitivity_length = float(pd.to_numeric(sensitivity["length_m"], errors="coerce").fillna(0).sum() / 1000)

    excluded_counts = excluded["highway"].fillna("<missing>").astype(str).value_counts().to_dict()
    audit = {
        "edges_total": int(len(df)),
        "total_length_km": total_length,
        "primary_motor_edges": int(len(primary)),
        "primary_motor_length_km": primary_length,
        "primary_motor_edge_fraction": float(len(primary) / len(df)) if len(df) else None,
        "primary_motor_length_fraction": float(primary_length / total_length) if total_length else None,
        "track_sensitivity_edges": int(len(sensitivity)),
        "track_sensitivity_length_km": sensitivity_length,
        "explicitly_restricted_edges_excluded": int(explicitly_restricted.sum()),
        "primary_motor_classes": sorted(PRIMARY_MOTOR_CLASSES),
        "sensitivity_only_classes": sorted(SENSITIVITY_ONLY_CLASSES),
        "excluded_non_motor_classes": sorted(EXCLUDED_NON_MOTOR_CLASSES),
        "excluded_or_other_highway_counts": excluded_counts,
        "policy": (
            "Primary motor routing uses conventional OSM motor-vehicle road classes and excludes edges "
            "explicitly tagged access=no/private or motor_vehicle=no/private. Track is not included in the "
            "primary graph because its motorability and realized speed are context-dependent in the Amazon; "
            "it is retained as a separate sensitivity layer. Pedestrian/cycle/proposed/construction/special-purpose "
            "tags are excluded from the primary motor graph. No travel-time weight is assigned in this stage."
        ),
        "travel_time_assigned": False,
        "ready_for_primary_road_speed_assignment": bool(len(primary) > 0),
    }
    (args.output_dir / "primary_motor_road_graph_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
