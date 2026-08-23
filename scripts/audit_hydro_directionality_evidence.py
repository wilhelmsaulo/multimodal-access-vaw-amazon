from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

SRC = Path("artifacts/hydro_temporal_graph_reference/waterways_with_reference_time.gpkg")
OUT = Path("artifacts/hydro_directionality_audit")


def norm_text(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s.strip().lower())
    return s


def route_endpoint_key(row: pd.Series) -> tuple[str, str, str, str]:
    return (
        norm_text(row.get("origin_municipality")),
        norm_text(row.get("origin_state")),
        norm_text(row.get("destination_municipality")),
        norm_text(row.get("destination_state")),
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    g = gpd.read_file(SRC, layer="waterways_reference_time").reset_index(drop=True)
    required = {
        "origin_municipality", "origin_state", "destination_municipality",
        "destination_state", "travel_time_min", "hydro_id", "geometry"
    }
    missing = required - set(g.columns)
    if missing:
        raise RuntimeError(f"Missing directionality fields: {sorted(missing)}")

    rows = []
    for i, r in g.iterrows():
        o, os, d, ds = route_endpoint_key(r)
        rows.append({
            "route_index": int(i),
            "hydro_id": r.get("hydro_id"),
            "origin_municipality": r.get("origin_municipality"),
            "origin_state": r.get("origin_state"),
            "destination_municipality": r.get("destination_municipality"),
            "destination_state": r.get("destination_state"),
            "origin_norm": o,
            "origin_state_norm": os,
            "destination_norm": d,
            "destination_state_norm": ds,
            "travel_time_min": float(r["travel_time_min"]),
            "same_endpoint_municipality": bool(o and d and o == d and os == ds),
            "has_named_origin": bool(o),
            "has_named_destination": bool(d),
        })
    df = pd.DataFrame(rows)

    key_to_indices: dict[tuple[str, str, str, str], list[int]] = {}
    for _, r in df.iterrows():
        key = (r.origin_norm, r.origin_state_norm, r.destination_norm, r.destination_state_norm)
        if all(key):
            key_to_indices.setdefault(key, []).append(int(r.route_index))

    reverse_rows = []
    reciprocal_route_indices: set[int] = set()
    reciprocal_pairs_seen: set[tuple[int, int]] = set()
    for _, r in df.iterrows():
        if not (r.origin_norm and r.origin_state_norm and r.destination_norm and r.destination_state_norm):
            continue
        rev_key = (r.destination_norm, r.destination_state_norm, r.origin_norm, r.origin_state_norm)
        for j in key_to_indices.get(rev_key, []):
            i = int(r.route_index)
            if i == j:
                continue
            pair = tuple(sorted((i, j)))
            if pair in reciprocal_pairs_seen:
                continue
            reciprocal_pairs_seen.add(pair)
            reciprocal_route_indices.update(pair)
            a = df.loc[df.route_index == pair[0]].iloc[0]
            b = df.loc[df.route_index == pair[1]].iloc[0]
            ta = float(a.travel_time_min)
            tb = float(b.travel_time_min)
            reverse_rows.append({
                "route_index_a": int(pair[0]),
                "route_index_b": int(pair[1]),
                "hydro_id_a": a.hydro_id,
                "hydro_id_b": b.hydro_id,
                "a_origin": a.origin_municipality,
                "a_destination": a.destination_municipality,
                "b_origin": b.origin_municipality,
                "b_destination": b.destination_municipality,
                "time_a_min": ta,
                "time_b_min": tb,
                "absolute_time_difference_min": abs(ta - tb),
                "relative_time_difference_vs_mean": abs(ta - tb) / ((ta + tb) / 2.0) if (ta + tb) > 0 else np.nan,
                "times_equal_within_1min": bool(abs(ta - tb) <= 1.0),
            })
    reciprocal = pd.DataFrame(reverse_rows)

    df["has_explicit_reverse_route"] = df["route_index"].isin(reciprocal_route_indices)
    df["directionality_evidence_class"] = "single_reported_origin_destination_record"
    df.loc[~(df.has_named_origin & df.has_named_destination), "directionality_evidence_class"] = "missing_named_endpoint_direction"
    df.loc[df.same_endpoint_municipality, "directionality_evidence_class"] = "same_municipality_origin_destination"
    df.loc[df.has_explicit_reverse_route, "directionality_evidence_class"] = "explicit_reciprocal_route_records"

    # Geometry ordering is NOT validated as origin->destination by this audit because
    # municipality names alone do not give an exact terminal coordinate for each route.
    geometry_order_validated = False

    df.to_csv(OUT / "hydro_route_directionality_evidence.csv", index=False)
    reciprocal.to_csv(OUT / "explicit_reciprocal_route_pairs.csv", index=False)

    rel = reciprocal["relative_time_difference_vs_mean"].dropna() if not reciprocal.empty else pd.Series(dtype=float)
    audit = {
        "official_routes_total": int(len(df)),
        "routes_with_named_origin_and_destination": int((df.has_named_origin & df.has_named_destination).sum()),
        "routes_missing_named_endpoint_direction": int((~(df.has_named_origin & df.has_named_destination)).sum()),
        "same_municipality_origin_destination_routes": int(df.same_endpoint_municipality.sum()),
        "routes_with_explicit_reverse_record": int(df.has_explicit_reverse_route.sum()),
        "explicit_reciprocal_route_pair_count": int(len(reciprocal)),
        "reciprocal_pairs_with_equal_time_within_1min": int(reciprocal["times_equal_within_1min"].sum()) if not reciprocal.empty else 0,
        "reciprocal_time_relative_difference_median": float(rel.median()) if len(rel) else None,
        "reciprocal_time_relative_difference_p95": float(rel.quantile(0.95)) if len(rel) else None,
        "reciprocal_time_relative_difference_max": float(rel.max()) if len(rel) else None,
        "geometry_vertex_order_validated_as_origin_to_destination": geometry_order_validated,
        "symmetric_time_assumption_supported_statewide": False,
        "automatic_reverse_edge_creation_supported_statewide": False,
        "directionality_resolved_for_final_routing": False,
        "next_required_step": "Validate whether canonical ANTAQ route geometry orientation corresponds to its declared origin/destination using endpoint coordinates or another official directional field; until then do not map reported origin-to-destination time onto geometry orientation or synthesize reverse travel edges.",
        "scientific_policy": (
            "Reported origin and destination labels are treated as directional evidence at route-record level. "
            "An explicit reverse record is evidence that both directions are represented, but reverse time is not assumed equal to forward time. "
            "The order of vertices in a line geometry is not assumed to encode origin-to-destination direction without endpoint validation. "
            "No reverse route, symmetric travel time, or current-based adjustment is imputed."
        ),
    }
    (OUT / "hydro_directionality_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not reciprocal.empty:
        print(reciprocal.to_string(index=False))


if __name__ == "__main__":
    main()
