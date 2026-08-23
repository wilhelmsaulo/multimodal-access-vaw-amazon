from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

WATERWAYS = Path("artifacts/multimodal_graph_inputs/waterways.gpkg")
OUT = Path("artifacts/hydro_temporal_graph_reference")
TIME_RE = re.compile(r"^\s*(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)min\s*)?$", re.I)
METRIC_CRS = "EPSG:5880"
NUMERICAL_GEOMETRY_TOL_M = 1e-6


def parse_minutes(v: object) -> float | None:
    if v is None or pd.isna(v):
        return None
    m = TIME_RE.fullmatch(str(v).strip())
    if not m:
        return None
    total = int(m.group(1) or 0) * 1440 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
    return float(total) if total > 0 else None


def norm_hydro_id(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    s = str(v).strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


def normalize_scalar(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    return str(v).strip()


def canonicalize_by_hydro_id(w: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    if "hydro_id" not in w.columns:
        raise RuntimeError("Canonical waterways lack hydro_id")
    w = w.copy().reset_index(drop=True)
    w["hydro_id_norm"] = w["hydro_id"].map(norm_hydro_id)
    if (w["hydro_id_norm"] == "").any():
        raise RuntimeError("All ANTAQ waterway records must have hydro_id")

    temporal_cols = [
        "origin_municipality", "origin_state", "destination_municipality", "destination_state",
        "reported_length_km", "reported_time", "reference_speed_kmh",
    ]
    for c in temporal_cols:
        if c not in w.columns:
            raise RuntimeError(f"Canonical waterways lack required provenance/impedance field: {c}")

    wm = w.to_crs(METRIC_CRS)
    selected_rows: list[pd.Series] = []
    overlap_rows: list[dict[str, object]] = []
    duplicate_groups = 0
    max_hausdorff = 0.0

    for hid, idxs_raw in w.groupby("hydro_id_norm", sort=True).groups.items():
        idxs = list(idxs_raw)
        group = w.loc[idxs].copy()
        if len(group) > 1:
            duplicate_groups += 1

        # Official impedance and OD attributes must agree across archive copies.
        for c in temporal_cols:
            if c in {"reported_length_km", "reference_speed_kmh"}:
                vals = pd.to_numeric(group[c], errors="coerce").round(9).dropna().unique().tolist()
            else:
                vals = sorted({normalize_scalar(v) for v in group[c]})
            if len(vals) != 1:
                raise RuntimeError(f"Conflicting {c} across archive copies for hydro_id={hid}: {vals}")

        # Compare all geometry copies only to detect representation differences.
        pair_haus = []
        if len(idxs) > 1:
            geoms = [wm.geometry.iloc[i] for i in idxs]
            for a in range(len(geoms)):
                for b in range(a + 1, len(geoms)):
                    pair_haus.append(float(geoms[a].hausdorff_distance(geoms[b])))
        group_max_haus = max(pair_haus) if pair_haus else 0.0
        max_hausdorff = max(max_hausdorff, group_max_haus)
        if group_max_haus > NUMERICAL_GEOMETRY_TOL_M:
            raise RuntimeError(
                f"Geometry copies for hydro_id={hid} differ beyond numerical tolerance: "
                f"max_hausdorff_m={group_max_haus}"
            )

        # Deterministic representative only; source provenance is aggregated explicitly.
        if "source_archive" in group.columns:
            group = group.sort_values(["source_archive"], kind="stable")
            archives = sorted({normalize_scalar(v) for v in group["source_archive"] if normalize_scalar(v)})
        else:
            archives = []
        rep = group.iloc[0].copy()
        rep["source_archives"] = "|".join(archives)
        rep["archive_copy_count"] = int(len(group))
        rep["canonicalization_key"] = "official_hydro_id"
        rep["canonicalization_geometry_rule"] = "equivalent_archive_copy_deterministic_representative"
        rep["geometry_overlap_max_hausdorff_m"] = float(group_max_haus)
        selected_rows.append(rep)
        overlap_rows.append({
            "hydro_id": hid,
            "archive_copy_count": int(len(group)),
            "source_archives": "|".join(archives),
            "geometry_overlap_max_hausdorff_m": float(group_max_haus),
        })

    canonical = gpd.GeoDataFrame(selected_rows, geometry="geometry", crs=w.crs).reset_index(drop=True)
    canonical = canonical.drop(columns=["hydro_id_norm"], errors="ignore")
    pd.DataFrame(overlap_rows).to_csv(OUT / "hydro_id_canonicalization_inventory.csv", index=False)
    audit = {
        "input_archive_rows": int(len(w)),
        "canonical_unique_hydro_ids": int(len(canonical)),
        "duplicate_hydro_id_groups_collapsed": int(duplicate_groups),
        "archive_rows_removed_as_overlapping_copies": int(len(w) - len(canonical)),
        "max_archive_copy_geometry_hausdorff_m": float(max_hausdorff),
        "geometry_equivalence_numerical_tolerance_m": NUMERICAL_GEOMETRY_TOL_M,
        "reported_impedance_conflicts_detected": False,
        "source_provenance_aggregated": True,
        "canonicalization_key": "official_hydro_id",
        "canonicalization_changes_reported_time": False,
        "canonicalization_changes_reported_length": False,
        "canonicalization_changes_reference_speed": False,
    }
    return canonical, audit


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    w = gpd.read_file(WATERWAYS, layer="waterways").reset_index(drop=True)
    if "reported_time" not in w.columns:
        raise RuntimeError("Canonical waterways lack reported_time")

    w, canonical_audit = canonicalize_by_hydro_id(w)
    w["travel_time_min"] = w["reported_time"].map(parse_minutes)
    if w["travel_time_min"].isna().any():
        raise RuntimeError("All canonical waterway corridors must have parseable reported_time")
    w["time_source"] = "antaq_official_network_reference_time"
    w["passenger_realized_time"] = False
    w["waiting_time_included"] = False
    w["time_role"] = "hydro_network_reference_impedance"
    w["directional_observed_time_claimed"] = False
    w["reference_impedance_semantics"] = "corridor_reference_impedance_consistent_with_length_over_vel_cional"

    out_path = OUT / "waterways_with_reference_time.gpkg"
    w.to_file(out_path, layer="waterways_reference_time", driver="GPKG")
    audit = {
        **canonical_audit,
        "segments_total": int(len(w)),
        "segments_with_reference_time": int(w["travel_time_min"].notna().sum()),
        "coverage_fraction": float(w["travel_time_min"].notna().mean()),
        "time_source": "antaq_official_network_reference_time",
        "time_role": "hydro_network_reference_impedance",
        "passenger_realized_time_claimed": False,
        "directional_observed_time_claimed": False,
        "waiting_time_included": False,
        "time_imputation_applied": False,
        "ready_for_multimodal_temporal_integration": bool(len(w) and w["travel_time_min"].notna().all()),
        "policy": (
            "Overlapping ANTAQ archive copies are canonicalized by official hydro_id only after requiring identical OD, reported length, reported time, and reference-speed attributes and geometry equivalence within a numerical reprojection tolerance. "
            "ANTAQ reported_time is used as an official corridor/network reference impedance, strongly consistent with EXTENSAO/VEL_CIONAL in the Pará audit. It is not labeled as realized or observed directional passenger travel time. Waiting time is excluded and no missing-time imputation is applied."
        ),
    }
    (OUT / "hydro_temporal_graph_reference_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
