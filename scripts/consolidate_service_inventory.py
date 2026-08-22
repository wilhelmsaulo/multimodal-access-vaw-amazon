from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.data.service_consolidation import (
    consolidate_service_frames,
    load_and_consolidate_artifact,
    normalize_manual_standard,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate official Pará service extracts.")
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts/service_inventory"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/service_inventory/services_consolidated.csv"))
    parser.add_argument("--reference-date", default="2026-08-20")
    args = parser.parse_args()

    inventory, _ = load_and_consolidate_artifact(args.artifact_dir, args.reference_date)

    deam_path = args.artifact_dir / "deam_physical_units_pa.csv"
    frames = [inventory]
    if deam_path.exists():
        deam = normalize_manual_standard(pd.read_csv(deam_path))
        frames.append(deam)
    inventory, audit = consolidate_service_frames(frames)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(args.output, index=False)

    summary = {
        "rows_total": audit.rows_total,
        "rows_by_source": audit.rows_by_source.astype(int).to_dict(),
        "rows_by_type": audit.rows_by_type.astype(int).to_dict(),
        "missing_coordinates": audit.missing_coordinates,
        "missing_capacity": audit.missing_capacity,
        "duplicate_service_ids": audit.duplicate_service_ids,
        "strict_physical_deam_layer_included": bool(deam_path.exists()),
        "output": str(args.output),
    }
    (args.output.parent / "services_consolidation_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
