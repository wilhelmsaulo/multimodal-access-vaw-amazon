from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from src.accessibility.coverage_uncertainty import municipal_accessibility_envelope
from src.accessibility.e2sfca import e2sfca, exponential_decay, gaussian_decay


DEFAULT_THRESHOLDS = (120.0, 240.0, 480.0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decay_parameters(threshold: float, cutoff_weight: float) -> tuple[float, float]:
    if threshold <= 0:
        raise ValueError("Thresholds must be positive")
    if not 0 < cutoff_weight < 1:
        raise ValueError("cutoff_weight must be between zero and one")
    beta = -math.log(cutoff_weight) / threshold
    sigma = threshold / math.sqrt(-2.0 * math.log(cutoff_weight))
    return beta, sigma


def run_grid(
    travel: pd.DataFrame,
    routing_origins: pd.DataFrame,
    full_origins: pd.DataFrame,
    services: pd.DataFrame,
    *,
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
    cutoff_weight: float = 0.1,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    expected_service_types = {"creas", "health", "specialized_security", "specialized_justice"}
    actual_service_types = set(services["service_type"].dropna().astype(str))
    if actual_service_types != expected_service_types:
        raise ValueError(
            f"Unexpected service types: expected={sorted(expected_service_types)}, "
            f"actual={sorted(actual_service_types)}"
        )
    if len(services) != 225 or services["service_id"].duplicated().any():
        raise ValueError("Expected 225 unique routing-ready services")
    if len(routing_origins) != 12673 or routing_origins["origin_id"].duplicated().any():
        raise ValueError("Expected 12,673 unique routing-ready origins")
    if len(full_origins) != 15743 or full_origins["origin_id"].duplicated().any():
        raise ValueError("Expected 15,743 unique audited origins")

    od = travel.copy()
    if "reachable" in od:
        reachable = od["reachable"].astype(str).str.casefold().eq("true")
        od = od.loc[reachable].copy()
    od = od.rename(columns={"total_travel_time_min": "travel_time_min"})
    required = {"scenario", "origin_id", "service_id", "travel_time_min"}
    if missing := required - set(od.columns):
        raise ValueError(f"Travel input missing columns: {sorted(missing)}")
    if set(od["scenario"].dropna().unique()) != {"reference_network"}:
        raise ValueError("Only the frozen reference_network scenario is authorized")

    envelopes: list[pd.DataFrame] = []
    ratios: list[pd.DataFrame] = []
    specifications: list[dict] = []
    maximum_conservation_error = 0.0

    origin_population = routing_origins[["origin_id", "female_population"]].copy()
    for threshold in thresholds:
        beta, sigma = _decay_parameters(float(threshold), cutoff_weight)
        for decay_name, decay, parameter_name, parameter_value in [
            ("exponential", exponential_decay(beta), "beta", beta),
            ("gaussian", gaussian_decay(sigma), "sigma", sigma),
        ]:
            specification = f"reference_network__t{int(threshold)}__{decay_name}"
            current = od.copy()
            current["scenario"] = specification
            result = e2sfca(
                current,
                routing_origins,
                services,
                time_col="travel_time_min",
                threshold_minutes=float(threshold),
                decay=decay,
                supply_mode="unit_presence",
            )
            scored = result.sector_scores.merge(
                origin_population, on="origin_id", how="left", validate="many_to_one"
            )
            realized = (
                scored.assign(weighted=lambda d: d["e2sfca_score"] * d["female_population"])
                .groupby(["scenario", "service_type"])["weighted"]
                .sum()
            )
            expected = (
                result.service_ratios.groupby(["scenario", "service_type"])["capacity"].sum()
            )
            error = float((realized - expected).abs().max())
            maximum_conservation_error = max(maximum_conservation_error, error)

            envelope = municipal_accessibility_envelope(
                result.sector_scores,
                full_origins,
                stratum_cols=("service_type", "scenario"),
            )
            envelope["threshold_minutes"] = float(threshold)
            envelope["decay_function"] = decay_name
            envelope["cutoff_weight"] = cutoff_weight
            envelope["decay_parameter_name"] = parameter_name
            envelope["decay_parameter_value"] = parameter_value
            envelopes.append(envelope)

            ratio = result.service_ratios.copy()
            ratio["threshold_minutes"] = float(threshold)
            ratio["decay_function"] = decay_name
            ratios.append(ratio)
            specifications.append(
                {
                    "scenario": specification,
                    "threshold_minutes": float(threshold),
                    "decay_function": decay_name,
                    "cutoff_weight_at_threshold": cutoff_weight,
                    "decay_parameter_name": parameter_name,
                    "decay_parameter_value": parameter_value,
                }
            )

    envelope_table = pd.concat(envelopes, ignore_index=True)
    ratio_table = pd.concat(ratios, ignore_index=True)
    audit = {
        "status": "COVERAGE_SENSITIVITY_EXECUTED_NOT_FINAL",
        "supply_mode": "unit_presence",
        "unit_supply_value": 1.0,
        "reference_network_only": True,
        "routing_ready_origins": int(len(routing_origins)),
        "full_audited_origins": int(len(full_origins)),
        "routing_ready_services": int(len(services)),
        "service_types": {
            str(k): int(v) for k, v in services["service_type"].value_counts().sort_index().items()
        },
        "specification_count": len(specifications),
        "specifications": specifications,
        "maximum_supply_conservation_error": maximum_conservation_error,
        "municipal_envelope_rows": int(len(envelope_table)),
        "all_144_municipalities_retained": int(envelope_table["municipality_code"].nunique()) == 144,
        "afua_retained": bool(envelope_table["municipality_name"].eq("Afuá").any()),
        "is_confidence_interval": False,
        "corrects_unknown_connector_competition": False,
        "publishable_as_final": False,
    }
    return envelope_table, ratio_table, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--travel", type=Path, required=True)
    parser.add_argument("--routing-origins", type=Path, required=True)
    parser.add_argument("--full-origins", type=Path, required=True)
    parser.add_argument("--services", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cutoff-weight", type=float, default=0.1)
    args = parser.parse_args()

    travel = pd.read_csv(
        args.travel, dtype={"origin_id": "string", "service_id": "string"}, low_memory=False
    )
    routing_origins = pd.read_csv(args.routing_origins, dtype={"origin_id": "string"})
    full_origins = pd.read_csv(args.full_origins, dtype={"origin_id": "string"}, low_memory=False)
    services = pd.read_csv(args.services, dtype={"service_id": "string"})
    envelope, ratios, audit = run_grid(
        travel,
        routing_origins,
        full_origins,
        services,
        cutoff_weight=args.cutoff_weight,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    envelope_path = args.output_dir / "municipal_e2sfca_coverage_envelopes.csv.gz"
    ratios_path = args.output_dir / "service_supply_demand_ratios.csv.gz"
    envelope.to_csv(envelope_path, index=False, compression="gzip")
    ratios.to_csv(ratios_path, index=False, compression="gzip")
    audit["output_sha256"] = {
        envelope_path.name: _sha256(envelope_path),
        ratios_path.name: _sha256(ratios_path),
    }
    (args.output_dir / "e2sfca_coverage_sensitivity_manifest.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
