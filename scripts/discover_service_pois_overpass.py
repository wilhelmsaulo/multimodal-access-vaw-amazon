from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

import httpx
import pandas as pd

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "multimodal-access-vaw-amazon/0.1 (scientific service-location audit)"


def norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(text.lower().strip().split())


def regex_escape(value: str) -> str:
    return re.escape(value).replace("\\ ", " ")


def aliases_for(row: pd.Series) -> list[str]:
    service_type = str(row.get("service_type") or "").strip()
    municipality = norm(row.get("municipality_name"))
    service_name = str(row.get("service_name") or "").strip()
    aliases: list[str] = []

    if service_type == "specialized_justice":
        specific = {
            "belem": ["Fórum Criminal Des. Romão Amoedo Neto", "Fórum Criminal Desembargador Romão Amoedo Neto"],
            "ananindeua": ["Casa da Mulher Brasileira de Ananindeua", "Casa da Mulher Brasileira"],
            "castanhal": ["Fórum Des. João Bento de Souza", "Fórum Desembargador João Bento de Souza"],
            "maraba": ["Fórum Juiz José Elias Monteiro Lopes"],
            "santarem": ["Fórum de Santarém", "Fórum Desembargador Ernesto Alencar de Vasconcelos Chaves"],
        }
        aliases.extend(specific.get(municipality, []))
    elif service_type == "specialized_security":
        specific = {
            "ananindeua": ["Casa da Mulher Brasileira de Ananindeua", "Casa da Mulher Brasileira"],
            "canaa dos carajas": ["Complexo da Polícia Civil"],
            "redencao": ["Complexo da Polícia Civil"],
        }
        aliases.extend(specific.get(municipality, []))
        aliases.extend(["Delegacia Especializada de Atendimento à Mulher", "DEAM", "Delegacia da Mulher", "ParáPaz Mulher"])
    elif service_type == "creas":
        if municipality == "maraba":
            aliases.extend(["CREAS Nova Marabá", "CREAS"])
        elif municipality == "monte alegre":
            aliases.extend(["CREAS Monte Alegre", "CREAS"])
        else:
            aliases.append("CREAS")

    if service_name and service_name.lower() not in {"nan", "<na>"}:
        aliases.append(service_name)

    seen: set[str] = set()
    out: list[str] = []
    for alias in aliases:
        key = norm(alias)
        if key and key not in seen:
            seen.add(key)
            out.append(alias)
    return out


def build_query(municipality: str, aliases: list[str]) -> str:
    pattern = "|".join(regex_escape(alias) for alias in aliases)
    # Search administrative areas named after the municipality, restricted to Pará by ISO tag where available.
    return f'''[out:json][timeout:40];
area["boundary"="administrative"]["name"="{municipality}"]->.a;
(
  nwr(area.a)["name"~"({pattern})",i];
  nwr(area.a)["official_name"~"({pattern})",i];
  nwr(area.a)["short_name"~"({pattern})",i];
);
out center tags;'''


def request_overpass(client: httpx.Client, query: str) -> tuple[list[dict], str]:
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            response = client.post(url, data={"data": query})
            response.raise_for_status()
            payload = response.json()
            elements = payload.get("elements", []) if isinstance(payload, dict) else []
            return elements if isinstance(elements, list) else [], url
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return [], OVERPASS_URLS[0]


def element_point(element: dict) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None, None


def discover(queue: pd.DataFrame, delay: float = 1.0) -> pd.DataFrame:
    rows: list[dict] = []
    with httpx.Client(timeout=60.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for _, row in queue.iterrows():
            municipality = str(row.get("municipality_name") or "").strip()
            aliases = aliases_for(row)
            if not municipality or not aliases:
                continue
            query = build_query(municipality, aliases)
            try:
                elements, endpoint = request_overpass(client, query)
                for element in elements:
                    lat, lon = element_point(element)
                    tags = element.get("tags") or {}
                    rows.append({
                        "service_id": row.get("service_id"),
                        "service_name": row.get("service_name"),
                        "service_type": row.get("service_type"),
                        "municipality_name": municipality,
                        "address_public": row.get("address_public"),
                        "overpass_aliases": " | ".join(aliases),
                        "osm_element_type": element.get("type"),
                        "osm_element_id": element.get("id"),
                        "osm_name": tags.get("name"),
                        "osm_official_name": tags.get("official_name"),
                        "osm_short_name": tags.get("short_name"),
                        "osm_amenity": tags.get("amenity"),
                        "osm_office": tags.get("office"),
                        "osm_addr_street": tags.get("addr:street"),
                        "osm_addr_housenumber": tags.get("addr:housenumber"),
                        "osm_addr_postcode": tags.get("addr:postcode"),
                        "latitude_candidate": lat,
                        "longitude_candidate": lon,
                        "overpass_endpoint": endpoint,
                        "promotion_status": "manual_validation_required",
                    })
            except Exception as exc:
                rows.append({
                    "service_id": row.get("service_id"),
                    "service_name": row.get("service_name"),
                    "service_type": row.get("service_type"),
                    "municipality_name": municipality,
                    "address_public": row.get("address_public"),
                    "overpass_aliases": " | ".join(aliases),
                    "promotion_status": f"request_error:{type(exc).__name__}",
                })
            time.sleep(delay)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover named OSM POIs for unresolved public services using Overpass.")
    parser.add_argument("--queue", type=Path, default=Path("artifacts/service_inventory/services_geocoding_queue.csv"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/service_inventory/services_overpass_poi_candidates.csv"))
    parser.add_argument("--audit", type=Path, default=Path("artifacts/service_inventory/services_overpass_poi_audit.json"))
    args = parser.parse_args()

    queue = pd.read_csv(args.queue, low_memory=False)
    result = discover(queue)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)

    valid_coords = pd.to_numeric(result.get("latitude_candidate"), errors="coerce").notna() if len(result) else pd.Series(dtype=bool)
    audit = {
        "queue_rows": int(len(queue)),
        "candidate_rows": int(len(result)),
        "candidate_rows_with_coordinates": int(valid_coords.sum()) if len(result) else 0,
        "distinct_services_with_coordinate_candidates": int(result.loc[valid_coords, "service_id"].astype("string").nunique()) if len(result) else 0,
        "source": "OpenStreetMap Overpass API",
        "promotion_rule": "Discovery only. Exact institution/function, address/provenance and municipality containment must be checked before routing promotion.",
    }
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
