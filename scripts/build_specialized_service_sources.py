from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx

from src.data.service_inventory import fetch_tjpa_specialized_units

LIGUE180_PAGE = "https://www.gov.br/mulheres/pt-br/ligue180/painel-da-rede-de-atendimento"


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
        "note": (
            "Candidate resources are discovery metadata only. Service rows are not treated as "
            "acquired until a public tabular resource can be fetched and validated."
        ),
    }
    (out_dir / "ligue180_publication_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def build_tjpa(out_dir: Path) -> dict:
    units = fetch_tjpa_specialized_units()
    units.to_csv(out_dir / "tjpa_specialized_vaw_units.csv", index=False)
    manifest = {
        "source": "Tribunal de Justiça do Estado do Pará - diretório oficial",
        "url": "https://centralservicos.tjpa.jus.br/bv/todos.php",
        "rows_specialized_units": int(len(units)),
        "columns": [str(c) for c in units.columns],
        "function_validation_status": "function_validated_from_official_tjpa_directory",
        "location_note": (
            "The official directory validates the existence and specialized judicial function of each unit. "
            "Street address and coordinates remain separate location-validation requirements and are not inferred here."
        ),
    }
    (out_dir / "tjpa_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
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
    (args.output_dir / "specialized_sources_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
