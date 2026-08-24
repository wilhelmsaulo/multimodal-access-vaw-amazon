from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

PRIMARY_MOTOR_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service",
}
RESTRICTED_VALUES = {"no", "private"}


def norm(x: object) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip().lower()


def reconstruct_targets(local: pd.DataFrame, target_id_col: str, target_ids: set[str], nodes: pd.DataFrame, road_edges_path: Path, motor_ids: pd.Index) -> pd.DataFrame:
    non_ids = nodes.loc[~nodes["node_id"].isin(motor_ids), "node_id"].to_numpy(dtype=np.int64)
    non_index = {int(n): i for i, n in enumerate(non_ids)}
    n_non = len(non_ids)
    source = n_non

    boundary = np.full(n_non, np.inf)
    boundary_meta: dict[int, dict] = {}
    ri: list[int] = []
    rj: list[int] = []
    rw: list[float] = []
    pair_meta: dict[tuple[int, int], dict] = {}

    usecols = ["u", "v", "highway", "length_m", "access", "motor_vehicle"]
    for chunk in pd.read_csv(road_edges_path, usecols=lambda c: c in usecols, chunksize=500_000, low_memory=False):
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
                meta = {"length_m": w, "highway": norm(r.highway), "access": norm(r.access), "motor_vehicle": norm(r.motor_vehicle)}
                old = pair_meta.get(key)
                if old is None or w < old["length_m"]:
                    pair_meta[key] = meta
        for mask, col in ((u_non & ~v_non, "u"), (~u_non & v_non, "v")):
            if mask.any():
                for r in chunk.loc[mask].itertuples(index=False):
                    node_id = int(getattr(r, col))
                    i = non_index[node_id]
                    w = float(r.length_m)
                    if np.isfinite(w) and w >= 0 and w < boundary[i]:
                        boundary[i] = w
                        boundary_meta[i] = {"length_m": w, "highway": norm(r.highway), "access": norm(r.access), "motor_vehicle": norm(r.motor_vehicle)}

    bidx = np.flatnonzero(np.isfinite(boundary))
    rows = np.asarray(ri + bidx.tolist() + [source] * len(bidx), dtype=np.int32)
    cols = np.asarray(rj + [source] * len(bidx) + bidx.tolist(), dtype=np.int32)
    vals = np.asarray(rw + boundary[bidx].tolist() + boundary[bidx].tolist(), dtype=float)
    graph = coo_matrix((vals, (rows, cols)), shape=(n_non + 1, n_non + 1)).tocsr()
    _, pred = dijkstra(graph, directed=False, indices=source, return_predecessors=True)

    out_rows = []
    subset = local[local[target_id_col].astype(str).isin(target_ids)].copy()
    for r in subset.itertuples(index=False):
        cur = non_index[int(r.nearest_osm_node_id)]
        metas: list[dict] = []
        while cur != source:
            parent = int(pred[cur])
            if parent == -9999:
                raise RuntimeError(f"Missing predecessor for {getattr(r, target_id_col)}")
            if parent == source:
                metas.append(boundary_meta[cur])
                cur = parent
                continue
            a, b = int(non_ids[cur]), int(non_ids[parent])
            meta = pair_meta[(min(a, b), max(a, b))]
            metas.append(meta)
            cur = parent

        classes = sorted({m["highway"] for m in metas if m["highway"]})
        restricted = [m for m in metas if m["access"] in RESTRICTED_VALUES or m["motor_vehicle"] in RESTRICTED_VALUES]
        all_motorlike = bool(metas) and all(m["highway"] in PRIMARY_MOTOR_CLASSES for m in metas)
        if restricted:
            reason = "explicit_access_or_motor_vehicle_restriction"
        elif all_motorlike:
            reason = "motorlike_unrestricted_but_outside_primary_node_set_or_parallel_edge_selection"
        else:
            reason = "contains_nonprimary_nontrack_class"

        out_rows.append({
            target_id_col: str(getattr(r, target_id_col)),
            "path_highway_classes": "|".join(classes),
            "path_edge_count": len(metas),
            "path_length_m_reconstructed": float(sum(m["length_m"] for m in metas)),
            "restricted_edge_count": len(restricted),
            "all_edges_primary_motor_class": all_motorlike,
            "exclusion_reason": reason,
            "any_access_no_private": any(m["access"] in RESTRICTED_VALUES for m in metas),
            "any_motor_vehicle_no_private": any(m["motor_vehicle"] in RESTRICTED_VALUES for m in metas),
        })
    return pd.DataFrame(out_rows)


