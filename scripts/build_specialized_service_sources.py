from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx
import pandas as pd

LIGUE180_PAGE = "https://www.gov.br/mulheres/pt-br/ligue180/painel-da-rede-de-atendimento"
TJPA_DIRECTORY = "https://centralservicos.tjpa.jus.br/bv/todos.php"
TJPA_SNAPSHOT = Path("data/snapshots/tjpa_specialized_vaw_units_2026-08-20.csv")
DEAM_SNAPSHOT = Path("data/snapshots/deam_physical_units_pa_2026-08-20.csv")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_ligue180_publication(out_dir: Path, client: httpx.Client) -> dict:
    response = client.get(LIGUE180_PAGE)
    response.raise_for_status()
    html = response.text
    (out_dir / "ligue180_panel_page.html").write_text(html, encoding="utf-8")
    hrefs = [urljoin(str(response.url), h) for h in re.findall(r'href=["\']([^"\']+)', html, re.I)]
    iframes = [urljoin(str(response.url), s) for s in re.findall(r'<iframe[^>]+src=["\']([^"\']+)', html, re.I)]
    scripts = [urljoin(str(response.url), s) for s in re.findall(r'<script[^>]+src=["\']([^"\']+)', html, re.I)]
    resource_candidates = []
    for url in hrefs + iframes + scripts:
        low = url.lower()
        if any(token in low for token in ("powerbi", ".csv", ".xlsx", ".xls", ".json", "tableau", "painel")):
            resource_candidates.append(url)
    manifest = {
        "source": "Ministério das Mulheres - Painel da Rede de Atendimento",
        "page_url": LIGUE180_PAGE,
        "resolved_url": str(response.url),
        "http_status": response.status_code,
        "page_sha256": sha256_bytes(response.content),
        "iframes": list(dict.fromkeys(iframes)),
        "candidate_resources": list(dict.fromkeys(resource_candidates)),
        "note": "Discovery metadata only; no rows are acquired until a public tabular resource is validated.",
    }
    (out_dir / "ligue180_publication_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def build_tjpa(out_dir: Path) -> dict:
    units = pd.read_csv(TJPA_SNAPSHOT, dtype=str)
    required = {"service_name", "municipality_name", "address_public", "validation_status"}
    missing = required.difference(units.columns)
    if missing:
        raise ValueError(f"TJPA snapshot missing columns: {sorted(missing)}")
    if len(units) != 9:
        raise ValueError("TJPA specialized VAW snapshot must contain 9 units")
    units["service_type"] = "specialized_justice"
    units["provider_source"] = "TJPA"
    units.to_csv(out_dir / "tjpa_specialized_vaw_units.csv", index=False)
    manifest = {
        "source": "Tribunal de Justiça do Estado do Pará - official directory and property/address records",
        "directory_url": TJPA_DIRECTORY,
        "snapshot_file": str(TJPA_SNAPSHOT),
        "snapshot_sha256": sha256_bytes(TJPA_SNAPSHOT.read_bytes()),
        "snapshot_reference_date": "2026-08-20",
        "rows_specialized_units": int(len(units)),
        "function_validation_status": "function_validated_from_official_tjpa_directory",
        "address_status": "official_building_address_resolved",
        "coordinate_status": "pending_geocoding_and_spatial_validation",
    }
    (out_dir / "tjpa_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def build_deam(out_dir: Path) -> dict:
    units = pd.read_csv(DEAM_SNAPSHOT, dtype=str)
    required = {
        "service_id", "service_name", "service_type", "provider_source", "municipality_name",
        "address_evidence_status", "validation_status"
    }
    missing = required.difference(units.columns)
    if missing:
        raise ValueError(f"DEAM snapshot missing columns: {sorted(missing)}")
    if len(units) != 21 or units["service_id"].nunique() != 21:
        raise ValueError("Strict physical DEAM snapshot must contain 21 unique units")
    if not units["service_type"].eq("specialized_security").all():
        raise ValueError("DEAM snapshot must contain only specialized_security units")
    units.to_csv(out_dir / "deam_physical_units_pa.csv", index=False)
    evidence_counts = units["address_evidence_status"].fillna("unresolved").value_counts().to_dict()
    with_address = units["address_public"].astype("string").str.strip().notna()
    manifest = {
        "source": "PCPA/SEGUP and official/institutional public sources",
        "snapshot_file": str(DEAM_SNAPSHOT),
        "snapshot_sha256": sha256_bytes(DEAM_SNAPSHOT.read_bytes()),
        "snapshot_reference_date": "2026-08-20",
        "rows_physical_deam": int(len(units)),
        "rows_with_address_candidate": int(with_address.sum()),
        "rows_without_address": int((~with_address).sum()),
        "address_evidence_counts": {str(k): int(v) for k, v in evidence_counts.items()},
        "definition": "Physical Delegacia Especializada de Atendimento à Mulher (DEAM) only.",
        "excluded_from_physical_routing_layer": ["DEAM Virtual", "Sala Lilás", "mobile/itinerant services", "generic police stations"],
        "function_validation_status": "function_validated_from_official_state_sources",
        "coordinate_status": "pending_geocoding_and_spatial_validation",
        "address_rule": (
            "Nonblank addresses are candidates with explicit provenance. Only current_official_state evidence may be described "
            "as a current official state address; legacy/institutional candidates require revalidation before routing promotion."
        ),
    }
    (out_dir / "deam_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/service_inventory"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {}
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        summary["ligue180"] = audit_ligue180_publication(args.output_dir, client)
    summary["tjpa"] = build_tjpa(args.output_dir)
    summary["deam"] = build_deam(args.output_dir)
    (args.output_dir / "specialized_sources_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
