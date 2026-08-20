from __future__ import annotations

import argparse
import json
import time
import unicodedata
from pathlib import Path

import httpx
import pandas as pd

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "multimodal-access-vaw-amazon/0.1 (scientific service-location audit)"


def norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(text.lower().strip().split())


def choose_candidate(results: list[dict], expected_municipality: str) -> tuple[dict | None, str]:
    expected = norm(expected_municipality)
    for result in results:
        address = result.get("address") or {}
        state = norm(address.get("state"))
        display = norm(result.get("display_name"))
        locality_values = " ".join(
            norm(address.get(k))
            for k in ("city", "town", "municipality", "county", "village", "city_district", "suburb")
        )
        state_ok = "para" in state or ", para," in f", {display},"
        municipality_ok = expected and (expected in locality_values or expected in display)
        if state_ok and municipality_ok:
            return result, "municipality_and_state_match"
    for result in results:
        address = result.get("address") or {}
        state = norm(address.get("state"))
        display = norm(result.get("display_name"))
        if "para" in state or ", para," in f", {display},":
            return result, "state_match_only_manual_review"
    return None, "no_defensible_match"


def query_nominatim(client: httpx.Client, query: str) -> list[dict]:
    response = client.get(
        NOMINATIM_URL,
        params={"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 3, "countrycodes": "br"},
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def institution_aliases(service_type: str, municipality: str) -> list[tuple[str, str]]:
    m = norm(municipality)
    base = f"{municipality}, Pará, Brasil"

    if service_type == "specialized_security":
        specific: dict[str, list[tuple[str, str]]] = {
            "ananindeua": [
                ("exact_casa_mulher_brasileira_address", "Casa da Mulher Brasileira, Avenida Cláudio Sanders 28, Ananindeua, Pará, Brasil"),
            ],
            "canaa dos carajas": [
                ("exact_complexo_policia_civil", "Complexo da Polícia Civil, Avenida Weyne Cavalcante, Jardim das Palmeiras, Canaã dos Carajás, Pará, Brasil"),
            ],
            "redencao": [
                ("exact_complexo_policia_civil", "Complexo da Polícia Civil, Setor Buriti III, Redenção, Pará, Brasil"),
            ],
        }
        return specific.get(m, []) + [
            ("alias_deam_full", f"Delegacia Especializada de Atendimento à Mulher, {base}"),
            ("alias_deam", f"DEAM, {base}"),
            ("alias_delegacia_mulher", f"Delegacia da Mulher, {base}"),
        ]

    if service_type == "specialized_justice":
        specific = {
            "belem": [
                ("exact_forum_criminal", "Fórum Criminal Des. Romão Amoedo Neto, Rua Tomázia Perdigão 310, Cidade Velha, Belém, Pará, Brasil"),
            ],
            "ananindeua": [
                ("exact_casa_mulher_brasileira_address", "Casa da Mulher Brasileira, Avenida Cláudio Sanders 28, Ananindeua, Pará, Brasil"),
            ],
            "castanhal": [
                ("exact_forum_castanhal", "Fórum Judiciário, Avenida Presidente Vargas 2639, Centro, Castanhal, Pará, Brasil"),
            ],
        }
        return specific.get(m, [])

    if service_type == "creas":
        specific = {
            "maraba": [
                ("exact_creas_nova_maraba", "CREAS Nova Marabá, Folha 30, Quadra 01, Lote 40, Marabá, Pará, Brasil"),
            ],
            "monte alegre": [
                ("exact_creas_monte_alegre", "CREAS, Avenida Nilo Peçanha 120, Monte Alegre, Pará, Brasil"),
            ],
        }
        return specific.get(m, []) + [
            ("alias_creas_municipality", f"CREAS de {municipality}, Pará, Brasil"),
        ]
    return []


def geocode_queue(queue: pd.DataFrame, *, timeout: float = 30.0, delay: float = 1.1) -> pd.DataFrame:
    rows: list[dict] = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for _, row in queue.iterrows():
            record = row.to_dict()
            address = str(row.get("address_public") or "").strip()
            service_name = str(row.get("service_name") or "").strip()
            service_type = str(row.get("service_type") or "").strip()
            municipality = str(row.get("municipality_name") or "").strip()
            record.update({
                "geocoding_query": pd.NA,
                "geocoding_query_strategy": pd.NA,
                "latitude_candidate": pd.NA,
                "longitude_candidate": pd.NA,
                "geocoding_source": "OpenStreetMap Nominatim",
                "geocoding_quality": "not_attempted",
                "geocoding_display_name": pd.NA,
                "geocoding_osm_type": pd.NA,
                "geocoding_osm_id": pd.NA,
                "geocoding_result_type": pd.NA,
                "geocoding_result_category": pd.NA,
                "candidate_accepted_for_manual_validation": False,
            })

            strategies: list[tuple[str, str]] = institution_aliases(service_type, municipality)
            if service_name and service_name.lower() not in {"nan", "<na>"}:
                strategies.append(("official_service_name", f"{service_name}, {municipality}, Pará, Brasil"))
            if address and address.lower() not in {"nan", "<na>"}:
                strategies.append(("public_address", f"{address}, {municipality}, Pará, Brasil"))

            if not strategies:
                record["geocoding_quality"] = "no_query_available"
                rows.append(record)
                continue

            seen_queries: set[str] = set()
            try:
                best_state_only: tuple[dict, str, str] | None = None
                for strategy, query in strategies:
                    if query in seen_queries:
                        continue
                    seen_queries.add(query)
                    results = query_nominatim(client, query)
                    chosen, quality = choose_candidate(results, municipality)
                    if chosen is not None and quality == "municipality_and_state_match":
                        record.update({
                            "geocoding_query": query,
                            "geocoding_query_strategy": strategy,
                            "geocoding_quality": quality,
                            "latitude_candidate": float(chosen["lat"]),
                            "longitude_candidate": float(chosen["lon"]),
                            "geocoding_display_name": chosen.get("display_name"),
                            "geocoding_osm_type": chosen.get("osm_type"),
                            "geocoding_osm_id": chosen.get("osm_id"),
                            "geocoding_result_type": chosen.get("type"),
                            "geocoding_result_category": chosen.get("category"),
                            "candidate_accepted_for_manual_validation": True,
                        })
                        break
                    if chosen is not None and quality == "state_match_only_manual_review" and best_state_only is None:
                        best_state_only = (chosen, strategy, query)
                    time.sleep(delay)
                else:
                    if best_state_only is not None:
                        chosen, strategy, query = best_state_only
                        record.update({
                            "geocoding_query": query,
                            "geocoding_query_strategy": strategy,
                            "geocoding_quality": "state_match_only_manual_review",
                            "latitude_candidate": float(chosen["lat"]),
                            "longitude_candidate": float(chosen["lon"]),
                            "geocoding_display_name": chosen.get("display_name"),
                            "geocoding_osm_type": chosen.get("osm_type"),
                            "geocoding_osm_id": chosen.get("osm_id"),
                            "geocoding_result_type": chosen.get("type"),
                            "geocoding_result_category": chosen.get("category"),
                        })
                    else:
                        record["geocoding_quality"] = "no_defensible_match"
            except Exception as exc:
                record["geocoding_quality"] = f"request_error:{type(exc).__name__}"
            rows.append(record)
            time.sleep(delay)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate auditable geocoding candidates for unresolved public services.")
    parser.add_argument("--queue", type=Path, default=Path("artifacts/service_inventory/services_geocoding_queue.csv"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/service_inventory/services_geocoded_candidates.csv"))
    parser.add_argument("--audit", type=Path, default=Path("artifacts/service_inventory/services_geocoding_audit.json"))
    args = parser.parse_args()
    queue = pd.read_csv(args.queue, low_memory=False)
    result = geocode_queue(queue)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    audit = {
        "rows_queue": int(len(result)),
        "rows_with_public_address": int(result["address_public"].astype("string").str.strip().notna().sum()),
        "rows_with_candidate_coordinates": int(pd.to_numeric(result["latitude_candidate"], errors="coerce").notna().sum()),
        "rows_accepted_for_manual_validation": int(result["candidate_accepted_for_manual_validation"].fillna(False).astype(bool).sum()),
        "quality_counts": {str(k): int(v) for k, v in result["geocoding_quality"].astype("string").value_counts(dropna=False).to_dict().items()},
        "query_strategy_counts": {str(k): int(v) for k, v in result["geocoding_query_strategy"].astype("string").value_counts(dropna=False).to_dict().items()},
        "source": "OpenStreetMap Nominatim",
        "promotion_rule": (
            "Generic courthouse aliases are disabled. Exact institutional/address queries are preferred; "
            "no candidate is automatically promoted without municipality, IBGE containment, precision and provenance validation."
        ),
    }
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
