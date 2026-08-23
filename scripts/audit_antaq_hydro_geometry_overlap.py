from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

WATERWAYS = Path("artifacts/multimodal_graph_inputs/waterways.gpkg")
OUT = Path("artifacts/antaq_hydro_geometry_overlap")
METRIC_CRS = "EPSG:5880"


def norm_id(v: object) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    w = gpd.read_file(WATERWAYS, layer="waterways").reset_index(drop=True)
    required = {"hydro_id", "source_archive", "reported_length_km", "reported_time", "reference_speed_kmh", "geometry"}
    missing = required - set(w.columns)
    if missing:
        raise RuntimeError(f"Missing provenance-aware waterways columns: {sorted(missing)}")

    w["hydro_id_norm"] = w["hydro_id"].map(norm_id)
    wm = w.to_crs(METRIC_CRS)

    rows = []
    dup_groups = 0
    identical_all = 0
    zero_hausdorff_all = 0
    max_haus = 0.0
    max_rel_len = 0.0

    for hid, idxs in w.groupby("hydro_id_norm").groups.items():
        idxs = list(idxs)
        if len(idxs) <= 1:
            continue
        dup_groups += 1
        geoms = [wm.geometry.iloc[i] for i in idxs]
        archives = [str(w.loc[i, "source_archive"]) for i in idxs]
        wkbs = [g.wkb for g in geoms]
        exact_same = len(set(wkbs)) == 1
        pair_haus = []
        pair_rel_len = []
        for a in range(len(geoms)):
            for b in range(a + 1, len(geoms)):
                ga, gb = geoms[a], geoms[b]
                h = float(ga.hausdorff_distance(gb))
                pair_haus.append(h)
                la, lb = float(ga.length), float(gb.length)
                denom = max(la, lb)
                pair_rel_len.append(abs(la - lb) / denom if denom > 0 else 0.0)
        group_max_haus = max(pair_haus) if pair_haus else 0.0
        group_max_rel_len = max(pair_rel_len) if pair_rel_len else 0.0
        if exact_same:
            identical_all += 1
        if group_max_haus == 0.0:
            zero_hausdorff_all += 1
        max_haus = max(max_haus, group_max_haus)
        max_rel_len = max(max_rel_len, group_max_rel_len)
        rows.append({
            "hydro_id": hid,
            "row_count": len(idxs),
            "archive_set": "|".join(sorted(set(archives))),
            "exact_wkb_same": exact_same,
            "max_pairwise_hausdorff_m": group_max_haus,
            "max_pairwise_relative_geometry_length_difference": group_max_rel_len,
            "reported_length_values": "|".join(sorted({str(w.loc[i, 'reported_length_km']) for i in idxs})),
            "reported_time_values": "|".join(sorted({str(w.loc[i, 'reported_time']) for i in idxs})),
            "reference_speed_values": "|".join(sorted({str(w.loc[i, 'reference_speed_kmh']) for i in idxs})),
        })

    out = pd.DataFrame(rows).sort_values(["max_pairwise_hausdorff_m", "hydro_id"], ascending=[False, True])
    out.to_csv(OUT / "hydro_id_geometry_overlap.csv", index=False)

    audit = {
        "waterway_rows_total": int(len(w)),
        "unique_hydro_ids": int(w["hydro_id_norm"].nunique()),
        "duplicate_hydro_id_groups": int(dup_groups),
        "duplicate_groups_exact_wkb_identical": int(identical_all),
        "duplicate_groups_zero_hausdorff": int(zero_hausdorff_all),
        "duplicate_groups_geometry_variant": int(dup_groups - zero_hausdorff_all),
        "max_pairwise_hausdorff_m": float(max_haus),
        "max_pairwise_relative_geometry_length_difference": float(max_rel_len),
        "reported_impedance_attributes_are_not_modified": True,
        "canonical_geometry_selection_applied": False,
        "scientific_policy": (
            "This audit compares overlapping ANTAQ archive representations sharing the same official hydro_id. "
            "It does not select a canonical geometry and does not alter reported length, time, or reference-speed fields. "
            "Canonicalization is permitted only after overlap geometry differences are quantified alongside already-confirmed attribute identity."
        ),
    }
    (OUT / "antaq_hydro_geometry_overlap_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not out.empty:
        print(out.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
