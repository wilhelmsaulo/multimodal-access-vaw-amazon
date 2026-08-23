from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

SRC = Path("artifacts/hydro_temporal_graph_reference/waterways_with_reference_time.gpkg")
OUT = Path("artifacts/hydro_reference_traversal_policy")


def _norm(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.strip().lower())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    g = gpd.read_file(SRC, layer="waterways_reference_time").reset_index(drop=True)
    if len(g) != 122 or g["hydro_id"].nunique() != 122:
        raise RuntimeError("Traversal policy requires the 122 canonical official hydro_id corridors")
    if not (g["time_source"] == "antaq_official_network_reference_time").all():
        raise RuntimeError("Unexpected hydro time source")
    if g.get("passenger_realized_time", pd.Series(False, index=g.index)).fillna(False).any():
        raise RuntimeError("Reference impedance must not be labeled as realized passenger time")

    rows = g[[
        "hydro_id", "origin_municipality", "origin_state", "destination_municipality",
        "destination_state", "reported_length_km", "travel_time_min"
    ]].copy()
    rows["o"] = rows["origin_municipality"].map(_norm)
    rows["d"] = rows["destination_municipality"].map(_norm)
    rows["os"] = rows["origin_state"].map(_norm)
    rows["ds"] = rows["destination_state"].map(_norm)

    key_map: dict[tuple[str, str, str, str], list[int]] = {}
    for i, r in rows.iterrows():
        key = (r.o, r.os, r.d, r.ds)
        if all(key):
            key_map.setdefault(key, []).append(i)

    reciprocal = []
    seen: set[tuple[int, int]] = set()
    for i, r in rows.iterrows():
        if not (r.o and r.d and r.os and r.ds) or (r.o == r.d and r.os == r.ds):
            continue
        for j in key_map.get((r.d, r.ds, r.o, r.os), []):
            if i == j:
                continue
            a_id = int(float(rows.at[i, "hydro_id"]))
            b_id = int(float(rows.at[j, "hydro_id"]))
            pair = tuple(sorted((a_id, b_id)))
            if pair in seen:
                continue
            seen.add(pair)
            reciprocal.append({
                "hydro_id_a": a_id,
                "origin_a": rows.at[i, "origin_municipality"],
                "destination_a": rows.at[i, "destination_municipality"],
                "length_a_km": float(rows.at[i, "reported_length_km"]),
                "time_a_min": float(rows.at[i, "travel_time_min"]),
                "hydro_id_b": b_id,
                "origin_b": rows.at[j, "origin_municipality"],
                "destination_b": rows.at[j, "destination_municipality"],
                "length_b_km": float(rows.at[j, "reported_length_km"]),
                "time_b_min": float(rows.at[j, "travel_time_min"]),
                "same_official_hydro_id": a_id == b_id,
                "same_reported_length": abs(float(rows.at[i, "reported_length_km"]) - float(rows.at[j, "reported_length_km"])) < 1e-9,
            })

    reciprocal_df = pd.DataFrame(reciprocal)
    reciprocal_df.to_csv(OUT / "canonical_reciprocal_endpoint_corridors.csv", index=False)
    same_id = bool(reciprocal_df["same_official_hydro_id"].any()) if len(reciprocal_df) else False
    identical_length = bool(reciprocal_df["same_reported_length"].any()) if len(reciprocal_df) else False

    audit = {
        "canonical_corridors": int(len(g)),
        "canonical_unique_hydro_ids": int(g["hydro_id"].nunique()),
        "time_source": "antaq_official_network_reference_time",
        "time_role": "hydro_network_reference_impedance",
        "passenger_realized_time_claimed": False,
        "directional_observed_time_claimed": False,
        "nonself_reciprocal_endpoint_corridor_pairs": int(len(reciprocal_df)),
        "reciprocal_pairs_sharing_same_hydro_id": same_id,
        "reciprocal_pairs_with_identical_reported_length": identical_length,
        "traversal_policy": "bidirectional_symmetric_reference_impedance_per_canonical_hydro_id",
        "bidirectional_reference_traversal_authorized": True,
        "symmetric_realized_passenger_time_claimed": False,
        "synthetic_direction_specific_time_imputed": False,
        "cross_route_switching_enabled": False,
        "waiting_time_included": False,
        "hydro_traversal_policy_resolved": True,
        "scientific_policy": (
            "Each canonical ANTAQ hydro_id is treated as a navigable corridor with an official network reference impedance. "
            "Because reported TEMPO is an estimated corridor impedance strongly explained by reported length and VEL_CIONAL, "
            "the same reference impedance is available for graph traversal in either direction along that corridor. This is a "
            "network-reference modeling convention, not a claim that realized passenger travel times are directionally symmetric. "
            "Canonical corridors that name reversed municipality endpoints remain separate hydro_id geometries; they are not treated "
            "as observations of the reverse time of another corridor. Waiting/frequency remains excluded and cross-route switching "
            "is not enabled without independent transfer evidence."
        ),
    }
    (OUT / "hydro_reference_traversal_policy_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
