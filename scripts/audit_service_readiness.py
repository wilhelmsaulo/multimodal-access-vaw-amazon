from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.data.service_readiness import audit_service_readiness, build_geocoding_queue


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit readiness of consolidated services for routing/E2SFCA.")
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("artifacts/service_inventory/services_consolidated.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/service_inventory"),
    )
    args = parser.parse_args()

    inventory = pd.read_csv(args.inventory)
    readiness, audit = audit_service_readiness(inventory)
    queue = build_geocoding_queue(readiness)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    readiness.to_csv(args.output_dir / "services_readiness.csv", index=False)
    queue.to_csv(args.output_dir / "services_geocoding_queue.csv", index=False)

    summary = {
        "total_services": audit.total_services,
        "ready_for_routing": audit.ready_for_routing,
        "ready_for_e2sfca_primary": audit.ready_for_e2sfca_primary,
        "missing_coordinates": audit.missing_coordinates,
        "missing_capacity": audit.missing_capacity,
        "needs_function_validation": audit.needs_function_validation,
        "geocoding_queue_rows": int(len(queue)),
    }
    (args.output_dir / "services_readiness_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
