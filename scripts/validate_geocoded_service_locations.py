from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import Point

from src.data.ibge_census2022_sectors import download_file

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "ibge_census2022_sectors.yml"
RAW_DIR = ROOT / "data" / "raw" / "ibge" / "censo2022_sector"


def norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(text.lower().strip().split())


def requested_house_number(address: object) -> str | None:
    text = "" if address is None else str(address)
    if re.search(r"\bs\s*/?\s*n\b", text, re.I):
        return None
    matches = re.findall(r"(?:^|[,\s])([0-9]{1,6})(?:[,\s]|$)", text)
    return matches[-1] if matches else None


def result_has_house_number(display: object, requested: str | None) -> bool:
    if not requested:
        return False
    return bool(re.search(rf"(?:^|\D){re.escape(requested)}(?:\D|$)", str(display or "")))


def load_municipal_boundaries() -> gpd.GeoDataFrame:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    meta = config["files"]["geometry"]
    archive = RAW_DIR / meta["filename"]
    download_file(meta["url"], archive, meta["sha256"])
    sectors = gpd.read_file(archive)
    required = {"CD_MUN", "NM_MUN"}
    missing = required.difference(sectors.columns)
    if missing:
        raise ValueError(f"IBGE sector geometry missing columns: {sorted(missing)}")
    municipalities = sectors[["CD_MUN", "NM_MUN", sectors.geometry.name]].dissolve(
        by=["CD_MUN", "NM_MUN"], as_index=False
    )
    return municipalities.to_crs(4674)


def validate(candidates: pd.DataFrame, municipalities: gpd.GeoDataFrame) -> pd.DataFrame:
    out = candidates.copy()
    lat = pd.to_numeric(out["latitude_candidate"], errors="coerce")
    lon = pd.to_numeric(out["longitude_candidate"], errors="coerce")
    out["ibge_point_in_expected_municipality"] = False
    out["ibge_matched_municipality"] = pd.NA
    out["ibge_matched_municipality_code"] = pd.NA
    out["house_number_requested"] = pd.NA
    out["house_number_present_in_geocoder_result"] = False
    out["spatial_validation_status"] = "no_candidate_coordinate"

    valid_idx = out.index[lat.notna() & lon.notna()].tolist()
    if valid_idx:
        points = gpd.GeoDataFrame(
            out.loc[valid_idx, ["service_id", "municipality_name"]].copy(),
            geometry=[Point(float(lon[i]), float(lat[i])) for i in valid_idx],
            crs=4674,
        )
        joined = gpd.sjoin(points, municipalities[["CD_MUN", "NM_MUN", "geometry"]], how="left", predicate="within")
        by_service = joined.drop_duplicates("service_id").set_index("service_id")
        for i in valid_idx:
            sid = out.at[i, "service_id"]
            if sid not in by_service.index:
                out.at[i, "spatial_validation_status"] = "outside_ibge_municipalities"
                continue
            match_name = by_service.at[sid, "NM_MUN"]
            match_code = by_service.at[sid, "CD_MUN"]
            out.at[i, "ibge_matched_municipality"] = match_name
            out.at[i, "ibge_matched_municipality_code"] = match_code
            expected = norm(out.at[i, "municipality_name"])
            observed = norm(match_name)
            same = expected == observed
            # Icoaraci is a district of Belém and is intentionally represented as municipality Belém.
            out.at[i, "ibge_point_in_expected_municipality"] = bool(same)
            out.at[i, "spatial_validation_status"] = "ibge_municipality_match" if same else "ibge_municipality_mismatch"

    for i in out.index:
        req = requested_house_number(out.at[i, "address_public"] if "address_public" in out.columns else None)
        out.at[i, "house_number_requested"] = req if req else pd.NA
        out.at[i, "house_number_present_in_geocoder_result"] = result_has_house_number(
            out.at[i, "geocoding_display_name"] if "geocoding_display_name" in out.columns else None,
            req,
        )

    municipal_ok = out["ibge_point_in_expected_municipality"].fillna(False).astype(bool)
    exact_num = out["house_number_present_in_geocoder_result"].fillna(False).astype(bool)
    out["candidate_precision_tier"] = "unresolved"
    out.loc[municipal_ok, "candidate_precision_tier"] = "municipality_validated_street_or_feature"
    out.loc[municipal_ok & exact_num, "candidate_precision_tier"] = "municipality_validated_exact_house_number"
    out["eligible_for_routing_promotion"] = False
    out["promotion_note"] = (
        "Spatial validation alone does not promote a point. Current source provenance and address precision must also be reviewed."
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=Path("artifacts/service_inventory/services_geocoded_candidates.csv"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/service_inventory/services_geocoded_spatial_validation.csv"))
    parser.add_argument("--audit", type=Path, default=Path("artifacts/service_inventory/services_geocoded_spatial_validation.audit.json"))
    args = parser.parse_args()

    candidates = pd.read_csv(args.candidates, low_memory=False)
    municipalities = load_municipal_boundaries()
    result = validate(candidates, municipalities)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    audit = {
        "rows": int(len(result)),
        "candidate_coordinates": int(pd.to_numeric(result["latitude_candidate"], errors="coerce").notna().sum()),
        "ibge_municipality_matches": int(result["ibge_point_in_expected_municipality"].fillna(False).astype(bool).sum()),
        "exact_house_number_matches": int(result["house_number_present_in_geocoder_result"].fillna(False).astype(bool).sum()),
        "precision_tiers": {str(k): int(v) for k, v in result["candidate_precision_tier"].value_counts(dropna=False).to_dict().items()},
        "auto_promoted": 0,
        "boundary_source": "official IBGE 2022 census-sector geometry dissolved by municipality",
    }
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