def main() -> None:
    nodes = pd.read_csv("artifacts/transport_topology/road_nodes.csv.gz", usecols=["node_id"])
    motor = pd.read_csv("artifacts/primary_motor_road_times_complete/primary_motor_edges_with_complete_times.csv.gz", usecols=["u", "v"])
    motor_ids = pd.Index(pd.unique(pd.concat([motor["u"], motor["v"]], ignore_index=True)))
    road_edges_path = Path("artifacts/transport_topology/road_edges.csv.gz")

    mixed = pd.read_csv("artifacts/mixed_aligned_local_paths/mixed_aligned_local_paths.csv.gz", dtype={"origin_id": "string"}, low_memory=False)
    origin_targets = set(mixed.loc[mixed["mixed_path_semantic_class"].eq("motor_like_local_path_but_excluded_from_primary_topology"), "origin_id"].astype(str))
    origin_local = pd.read_csv("artifacts/local_access_primary_motor_audit/origin_local_access_to_primary_motor.csv.gz", dtype={"origin_id": "string"}, low_memory=False)
    origin_out = reconstruct_targets(origin_local, "origin_id", origin_targets, nodes, road_edges_path, motor_ids)

    service_comp = pd.read_csv("artifacts/service_local_path_modal_composition/service_local_path_modal_composition.csv.gz", dtype={"service_id": "string"}, low_memory=False)
    service_targets = set(service_comp.loc[service_comp["service_local_path_evidence_class"].eq("mixed_or_other_local_osm_path"), "service_id"].astype(str))
    service_local = pd.read_csv("artifacts/service_local_access_primary_motor_audit/service_local_access_to_primary_motor.csv.gz", dtype={"service_id": "string"}, low_memory=False)
    service_out = reconstruct_targets(service_local, "service_id", service_targets, nodes, road_edges_path, motor_ids)

    outdir = Path("artifacts/nonprimary_motorlike_exclusion_reasons")
    outdir.mkdir(parents=True, exist_ok=True)
    origin_out.to_csv(outdir / "origin_motorlike_exclusion_reasons.csv.gz", index=False, compression="gzip")
    service_out.to_csv(outdir / "service_motorlike_exclusion_reasons.csv.gz", index=False, compression="gzip")

    audit = {
        "origin_motorlike_targets": int(len(origin_targets)),
        "origin_reason_counts": origin_out["exclusion_reason"].value_counts().to_dict(),
        "origin_targets_with_explicit_restriction": int((origin_out["restricted_edge_count"] > 0).sum()),
        "origin_targets_all_edges_primary_motor_class": int(origin_out["all_edges_primary_motor_class"].sum()),
        "service_motorlike_targets": int(len(service_targets)),
        "service_reason_counts": service_out["exclusion_reason"].value_counts().to_dict(),
        "service_targets_with_explicit_restriction": int((service_out["restricted_edge_count"] > 0).sum()),
        "service_targets_all_edges_primary_motor_class": int(service_out["all_edges_primary_motor_class"].sum()),
        "new_speed_assumption_used": False,
        "restricted_edges_promoted": False,
        "travel_time_assigned": False,
        "scientific_policy": (
            "Motor-like local paths are audited against the exact primary-motor inclusion rules before any temporal reuse. "
            "Residential/service/living_street labels alone do not authorize routing: any path containing access=no/private or motor_vehicle=no/private remains excluded. "
            "Unrestricted paths composed entirely of primary motor classes are separated for a subsequent topology/parallel-edge audit. No new speed or travel time is assigned here."
        ),
    }
    (outdir / "nonprimary_motorlike_exclusion_reasons_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
