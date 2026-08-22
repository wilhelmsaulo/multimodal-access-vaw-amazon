"""Reused with adaptation from https://github.com/wilhelmsaulo/explainable-municipal-prioritization-framework/blob/main/src/empriority/transport_accessibility/catalog.py (blob 7a7de02d2c9e3dd6bab92c5059f55dbb30ce09ce).
Authorized by the repository owner for this project; provenance retained pending final licensing audit.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# Pará envelope in SIRGAS 2000. Used only to constrain national WFS downloads;
# final clipping/validation is performed against official IBGE geometry downstream.
_PA_BBOX = "-58.95,-9.90,-46.00,2.00,EPSG:4674"

SOURCES: list[dict[str, Any]] = [
    {
        "source_id": "dnit_roads",
        "agency": "DNIT",
        "theme": "roads",
        "official_page": "https://www.gov.br/dnit/pt-br/assuntos/atlas-e-mapas/pnv-e-snv",
        "expected_formats": ["shp", "geojson", "csv"],
        "map_reference_year": 2024,
        "download_enabled": True,
        "direct_urls": [
            (
                "https://geoservicos.inde.gov.br/geoserver/DNIT/ows?"
                "service=WFS&version=1.0.0&request=GetFeature&"
                "typeName=SNV202407A&outputFormat=SHAPE-ZIP&bbox=" + _PA_BBOX
            ),
            (
                "https://geoservicos.inde.gov.br/geoserver/DNIT/ows?"
                "service=WFS&version=2.0.0&request=GetFeature&"
                "typeNames=SNV202407A&outputFormat=application/json&bbox=" + _PA_BBOX
            ),
        ],
        "direct_urls_only": True,
        "purpose": (
            "Primary official federal road-network geometry from the DNIT/INDE WFS, "
            "SNV reference 2024-07-25, spatially constrained to the Pará envelope."
        ),
    },
    {
        "source_id": "mapbiomas_state_roads",
        "agency": "MapBiomas",
        "theme": "state_roads",
        "official_page": "https://brasil.mapbiomas.org/dados-de-infraestrutura/",
        "expected_formats": ["shp"],
        "map_reference_year": 2023,
        "direct_urls": [
            "https://brasil.mapbiomas.org/wp-content/uploads/sites/4/2023/08/rodovia-estadual.zip"
        ],
        "expected_sha256": "364a070e9394a812b8eab3956c6056203decfde66d7771c679854d28d8b4fe05",
        "direct_urls_only": True,
        "purpose": "Supplementary state-road geometry; not a blocker when the primary DNIT road layer is available.",
    },
    {
        "source_id": "mapbiomas_federal_roads",
        "agency": "MapBiomas",
        "theme": "federal_roads",
        "official_page": "https://brasil.mapbiomas.org/dados-de-infraestrutura/",
        "expected_formats": ["shp"],
        "map_reference_year": 2023,
        "direct_urls": [
            "https://brasil.mapbiomas.org/wp-content/uploads/sites/4/2023/08/rodovia-federal.zip"
        ],
        "expected_sha256": "f507e9c2bdca50c1ee6814c07cd220c88e686c0aae2b88ca8baef0280d01ba94",
        "direct_urls_only": True,
        "purpose": "Supplementary federal-road geometry; not a blocker when the primary DNIT road layer is available.",
    },
    {
        "source_id": "mapbiomas_other_roads",
        "agency": "MapBiomas",
        "theme": "other_road_segments",
        "official_page": "https://brasil.mapbiomas.org/dados-de-infraestrutura/",
        "expected_formats": ["shp"],
        "map_reference_year": 2023,
        "direct_urls": [
            "https://brasil.mapbiomas.org/wp-content/uploads/sites/4/2023/08/outros-trechos.zip"
        ],
        "expected_sha256": "7df6c217fe2ea6bbfd556863fe21a426003042ad774ac7c73bf38e41d58d1585",
        "direct_urls_only": True,
        "purpose": "Supplementary other-road geometry; not a blocker when the primary DNIT road layer is available.",
    },
    {
        "source_id": "antaq_ports",
        "agency": "ANTAQ",
        "theme": "ports",
        "official_page": "https://www.gov.br/antaq/pt-br/central-de-conteudos/informacoes-geograficas",
        "expected_formats": ["shp", "kml"],
        "map_reference_year": 2025,
        "purpose": "Port facilities and authorized passenger/ferry crossing lines.",
    },
    {
        "source_id": "antaq_waterways",
        "agency": "ANTAQ",
        "theme": "waterways",
        "official_page": "https://www.gov.br/antaq/pt-br/central-de-conteudos/informacoes-geograficas",
        "expected_formats": ["shp"],
        "map_reference_year": 2022,
        "purpose": "Economically navigated inland waterways and navigation corridors.",
    },
    {
        "source_id": "decea_airports",
        "agency": "DECEA/ICA",
        "theme": "airports",
        "official_page": "https://geoaisweb.decea.gov.br/geoserver/ICA/ows?service=WFS&version=2.0.0&request=GetCapabilities",
        "expected_formats": ["shp", "geojson", "csv"],
        "map_reference_year": 2026,
        "direct_urls": [
            "https://geoaisweb.decea.gov.br/geoserver/ICA/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=ICA:airport&outputFormat=SHAPE-ZIP",
            "https://geoaisweb.decea.gov.br/geoserver/ICA/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=ICA:airport&outputFormat=application/json",
            "https://geoaisweb.decea.gov.br/geoserver/ICA/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=ICA:airport&outputFormat=SHAPE-ZIP",
        ],
        "purpose": "Operational aerodrome geometry from the official AIRAC-updated GeoAISWEB service.",
    },
    {
        "source_id": "ibge_municipal_boundaries",
        "agency": "IBGE",
        "theme": "municipal_boundaries",
        "official_page": (
            "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
            "malhas_municipais/municipio_2023/UFs/PA/PA_Municipios_2023.zip"
        ),
        "metadata_page": "https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html",
        "expected_formats": ["shp"],
        "map_reference_year": 2023,
        "expected_sha256": "0996ffd1b26928dfbd518f67339baa36fd860f50693c1c156f9b4d86fb77c7ad",
        "purpose": "Municipal boundaries and territorial reference geometry.",
    },
]


def _probe(client: httpx.Client, url: str) -> dict[str, Any]:
    try:
        response = client.get(url, follow_redirects=True)
        return {
            "status": "available" if response.is_success else "http_error",
            "http_status": response.status_code,
            "resolved_url": str(response.url),
            "content_type": response.headers.get("content-type"),
        }
    except Exception as exc:  # network diagnostics must be persisted
        return {
            "status": "unreachable",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def build_transport_source_catalog(
    output_dir: str | Path = "data/processed/transport",
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    checked_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=45.0, headers={"User-Agent": "empriority-research/0.1"}) as client:
        for source in SOURCES:
            result = dict(source)
            result.update(_probe(client, source["official_page"]))
            result["checked_at_utc"] = checked_at
            rows.append(result)
            print(source["source_id"], result["status"], result.get("http_status", ""))

    catalog_path = output / "official_transport_sources.json"
    status_path = output / "transport_source_status.json"

    catalog_path.write_text(
        json.dumps({"sources": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    status_path.write_text(
        json.dumps(
            {
                "generated_at_utc": checked_at,
                "source_count": len(rows),
                "available": sum(row["status"] == "available" for row in rows),
                "unavailable": sum(row["status"] != "available" for row in rows),
                "sources": {
                    row["source_id"]: {
                        "status": row["status"],
                        "http_status": row.get("http_status"),
                        "error": row.get("error"),
                    }
                    for row in rows
                },
                "provenance": {
                    "reference_map": "Mapa Multimodal Pará - Ministério dos Transportes",
                    "reference_map_updated": "2023-09-22",
                    "note": "Catalog retains the official sources used by the reproducible pipeline: DNIT/MapBiomas, ANTAQ, DECEA/ICA and IBGE.",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"catalog": catalog_path, "status": status_path}
