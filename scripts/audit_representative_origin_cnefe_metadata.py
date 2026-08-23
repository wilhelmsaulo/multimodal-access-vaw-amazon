from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import httpx
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "cnefe_origin_rules.yml"
DEFAULT_ORIGINS = ROOT / "data" / "processed" / "ibge" / "pa_cnefe_sector_origins_2022.csv"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "representative_origin_cnefe_metadata"

USECOLS = [
    "COD_SETOR",
    "COD_ESPECIE",
    "NV_GEO_COORD",
    "LATITUDE",
    "LONGITUDE",
    "DSC_LOCALIDADE",
    "NOM_TIPO_SEGLOGR",
    "NOM_TITULO_SEGLOGR",
    "NOM_SEGLOGR",
]


def _download(url: str, destination: Path) -> None:
    with httpx.stream("GET", url, timeout=600.0, follow_redirects=True) as response:
        response.raise_for_status()
        with destination.open("wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)


def _numeric_coordinate(values: pd.Series) -> pd.Series:
    s = values.astype("string").str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _key(sector: pd.Series, lat: pd.Series, lon: pd.Series) -> pd.Series:
    return (
        sector.astype("string").str.strip()
        + "|"
        + _numeric_coordinate(lat).round(7).astype("string")
        + "|"
        + _numeric_coordinate(lon).round(7).astype("string")
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--origins", type=Path, default=DEFAULT_ORIGINS)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--chunksize", type=int, default=250_000)
    args = p.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    url = str(cfg["source"]["full_address_metadata_url"])
    origins = pd.read_csv(args.origins, dtype={"origin_id": "string", "municipality_code": "string"}, low_memory=False)
    if "analysis_eligibility" in origins.columns:
        origins = origins[origins["analysis_eligibility"].eq("eligible")].copy()
    origins = origins[origins["latitude"].notna() & origins["longitude"].notna()].copy()
    keep = ["origin_id", "latitude", "longitude", "origin_method", "origin_validation_status"]
    if "municipality_code" in origins.columns:
        keep.append("municipality_code")
    origins = origins[keep].copy()
    origins["match_key"] = _key(origins["origin_id"], origins["latitude"], origins["longitude"])
    target_keys = set(origins["match_key"].dropna().astype(str))
    target_sectors = set(origins["origin_id"].dropna().astype("string").str.strip().astype(str))
    target_municipalities = set(origins.get("municipality_code", pd.Series(dtype="string")).dropna().astype("string").str.strip().astype(str))

    hits: list[pd.DataFrame] = []
    full_rows_scanned = 0
    eligible_full_rows = 0
    full_rows_in_target_sectors = 0
    full_rows_with_valid_coordinates = 0
    full_rows_in_target_sectors_with_valid_coordinates = 0
    full_rows_with_target_municipality_prefix = 0
    sector_length_counts: Counter[int] = Counter()
    sector_sample: list[str] = []
    unique_sector_codes: set[str] = set()

    with tempfile.TemporaryDirectory() as td:
        archive_path = Path(td) / "15_PA_full_cnefe.zip"
        _download(url, archive_path)
        with zipfile.ZipFile(archive_path) as z:
            members = [m for m in z.namelist() if m.lower().endswith(".csv")]
            if not members:
                raise RuntimeError("Full CNEFE archive has no CSV member")
            with z.open(members[0]) as stream:
                for chunk in pd.read_csv(
                    stream,
                    sep=";",
                    dtype="string",
                    usecols=USECOLS,
                    chunksize=args.chunksize,
                    encoding="utf-8",
                ):
                    full_rows_scanned += int(len(chunk))
                    chunk = chunk[
                        chunk["COD_ESPECIE"].astype("string").str.strip().eq("1")
                        & chunk["NV_GEO_COORD"].astype("string").str.strip().isin({"1", "2", "3"})
                    ].copy()
                    eligible_full_rows += int(len(chunk))
                    if chunk.empty:
                        continue

                    sector_norm = chunk["COD_SETOR"].astype("string").str.strip()
                    nonempty_sector = sector_norm[sector_norm.notna() & sector_norm.ne("")]
                    for length, count in nonempty_sector.str.len().value_counts().items():
                        sector_length_counts[int(length)] += int(count)
                    if len(sector_sample) < 10:
                        for code in nonempty_sector.drop_duplicates().astype(str):
                            if code not in sector_sample:
                                sector_sample.append(code)
                            if len(sector_sample) >= 10:
                                break
                    unique_sector_codes.update(nonempty_sector.drop_duplicates().astype(str).tolist())

                    in_target_sector = sector_norm.isin(target_sectors)
                    full_rows_in_target_sectors += int(in_target_sector.sum())
                    if target_municipalities:
                        full_rows_with_target_municipality_prefix += int(sector_norm.str[:7].isin(target_municipalities).sum())

                    lat_num = _numeric_coordinate(chunk["LATITUDE"])
                    lon_num = _numeric_coordinate(chunk["LONGITUDE"])
                    valid_coord = lat_num.between(-90, 90) & lon_num.between(-180, 180)
                    full_rows_with_valid_coordinates += int(valid_coord.sum())
                    full_rows_in_target_sectors_with_valid_coordinates += int((in_target_sector & valid_coord).sum())

                    chunk["match_key"] = _key(chunk["COD_SETOR"], chunk["LATITUDE"], chunk["LONGITUDE"])
                    sub = chunk[chunk["match_key"].isin(target_keys)].copy()
                    if len(sub):
                        hits.append(sub)

    full = pd.concat(hits, ignore_index=True) if hits else pd.DataFrame(columns=USECOLS + ["match_key"])
    meta_cols = ["DSC_LOCALIDADE", "NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "NV_GEO_COORD"]
    conflicts = 0
    for _, g in full.groupby("match_key", dropna=False):
        signatures = g[meta_cols].fillna("").astype(str).drop_duplicates()
        if len(signatures) > 1:
            conflicts += 1
    dedup = full.sort_values(["match_key", "NOM_SEGLOGR", "DSC_LOCALIDADE"], na_position="last").drop_duplicates("match_key", keep="first")

    merged = origins.merge(dedup[["match_key"] + meta_cols], on="match_key", how="left", validate="one_to_one")
    merged = merged.rename(columns={
        "DSC_LOCALIDADE": "representative_cnefe_locality",
        "NOM_TIPO_SEGLOGR": "representative_cnefe_street_type",
        "NOM_TITULO_SEGLOGR": "representative_cnefe_street_title",
        "NOM_SEGLOGR": "representative_cnefe_street_name",
        "NV_GEO_COORD": "representative_cnefe_geo_quality",
    })
    merged["full_cnefe_metadata_match"] = merged["representative_cnefe_geo_quality"].notna()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_cols = [
        "origin_id", "origin_method", "origin_validation_status",
        "representative_cnefe_locality", "representative_cnefe_street_type",
        "representative_cnefe_street_title", "representative_cnefe_street_name",
        "representative_cnefe_geo_quality", "full_cnefe_metadata_match",
    ]
    merged[out_cols].to_csv(args.output_dir / "representative_origin_cnefe_metadata.csv.gz", index=False, compression="gzip")

    matched = int(merged["full_cnefe_metadata_match"].sum())
    named = int(merged["representative_cnefe_street_name"].fillna("").astype(str).str.strip().ne("").sum())
    target_origin_lengths = {str(int(k)): int(v) for k, v in origins["origin_id"].astype("string").str.len().value_counts().sort_index().items()}
    full_length_dict = {str(k): int(v) for k, v in sorted(sector_length_counts.items())}
    audit = {
        "origin_count": int(len(origins)),
        "target_origin_sector_code_length_counts": target_origin_lengths,
        "target_origin_sector_code_sample": sorted(origins["origin_id"].astype(str).drop_duplicates().head(10).tolist()),
        "full_cnefe_rows_scanned": full_rows_scanned,
        "eligible_full_cnefe_residential_rows": eligible_full_rows,
        "full_cnefe_unique_nonempty_sector_codes": int(len(unique_sector_codes)),
        "full_cnefe_sector_code_length_counts": full_length_dict,
        "full_cnefe_sector_code_sample": sector_sample,
        "full_cnefe_rows_with_target_municipality_prefix": full_rows_with_target_municipality_prefix,
        "full_cnefe_rows_in_target_sectors": full_rows_in_target_sectors,
        "full_cnefe_rows_with_valid_coordinates_after_decimal_normalization": full_rows_with_valid_coordinates,
        "full_cnefe_rows_in_target_sectors_with_valid_coordinates": full_rows_in_target_sectors_with_valid_coordinates,
        "full_cnefe_metadata_matches": matched,
        "full_cnefe_metadata_match_fraction": float(matched / len(origins)) if len(origins) else None,
        "matched_origins_with_nonempty_street_name": named,
        "coordinate_metadata_groups_with_conflicting_street_or_locality": int(conflicts),
        "matching_key": "COD_SETOR + numeric latitude/longitude rounded to 7 decimals after decimal-separator normalization",
        "decimal_separator_normalization_applied": True,
        "origin_coordinates_changed": False,
        "address_number_published": False,
        "raw_full_cnefe_rows_published": False,
        "access_connector_promoted": False,
        "scientific_policy": (
            "The full official CNEFE file is used only to diagnose and recover street/locality metadata for the already-selected representative origin coordinate. "
            "Sector-code compatibility is audited explicitly before any join is trusted. Decimal separators are normalized for comparison only; coordinates are not altered. "
            "No address number or raw residential microdata are published, and no connector or travel time is promoted from this audit."
        ),
    }
    (args.output_dir / "representative_origin_cnefe_metadata_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
