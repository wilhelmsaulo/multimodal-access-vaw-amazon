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
            norm(address.get(key))
            for key in ("city", "town", "municipality", "county", "village", "city_district", "suburb")
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


def geocode_queue(queue: pd.DataFrame, *, timeout: float = 30.0, delay: float = 1.1) -> pd.DataFrame:
    rows: list[dict] = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for _, row in queue.iterrows():
            record = row.to_dict()
            address = str(row.get("address_public") or "").strip()
            municipality = str(row.get("municipality_name") or "").strip()
            record.update(
                {
                    "geocoding_query": pd.NA,
                    "latitude_candidate": pd.NA,
                    "longitude_candidate": pd.NA,
                    "geocoding_source": "OpenStreetMap Nominatim",
                    "geocoding_quality": "not_attempted",
                    "geocoding_display_name": pd.NA,
                    "geocoding_osm_type": pd.NA,
                    "geocoding_osm_id": pd.NA,
                    "candidate_accepted_for_manual_validation": False,
                }
            )
            if not address or address.lower() in {"nan", "<na>"}:
                record["geocoding_quality"] = "missing_public_address"
                rows.append(record)
                continue

            query = f"{address}, {municipality}, Pará, Brasil"
            record["geocoding_query"] = query
            try:
                response = client.get(
                    NOMINATIM_URL,
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "addressdetails": 1,
                        "limit": 3,
                        "countrycodes": "br",
                    },
                )
                response.raise_for_status()
                results = response.json()
                chosen, quality = choose_candidate(results if isinstance(results, list) else [], municipality)
                record["geocoding_quality"] = quality
                if chosen is not None:
                    record["latitude_candidate"] = float(chosen["lat"])
                    record["longitude_candidate"] = float(chosen["lon"])
                    record["geocoding_display_name"] = chosen.get("display_name")
                    record["geocoding_osm_type"] = chosen.get("osm_type")
                    record["geocoding_osm_id"] = chosen.get("osm_id")
                    record["candidate_accepted_for_manual_validation"] = quality == "municipality_and_state_match"
            except Exception as exc:  # keep the audit alive; network failure is not scientific evidence
                record["geocoding_quality"] = f"request_error:{type(exc).__name__}"
            rows.append(record)
            time.sleep(delay)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate auditable geocoding candidates for unresolved public service addresses.")
    parser.add_argument("--queue", type=Path, default=Path("artifacts/service_inventory/services_geocoding_queue.csv"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/service_inventory/services_geocoded_candidates.csv"))
    parser.add_argument("--audit", type=Path, default=Path("artifacts/service_inventory/services_geocoding_audit.json"))
    args = parser.parse_args()

    queue = pd.read_csv(args.queue, low_memory=False)
    result = geocode_queue(queue)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)

    quality_counts = result["geocoding_quality"].astype("string").value_counts(dropna=False).to_dict()
    audit = {
        "rows_queue": int(len(result)),
        "rows_with_public_address": int(result["address_public"].astype("string").str.strip().notna().sum()),
        "rows_with_candidate_coordinates": int(pd.to_numeric(result["latitude_candidate"], errors="coerce").notna().sum()),
        "rows_accepted_for_manual_validation": int(result["candidate_accepted_for_manual_validation"].fillna(False).astype(bool).sum()),
        "quality_counts": {str(k): int(v) for k, v in quality_counts.items()},
        "source": "OpenStreetMap Nominatim",
        "promotion_rule": (
            "No geocoded candidate is automatically promoted into the routing inventory. "
            "Candidates must first match the expected municipality and Pará, then undergo spatial/manual validation."
        ),
    }
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
