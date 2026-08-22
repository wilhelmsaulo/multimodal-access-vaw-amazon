from __future__ import annotations

import argparse
import json
import time
import unicodedata
from pathlib import Path

import httpx
import pandas as pd

REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "multimodal-access-vaw-amazon/0.1 (scientific service-location audit)"


def norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(text.lower().strip().split())


def reverse(client: httpx.Client, lat: float, lon: float) -> dict:
    r = client.get(REVERSE_URL, params={"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1, "zoom": 18})
    r.raise_for_status()
    payload = r.json()
    return payload if isinstance(payload, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=Path("data/candidates/manual_service_coordinate_candidates_2026-08-20.csv"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/service_inventory/manual_coordinate_candidate_audit.csv"))
    parser.add_argument("--audit", type=Path, default=Path("artifacts/service_inventory/manual_coordinate_candidate_audit.json"))
    args = parser.parse_args()

    df = pd.read_csv(args.candidates)
    rows = []
    with httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for _, row in df.iterrows():
            rec = row.to_dict()
            lat = float(row["latitude_candidate"])
            lon = float(row["longitude_candidate"])
            try:
                payload = reverse(client, lat, lon)
                addr = payload.get("address") or {}
                display = payload.get("display_name") or ""
                municipality = str(row["municipality_name"])
                localities = " ".join(str(addr.get(k) or "") for k in ("city", "town", "municipality", "county", "village", "city_district"))
                municipality_match = norm(municipality) in norm(localities + " " + display)
                supplied = norm(row.get("address_as_supplied"))
                returned = norm(display)
                number_tokens = [tok for tok in supplied.replace(",", " ").split() if tok.isdigit()]
                number_match = any(tok in returned.split() for tok in number_tokens) if number_tokens else False
                rec.update({
                    "reverse_display_name": display,
                    "reverse_type": payload.get("type"),
                    "reverse_category": payload.get("category"),
                    "reverse_osm_type": payload.get("osm_type"),
                    "reverse_osm_id": payload.get("osm_id"),
                    "municipality_match": municipality_match,
                    "house_number_match_if_supplied": number_match,
                    "reverse_status": "resolved",
                    "promotion_status": "manual_current-address-comparison_required" if municipality_match else "reject_wrong_municipality",
                })
            except Exception as exc:
                rec.update({
                    "reverse_status": f"request_error:{type(exc).__name__}",
                    "promotion_status": "unresolved_external_lookup",
                })
            rows.append(rec)
            time.sleep(1.05)

    out = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    audit = {
        "candidate_rows": int(len(out)),
        "reverse_resolved": int(out["reverse_status"].eq("resolved").sum()),
        "municipality_matches": int(out.get("municipality_match", pd.Series(dtype=bool)).fillna(False).sum()),
        "house_number_matches": int(out.get("house_number_match_if_supplied", pd.Series(dtype=bool)).fillna(False).sum()),
        "promotion_rule": "No manual coordinate is promoted automatically. Reverse geocoding only checks spatial plausibility; current official address/building evidence remains required.",
    }
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
