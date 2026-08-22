from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


def parse_numeric_maxspeed(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    # Keep only unambiguous single numeric values. Complex/lane-dependent values
    # remain outside this candidate calibration table rather than being guessed.
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        value_kmh = float(text)
        return value_kmh if 0 < value_kmh <= 160 else None
    if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:km/?h|kph|kmh)", text):
        value_kmh = float(re.search(r"\d+(?:\.\d+)?", text).group())
        return value_kmh if 0 < value_kmh <= 160 else None
    if re.fullmatch(r"\d+(?:\.\d+)?\s*mph", text):
        mph = float(re.search(r"\d+(?:\.\d+)?", text).group())
        value_kmh = mph * 1.609344
        return value_kmh if 0 < value_kmh <= 160 else None
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--edges",
        type=Path,
        default=Path("artifacts/transport_topology/road_edges.csv.gz"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/road_speed_calibration_candidates"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    edges = pd.read_csv(args.edges, low_memory=False)
    edges["length_m"] = pd.to_numeric(edges["length_m"], errors="coerce")
    edges["observed_maxspeed_kmh"] = edges["maxspeed_raw"].map(parse_numeric_maxspeed)
    edges["highway"] = edges["highway"].astype("string").fillna("<missing>")

    rows: list[dict[str, object]] = []
    for highway, group in edges.groupby("highway", dropna=False, sort=True):
        observed = group.loc[group["observed_maxspeed_kmh"].notna()].copy()
        values = observed["observed_maxspeed_kmh"].astype(float)
        total_len = float(group["length_m"].sum())
        observed_len = float(observed["length_m"].sum())
        rows.append(
            {
                "highway": str(highway),
                "edges_total": int(len(group)),
                "edges_with_observed_speed": int(len(observed)),
                "edge_observed_fraction": float(len(observed) / len(group)) if len(group) else 0.0,
                "length_total_km": total_len / 1000.0,
                "length_with_observed_speed_km": observed_len / 1000.0,
                "length_observed_fraction": observed_len / total_len if total_len > 0 else 0.0,
                "candidate_median_kmh": float(values.median()) if len(values) else np.nan,
                "observed_p25_kmh": float(values.quantile(0.25)) if len(values) else np.nan,
                "observed_p75_kmh": float(values.quantile(0.75)) if len(values) else np.nan,
                "observed_min_kmh": float(values.min()) if len(values) else np.nan,
                "observed_max_kmh": float(values.max()) if len(values) else np.nan,
                "candidate_status": "observed_class_median_candidate" if len(values) else "no_class_observation",
            }
        )

    table = pd.DataFrame(rows).sort_values(
        ["edges_total", "highway"], ascending=[False, True]
    )
    table.to_csv(args.output_dir / "road_speed_candidates_by_highway.csv", index=False)

    observed_edges = int(edges["observed_maxspeed_kmh"].notna().sum())
    classes_total = int(table["highway"].nunique())
    classes_observed = int((table["edges_with_observed_speed"] > 0).sum())
    edges_in_observed_classes = int(
        table.loc[table["edges_with_observed_speed"] > 0, "edges_total"].sum()
    )
    length_in_observed_classes_km = float(
        table.loc[table["edges_with_observed_speed"] > 0, "length_total_km"].sum()
    )
    summary = {
        "edges_total": int(len(edges)),
        "edges_with_unambiguous_observed_maxspeed": observed_edges,
        "highway_classes_total": classes_total,
        "highway_classes_with_any_observed_maxspeed": classes_observed,
        "edges_belonging_to_classes_with_any_observation": edges_in_observed_classes,
        "fraction_edges_in_classes_with_any_observation": (
            edges_in_observed_classes / len(edges) if len(edges) else 0.0
        ),
        "length_km_in_classes_with_any_observation": length_in_observed_classes_km,
        "candidate_method": (
            "For each OSM highway class, report the median of explicit, unambiguous maxspeed values. "
            "This follows the OSMnx-supported class-wise imputation concept, using the median as a robust aggregation candidate."
        ),
        "important_limitation": (
            "Posted/OSM maxspeed is a free-flow impedance proxy, not observed realized travel speed. "
            "No candidate is applied to missing edges at this stage; classes without observations remain unresolved."
        ),
        "external_method_reference": "https://osmnx.readthedocs.io/en/stable/user-reference.html#osmnx.routing.add_edge_speeds",
        "travel_time_assigned": False,
        "ready_for_road_speed_model_decision": True,
    }
    (args.output_dir / "road_speed_calibration_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(table.head(30).to_string(index=False))


if __name__ == "__main__":
    main()
