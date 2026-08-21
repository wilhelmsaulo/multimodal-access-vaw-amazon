from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.network.download import discover_and_download_transport_layers
from src.network.source_catalog import build_transport_source_catalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the versioned transport-layer bundle required by the multimodal router."
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/transport"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/transport"))
    parser.add_argument("--max-bytes-per-file", type=int, default=80_000_000)
    args = parser.parse_args()

    catalog = build_transport_source_catalog(args.output_dir)
    downloads = discover_and_download_transport_layers(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        max_bytes_per_file=args.max_bytes_per_file,
    )

    status = json.loads(downloads["status"].read_text(encoding="utf-8"))
    summary = {
        "catalog": {k: str(v) for k, v in catalog.items()},
        "downloads": {k: str(v) for k, v in downloads.items()},
        "transport_bundle_status": status.get("status"),
        "source_status": status.get("sources", {}),
        "scientific_policy": (
            "This step only acquires and versions transport geometries. It does not infer travel times, "
            "does not use straight-line substitutes, and does not assign unsupported modal speeds."
        ),
    }
    summary_path = args.output_dir / "transport_bundle_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
