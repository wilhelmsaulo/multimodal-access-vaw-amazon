from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALIGNMENT = ROOT / "artifacts" / "cnefe_osm_street_name_alignment" / "cnefe_osm_street_name_alignment.csv.gz"
DEFAULT_REGIMES = ROOT / "artifacts" / "cnefe_osm_alignment_regimes" / "cnefe_osm_alignment_regimes_audit.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "empirical_origin_cartographic_alignment"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--alignment", type=Path, default=DEFAULT_ALIGNMENT)
    p.add_argument("--regimes", type=Path, default=DEFAULT_REGIMES)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = p.parse_args()

    x = pd.read_csv(args.alignment, dtype={"origin_id": "string"}, low_memory=False)
    regimes = json.loads(args.regimes.read_text(encoding="utf-8"))

    boundary_m = float(regimes["posterior_equal_intersection_m"])
    bootstrap = regimes["bootstrap_intersection_m"]
    bic_improvement = float(regimes["bic_improvement_2_vs_1"])
    if not (bic_improvement > 0):
        raise ValueError("Two-component empirical regime is not supported by BIC")
    if int(regimes["bootstrap_valid_intersections"]) != int(regimes["bootstrap_replicates_requested"]):
        raise ValueError("Not all bootstrap replicates produced valid empirical intersections")

    nominal = x["any_nominal_match_same_municipality"].fillna(False).astype(bool)
    distance = pd.to_numeric(x["distance_to_any_same_name_osm_m"], errors="coerce")
    local_regime = nominal & distance.notna() & (distance <= boundary_m)

    x["empirical_local_cartographic_alignment"] = local_regime
    x["empirical_alignment_boundary_m"] = boundary_m
    x["alignment_boundary_role"] = "posterior-equality boundary between two fitted log-distance regimes"
    x["cartographic_alignment_policy"] = "unresolved"
    x.loc[local_regime, "cartographic_alignment_policy"] = "same_name_same_municipality_empirical_local_regime"
    x.loc[nominal & ~local_regime, "cartographic_alignment_policy"] = "same_name_same_municipality_nonlocal_regime"
    x["cartographic_alignment_interpreted_as_travel"] = False
    x["distance_converted_to_time"] = False
    x["temporal_connector_promoted"] = False

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cols = [
        "origin_id",
        "strict_full_name_match_same_municipality",
        "core_name_match_same_municipality",
        "any_nominal_match_same_municipality",
        "distance_to_any_same_name_osm_m",
        "empirical_local_cartographic_alignment",
        "empirical_alignment_boundary_m",
        "alignment_boundary_role",
        "cartographic_alignment_policy",
        "cartographic_alignment_interpreted_as_travel",
        "distance_converted_to_time",
        "temporal_connector_promoted",
    ]
    x[cols].to_csv(
        args.output_dir / "empirical_origin_cartographic_alignment.csv.gz",
        index=False,
        compression="gzip",
    )

    audit = {
        "origins_in_alignment_table": int(len(x)),
        "nominal_same_municipality_origins": int(nominal.sum()),
        "empirical_local_cartographic_alignment_origins": int(local_regime.sum()),
        "empirical_nonlocal_nominal_origins": int((nominal & ~local_regime).sum()),
        "fitted_boundary_m": boundary_m,
        "bootstrap_boundary_p05_m": float(bootstrap["p05"]),
        "bootstrap_boundary_median_m": float(bootstrap["median"]),
        "bootstrap_boundary_p95_m": float(bootstrap["p95"]),
        "bic_improvement_2_vs_1": bic_improvement,
        "boundary_is_data_derived": True,
        "boundary_is_universal_distance_cutoff": False,
        "boundary_applies_only_after_same_name_same_municipality_evidence": True,
        "cartographic_alignment_interpreted_as_travel": False,
        "distance_converted_to_time": False,
        "temporal_connector_promoted": False,
        "origin_access_temporal_connector_rule_resolved": False,
        "scientific_policy": (
            "The fitted posterior-equality boundary is adopted only to distinguish the local cartographic-alignment regime among origins that already have independent nominal agreement between official CNEFE street metadata and OSM within the same IBGE municipality. "
            "It is not a statewide proximity cutoff, is not interpreted as physical travel distance, and is not converted to time. Temporal access remains unresolved until the aligned evidence is crossed with routable topology."
        ),
    }
    (args.output_dir / "empirical_origin_cartographic_alignment_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
