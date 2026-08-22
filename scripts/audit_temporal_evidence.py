from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

TEMPORAL_TOKENS = (
    "speed", "veloc", "tempo", "time", "dur", "hora", "hour", "minute", "minuto",
    "schedule", "freq", "frequ", "wait", "espera", "travel", "viagem", "operac",
)


def _parse_maxspeed_kmh(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    # Reject compound/conditional values at this stage; they require explicit parsing rules.
    if any(tok in text for tok in (";", "@", "signals", "walk", "none", "variable")):
        return None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(km/?h|kmh|kph)?\s*", text)
    if m:
        return float(m.group(1))
    mph = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*mph\s*", text)
    if mph:
        return float(mph.group(1)) * 1.609344
    return None


def _layer_evidence(path: Path, layer: str) -> dict[str, object]:
    g = gpd.read_file(path, layer=layer)
    cols = [str(c) for c in g.columns if c != "geometry"]
    candidate_cols = [c for c in cols if any(t in c.lower() for t in TEMPORAL_TOKENS)]
    evidence = {}
    for c in candidate_cols:
        s = g[c]
        nonnull = int(s.notna().sum())
        if nonnull:
            vals = s.dropna().astype(str)
            evidence[c] = {
                "nonnull": nonnull,
                "coverage_fraction": nonnull / len(g) if len(g) else 0.0,
                "sample_values": vals.drop_duplicates().head(10).tolist(),
            }
    return {
        "features": int(len(g)),
        "columns": cols,
        "temporal_candidate_columns": evidence,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--topology-dir", type=Path, default=Path("artifacts/transport_topology"))
    p.add_argument("--graph-inputs", type=Path, default=Path("artifacts/multimodal_graph_inputs"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/temporal_evidence_audit"))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    edges = pd.read_csv(args.topology_dir / "road_edges.csv.gz", low_memory=False)
    raw = edges.get("maxspeed_raw", pd.Series(index=edges.index, dtype="object"))
    parsed = raw.map(_parse_maxspeed_kmh)
    observed_raw = int(raw.notna().sum())
    parsed_count = int(parsed.notna().sum())
    parsed_length = float(edges.loc[parsed.notna(), "length_m"].sum()) if parsed_count else 0.0
    total_length = float(pd.to_numeric(edges["length_m"], errors="coerce").fillna(0).sum())

    road = {
        "edges": int(len(edges)),
        "edges_with_maxspeed_raw": observed_raw,
        "raw_edge_coverage_fraction": observed_raw / len(edges) if len(edges) else 0.0,
        "edges_with_unambiguous_numeric_maxspeed": parsed_count,
        "numeric_edge_coverage_fraction": parsed_count / len(edges) if len(edges) else 0.0,
        "numeric_length_coverage_fraction": parsed_length / total_length if total_length else 0.0,
        "parsed_kmh_summary": {
            "min": float(parsed.min()) if parsed_count else None,
            "median": float(parsed.median()) if parsed_count else None,
            "p95": float(parsed.quantile(0.95)) if parsed_count else None,
            "max": float(parsed.max()) if parsed_count else None,
        },
        "raw_value_examples": raw.dropna().astype(str).drop_duplicates().head(30).tolist(),
        "policy": "Only explicit, unambiguous OSM maxspeed values are parsed here. Missing maxspeed values are not imputed and no default speed by highway class is assigned in this audit.",
    }

    layers = {}
    for layer in ("waterways", "ports", "airports"):
        path = args.graph_inputs / f"{layer}.gpkg"
        layers[layer] = _layer_evidence(path, layer)

    audit = {
        "road_temporal_evidence": road,
        "other_modal_attribute_evidence": layers,
        "decision_status": {
            "road_can_use_observed_maxspeed_for_subset": parsed_count > 0,
            "road_requires_imputation_or_external_calibration_for_complete_routing": parsed_count < len(edges),
            "waterway_time_ready": False,
            "air_time_ready": False,
            "connector_time_ready": False,
        },
        "scientific_policy": (
            "This audit inventories temporal evidence already present in source attributes. It does not invent speeds, "
            "does not convert geometric distance to time where evidence is absent, and does not infer scheduled air or river service from infrastructure alone."
        ),
        "ready_for_external_temporal_calibration": True,
        "travel_time_assigned": False,
    }
    (args.output_dir / "temporal_evidence_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
