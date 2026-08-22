from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

URL = "https://download.geofabrik.de/south-america/brazil/norte-latest.osm.pbf"
OUTPUT = Path("data/raw/transport/osm_roads/norte-latest.osm.pbf")
MANIFEST = Path("data/processed/transport/osm_roads_manifest.json")
MAX_BYTES = 250_000_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "multimodal-access-vaw/0.1 reproducible-research"}
    timeout = httpx.Timeout(180.0, connect=60.0, read=180.0, write=30.0, pool=30.0)
    total = 0
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        with client.stream("GET", URL) as response:
            response.raise_for_status()
            length = int(response.headers.get("content-length") or 0)
            if length and length > MAX_BYTES:
                raise RuntimeError(f"OSM extract too large: {length} bytes")
            with OUTPUT.open("wb") as f:
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise RuntimeError("OSM extract exceeded configured size limit")
                    f.write(chunk)
    if total == 0:
        raise RuntimeError("OSM road extract download is empty")
    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": "OpenStreetMap regional extract distributed by Geofabrik",
        "url": URL,
        "bytes": total,
        "sha256": sha256(OUTPUT),
        "purpose": "Primary routable terrestrial network for door-to-door accessibility; DNIT/SNV remains the official federal-road reference layer for validation.",
        "license_note": "OpenStreetMap data are subject to ODbL; attribution and licensing must be retained in publication/repository documentation.",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
