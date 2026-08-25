from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra


RESTRICTED_VALUES = {"no", "private"}
PEDESTRIAN_CLASSES = {"footway", "path", "pedestrian", "steps", "cycleway"}
MOTOR_LIKE_CLASSES = {
    "living_street", "motorway", "motorway_link", "primary", "primary_link",
    "residential", "secondary", "secondary_link", "service", "tertiary",
    "tertiary_link", "trunk", "trunk_link", "unclassified",
}
TRACK_CLASSES = {"track"}


def norm(v: object) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip().lower()


def main() -> None:
    local_access = pd.read_csv("artifacts/local_access_primary_motor_audit/origin_local_access_to_primary_motor.csv.gz", low_memory=False)
    modal = pd.read_csv("artifacts/local_access_path_modal_composition/local_access_path_modal_composition.csv.gz", low_memory=False)
    gated = pd.read_csv("artifacts/local_topology_empirical_node_attachments/local_topology_empirical_node_attachments.csv.gz", low_memory=False)
    nodes = pd.read_csv("artifacts/transport_topology/road_nodes.csv.gz", usecols=["node_id"])
    motor = pd.read_csv("artifacts/primary_motor_road_times_complete/primary_motor_edges_with_complete_times.csv.gz", usecols=["u", "v"])

    motor_ids = pd.Index(pd.unique(pd.concat([motor["u"], motor["v"]], ignore_index=True)))
    non_ids = nodes.loc[~nodes["node_id"].isin(motor_ids), "node_id"].to_numpy(dtype=np.int64)
    non_index = {int(n): i for i, n in enumerate(non_ids)}
    n_non = len(non_ids)
    source = n_non

    base = local_access.merge(modal, on="origin_id", how="inner", validate="one_to_one")
    base = base.merge(gated[["origin_id"]], on="origin_id", how="inner", validate="one_to_one")
    if len(base) != 693:
        raise RuntimeError(f"Expected 693 gated local-topology origins, found {len(base)}")

    target = base[(~base["path_uses_track"]) & (~base["path_exclusively_pedestrian_classes"])].copy()
    if len(target) != 286:
        raise RuntimeError(f"Expected 286 gated mixed/other local paths, found {len(target)}")

    boundary = np.full(n_non, np.inf)
    boundary_meta: list[dict | None] = [None] * n_non
    ri: list[int] = []
    rj: list[int] = []
    rw: list[float] = []
    pair_best: dict[tuple[int, int], dict] = {}
    pair_variants: dict[tuple[int, int], set[tuple[str, str, str]]] = {}

    usecols = lambda c: c in {"u", "v", "highway", "length_m", "access", "motor_vehicle"}
    for chunk in pd.read_csv("artifacts/transport_topology/road_edges.csv.gz", usecols=usecols, chunksize=500_000, low_memory=False):
        for c in ["access", "motor_vehicle"]:
            if c not in chunk.columns:
                chunk[c] = ""
        u_non = chunk["u"].isin(non_index)
        v_non = chunk["v"].isin(non_index)
        both = u_non & v_non
        if both.any():
            for r in chunk.loc[both].itertuples(index=False):
                w = float(r.length_m)
                if not np.isfinite(w) or w < 0:
                    continue
                u_id, v_id = int(r.u), int(r.v)
                ui, vi = non_index[u_id], non_index[v_id]
                ri.extend([ui, vi]); rj.extend([vi, ui]); rw.extend([w, w])
                key = (min(u_id, v_id), max(u_id, v_id))
                meta = {
                    "length_m": w,
                    "highway": norm(r.highway),
                    "access": norm(r.access),
                    "motor_vehicle": norm(r.motor_vehicle),
                }
                pair_variants.setdefault(key, set()).add((meta["highway"], meta["access"], meta["motor_vehicle"]))
                old = pair_best.get(key)
                if old is None or w < old["length_m"]:
                    pair_best[key] = meta

        for mask, col in ((u_non & ~v_non, "u"), (~u_non & v_non, "v")):
            if mask.any():
                for r in chunk.loc[mask].itertuples(index=False):
                    node_id = int(getattr(r, col))
                    i = non_index[node_id]
                    w = float(r.length_m)
                    if not np.isfinite(w) or w < 0:
                        continue
                    if w < boundary[i]:
                        boundary[i] = w
                        boundary_meta[i] = {
                            "length_m": w,
                            "highway": norm(r.highway),
                            "access": norm(r.access),
                            "motor_vehicle": norm(r.motor_vehicle),
                        }

    bidx = np.flatnonzero(np.isfinite(boundary))
    rows = np.asarray(ri + bidx.tolist() + [source] * len(bidx), dtype=np.int32)
    cols = np.asarray(rj + [source] * len(bidx) + bidx.tolist(), dtype=np.int32)
    vals = np.asarray(rw + boundary[bidx].tolist() + boundary[bidx].tolist(), dtype=float)
    graph = coo_matrix((vals, (rows, cols)), shape=(n_non + 1, n_non + 1)).tocsr()
    _, pred = dijkstra(graph, directed=False, indices=source, return_predecessors=True)

    out_rows: list[dict] = []
    for r in target.itertuples(index=False):
        cur = non_index[int(r.nearest_osm_node_id)]
        metas: list[dict] = []
        parallel_conflicts = 0
        while cur != source:
            parent = int(pred[cur])
            if parent == -9999:
                raise RuntimeError(f"Missing predecessor for connected gated origin {r.origin_id}")
            if parent == source:
                meta = boundary_meta[cur]
                if meta is None:
                    raise RuntimeError(f"Missing boundary metadata for {r.origin_id}")
                metas.append(meta)
                cur = parent
                continue
            a, b = int(non_ids[cur]), int(non_ids[parent])
            key = (min(a, b), max(a, b))
            meta = pair_best.get(key)
            if meta is None:
                raise RuntimeError(f"Missing pair metadata for {r.origin_id}: {key}")
            metas.append(meta)
            if len(pair_variants.get(key, set())) > 1:
                parallel_conflicts += 1
            cur = parent

        classes = {m["highway"] for m in metas if m["highway"]}
        restricted = [m for m in metas if m["access"] in RESTRICTED_VALUES or m["motor_vehicle"] in RESTRICTED_VALUES]
        has_ped = bool(classes & PEDESTRIAN_CLASSES)
        has_motor = bool(classes & MOTOR_LIKE_CLASSES)
        has_track = bool(classes & TRACK_CLASSES)
        unsupported = sorted(classes - PEDESTRIAN_CLASSES - MOTOR_LIKE_CLASSES - TRACK_CLASSES)

        if restricted:
            reason = "explicit_access_or_motor_vehicle_restriction"
        elif parallel_conflicts:
            reason = "parallel_edge_metadata_conflict_requires_review"
        elif has_track:
            reason = "contains_track_sensitivity_only"
        elif has_ped and has_motor and not unsupported:
            reason = "unrestricted_pedestrian_motor_mixed_path"
        elif has_motor and not has_ped and not unsupported:
            reason = "unrestricted_motorlike_path_outside_primary_topology"
        elif has_ped and not has_motor and not unsupported:
            reason = "unrestricted_pedestrian_path_unexpected_in_mixed_target"
        else:
            reason = "contains_unsupported_or_other_osm_class"

        out_rows.append({
            "origin_id": r.origin_id,
            "female_population": getattr(r, "female_population", None),
            "path_distance_m": r.local_osm_path_distance_to_primary_motor_m,
            "path_highway_classes": "|".join(sorted(classes)),
            "audit_reason": reason,
            "restricted_edge_count": int(len(restricted)),
            "parallel_conflicting_pair_count": int(parallel_conflicts),
            "has_pedestrian_class": has_ped,
            "has_motor_like_class": has_motor,
            "unsupported_classes": "|".join(unsupported),
        })

    out = pd.DataFrame(out_rows)
    outdir = Path("artifacts/gated_local_mixed_path_restrictions")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "gated_local_mixed_path_restrictions.csv.gz", index=False, compression="gzip")

    audit = {
        "gated_local_origin_count": int(len(base)),
        "mixed_other_target_count": int(len(target)),
        "reason_counts": {str(k): int(v) for k, v in out["audit_reason"].value_counts().to_dict().items()},
        "targets_with_explicit_restriction": int((out["restricted_edge_count"] > 0).sum()),
        "targets_with_parallel_edge_metadata_conflict": int((out["parallel_conflicting_pair_count"] > 0).sum()),
        "new_speed_assumption_used": False,
        "restricted_edges_promoted": False,
        "track_speed_assigned": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "The 286 gated local paths that are neither track-involved nor exclusively pedestrian are audited edge by edge before any temporal rule is considered. "
            "Explicit access=no/private or motor_vehicle=no/private restrictions block motor promotion. Parallel OSM edge pairs with conflicting highway/access metadata are flagged for review rather than silently resolved. "
            "No new motor, pedestrian, or track speed and no travel time are assigned by this audit."
        ),
    }
    (outdir / "gated_local_mixed_path_restrictions_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
