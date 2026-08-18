from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd
import yaml

from src.data.cnefe_origins import assign_cnefe_addresses_to_sectors, build_cnefe_sector_origins

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "cnefe_origin_rules.yml"
DEFAULT_SECTORS = ROOT / "data" / "processed" / "ibge" / "pa_census_sectors_2022.gpkg"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "ibge" / "pa_cnefe_sector_origins_2022.csv"


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=300.0, follow_redirects=True) as response:
        response.raise_for_status()
        with destination.open("wb") as stream:
            for chunk in response.iter_bytes():
                stream.write(chunk)


def _read_filtered_joined_addresses(
    archive_path: Path,
    sectors: gpd.GeoDataFrame,
    *,
    residential_species: set[str],
    accepted_quality: set[str],
    chunksize: int = 250_000,
) -> pd.DataFrame:
    joined_parts: list[pd.DataFrame] = []
    with zipfile.ZipFile(archive_path) as archive:
        csv_members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
        if not csv_members:
            raise ValueError("CNEFE coordinate archive contains no CSV member")
        member = csv_members[0]
        with archive.open(member) as stream:
            for chunk in pd.read_csv(
                stream,
                sep=";",
                dtype="string",
                usecols=["COD_ESPECIE", "LATITUDE", "LONGITUDE", "NV_GEO_COORD"],
                chunksize=chunksize,
                encoding="utf-8",
            ):
                species = chunk["COD_ESPECIE"].astype("string").str.strip()
                quality = chunk["NV_GEO_COORD"].astype("string").str.strip()
                selected = chunk[
                    species.isin(residential_species) & quality.isin(accepted_quality)
                ].copy()
                if selected.empty:
                    continue
                joined = assign_cnefe_addresses_to_sectors(
                    selected,
                    sectors,
                    latitude_col="LATITUDE",
                    longitude_col="LONGITUDE",
                    sector_id_col="CD_SETOR",
                )
                joined = pd.DataFrame(joined.drop(columns=[joined.geometry.name], errors="ignore"))
                joined = joined[joined["CD_SETOR"].notna()][
                    ["CD_SETOR", "COD_ESPECIE", "NV_GEO_COORD", "LATITUDE", "LONGITUDE"]
                ].copy()
                if len(joined):
                    joined_parts.append(joined)
    if not joined_parts:
        return pd.DataFrame(
            columns=["CD_SETOR", "COD_ESPECIE", "NV_GEO_COORD", "LATITUDE", "LONGITUDE"]
        )
    return pd.concat(joined_parts, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--sectors", type=Path, default=DEFAULT_SECTORS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    residential = {str(v) for v in cfg["rules"]["residential_species_values"]}
    accepted = {str(v) for v in cfg["rules"]["accepted_nv_geo_coord_values"]}
    if not residential or not accepted:
        raise ValueError("CNEFE origin rules are not finalized")

    sectors = gpd.read_file(args.sectors, layer="pa_census_sectors_2022")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "15_PA.zip"
        _download(cfg["source"]["coordinate_url"], archive)
        joined = _read_filtered_joined_addresses(
            archive,
            sectors,
            residential_species=residential,
            accepted_quality=accepted,
            chunksize=args.chunksize,
        )

    origins, audit = build_cnefe_sector_origins(
        joined,
        sectors,
        sector_col="CD_SETOR",
        species_col="COD_ESPECIE",
        geo_quality_col="NV_GEO_COORD",
        latitude_col="LATITUDE",
        longitude_col="LONGITUDE",
        residential_species_values=residential,
        accepted_geo_quality_values=accepted,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    origins.to_csv(args.output, index=False)

    audit_dict = {
        **audit.__dict__,
        "residential_species_values": sorted(residential),
        "accepted_nv_geo_coord_values": sorted(accepted),
        "coordinate_source_rows_audited_previously": 3_911_170,
        "method": "spatial_join_then_residential_median_anchored_observed_point",
        "raw_address_coordinates_committed": False,
    }
    args.output.with_suffix(".audit.json").write_text(
        json.dumps(audit_dict, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit_dict, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
