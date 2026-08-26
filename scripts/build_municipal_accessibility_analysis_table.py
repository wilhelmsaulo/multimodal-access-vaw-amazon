from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


ENDPOINTS = ("lower_sensitivity_envelope", "upper_sensitivity_envelope")


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def build_analysis_table(envelopes: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    required = {
        "municipality_code",
        "municipality_name",
        "female_population",
        "female_population_coverage_fraction",
        "service_type",
        "scenario",
        *ENDPOINTS,
    }
    if missing := required - set(envelopes.columns):
        raise ValueError(f"Envelope table missing columns: {sorted(missing)}")

    keys = ["municipality_code", "municipality_name"]
    municipal = envelopes[
        keys + ["female_population", "female_population_coverage_fraction"]
    ].drop_duplicates()
    if municipal["municipality_code"].duplicated().any():
        raise ValueError("Municipal population or coverage values are not unique")

    long = envelopes[keys + ["service_type", "scenario", *ENDPOINTS]].copy()
    long["feature"] = (
        "e2sfca__"
        + long["service_type"].map(_slug)
        + "__"
        + long["scenario"].map(_slug)
    )
    if long.duplicated(keys + ["feature"]).any():
        raise ValueError("Duplicate municipality/service/specification rows")

    pieces = [municipal.set_index(keys)]
    for endpoint in ENDPOINTS:
        suffix = "lower" if endpoint.startswith("lower") else "upper"
        wide = long.pivot(index=keys, columns="feature", values=endpoint)
        wide.columns = [f"{column}__{suffix}" for column in wide.columns]
        pieces.append(wide)

    table = pd.concat(pieces, axis=1).reset_index()
    feature_columns = sorted(column for column in table if column.startswith("e2sfca__"))
    table = table[[*keys, "female_population", "female_population_coverage_fraction", *feature_columns]]
    table = table.sort_values("municipality_code").reset_index(drop=True)

    lower = sorted(column for column in feature_columns if column.endswith("__lower"))
    upper = sorted(column for column in feature_columns if column.endswith("__upper"))
    paired = all(column.removesuffix("__lower") + "__upper" in upper for column in lower)
    audit = {
        "status": "ACCESSIBILITY_INTERVAL_INPUT_READY_STRUCTURAL_AUDIT_NOT_STARTED",
        "municipality_count": int(table["municipality_code"].nunique()),
        "row_count": int(len(table)),
        "service_type_count": int(envelopes["service_type"].nunique()),
        "specification_count": int(envelopes["scenario"].nunique()),
        "accessibility_feature_count": len(feature_columns),
        "lower_feature_count": len(lower),
        "upper_feature_count": len(upper),
        "all_endpoints_paired": paired,
        "coverage_fraction_retained": "female_population_coverage_fraction" in table,
        "contains_sociodemographic_block": False,
        "authorized_as_single_point_input": False,
        "next_gate": (
            "Audit missingness, temporal compatibility, correlation, redundancy, VIF and, "
            "if justified, PCA only after the sociodemographic and institutional blocks are versioned."
        ),
    }
    if len(table) != 144 or not paired:
        raise RuntimeError(f"Invalid analytical accessibility table: {audit}")
    return table, audit


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelopes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    envelopes = pd.read_csv(args.envelopes)
    table, audit = build_analysis_table(envelopes)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "municipal_accessibility_sensitivity_table.csv.gz"
    table.to_csv(output, index=False, compression="gzip")
    audit["sha256"] = {output.name: _sha256(output)}
    (args.output_dir / "municipal_accessibility_input_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
