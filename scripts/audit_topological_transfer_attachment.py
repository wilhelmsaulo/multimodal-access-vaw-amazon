from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ANCHORS = Path("artifacts/validated_spatial_transfer_anchors/validated_spatial_transfer_anchors.csv")
OUT = Path("artifacts/topological_transfer_attachment_audit")


def classify(row: pd.Series) -> str:
    hydro = float(row["hydro_distance_m_canonical"])
    road = float(row["road_distance_m"])
    # Descriptive classes only. These are not routing thresholds and do not
    # enable temporal traversal. The purpose is to distinguish near-coincident
    # geometry from clearly non-coincident geometry before a methodological
    # decision on connector impedance.
    if hydro < 1.0 and road < 1.0:
        return "near_coincident_geometry"
    return "noncoincident_geometry_requires_explicit_connector_treatment"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(ANCHORS)
    if len(df) != 3:
        raise RuntimeError(f"Expected 3 validated anchors, found {len(df)}")

    df["attachment_geometry_class"] = df.apply(classify, axis=1)
    df["topological_zero_cost_candidate"] = df["attachment_geometry_class"].eq("near_coincident_geometry")
    df["topological_zero_cost_adopted"] = False
    df["temporal_connector_impedance_resolved"] = False
    df["routing_enabled"] = False

    df.to_csv(OUT / "topological_transfer_attachment_audit.csv", index=False)

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "port_name": str(r["port_name"]),
            "road_distance_m": float(r["road_distance_m"]),
            "hydro_distance_m": float(r["hydro_distance_m_canonical"]),
            "attachment_geometry_class": str(r["attachment_geometry_class"]),
            "topological_zero_cost_candidate": bool(r["topological_zero_cost_candidate"]),
            "topological_zero_cost_adopted": False,
            "routing_enabled": False,
        })

    audit = {
        "anchor_count": int(len(df)),
        "near_coincident_geometry_count": int(df["topological_zero_cost_candidate"].sum()),
        "noncoincident_geometry_count": int((~df["topological_zero_cost_candidate"]).sum()),
        "temporal_connector_impedance_resolved": False,
        "topological_zero_cost_adopted": False,
        "routing_enabled": False,
        "scientific_policy": (
            "This audit only distinguishes near-coincident port/road/hydro geometry from non-coincident geometry. "
            "The <1 m descriptor identifies effectively coincident coordinates at the resolution of the source layers; "
            "it is not a statewide routing threshold. No zero-cost connector is adopted here. Non-coincident anchors "
            "require explicit connector treatment rather than an unsupported distance-to-time conversion."
        ),
        "rows": rows,
    }
    (OUT / "topological_transfer_attachment_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
