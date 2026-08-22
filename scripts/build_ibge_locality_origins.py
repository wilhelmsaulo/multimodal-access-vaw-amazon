from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import httpx

from src.data.ibge_localities_2022 import (
    LOCALITIES_URL,
    audit_localities_per_sector,
    extract_localities_archive,
    read_para_localities,
    spatial_join_localities_to_sectors,
)


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=180, follow_redirects=True) as response:
        response.raise_for_status()
        with destination.open("wb") as stream:
            for chunk in response.iter_bytes():
                stream.write(chunk)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    raw_dir = root / "data" / "raw" / "ibge" / "localidades_2022"
    processed_dir = root / "data" / "processed" / "ibge"
    archive = raw_dir / "Localidades_UFs_gpkg.zip"
    extracted = raw_dir / "extracted"
    sectors_path = processed_dir / "pa_census_sectors_2022.gpkg"

    if not sectors_path.exists():
        raise FileNotFoundError("Build pa_census_sectors_2022.gpkg before locality audit")
    if not archive.exists():
        download(LOCALITIES_URL, archive)

    pa_gpkg = extract_localities_archive(archive, extracted)
    localities = read_para_localities(pa_gpkg)
    sectors = gpd.read_file(sectors_path, layer="pa_census_sectors_2022")
    joined = spatial_join_localities_to_sectors(localities, sectors)
    sector_audit, audit = audit_localities_per_sector(joined, sectors)

    joined_path = processed_dir / "pa_ibge_localities_2022_by_sector.gpkg"
    joined.to_file(joined_path, layer="pa_localities_by_sector", driver="GPKG")
    joined.drop(columns=joined.geometry.name).to_csv(
        processed_dir / "pa_ibge_localities_2022_by_sector.csv", index=False
    )
    sector_audit.to_csv(
        processed_dir / "pa_sector_locality_counts_2022.csv", index=False
    )
    audit_payload = {
        "source": "IBGE Censo Demografico 2022 - Localidades do Brasil",
        "source_url": LOCALITIES_URL,
        "localities_para": audit.localities_para,
        "sectors_total": audit.sectors_total,
        "sectors_with_zero_localities": audit.sectors_with_zero_localities,
        "sectors_with_one_locality": audit.sectors_with_one_locality,
        "sectors_with_multiple_localities": audit.sectors_with_multiple_localities,
        "max_localities_in_sector": audit.max_localities_in_sector,
        "methodological_note": (
            "Localities are candidate inhabited reference points. The audit does not yet "
            "assign full sector population to a locality when a sector contains multiple "
            "localities, and it does not use rural polygon centroids as final origins."
        ),
    }
    (processed_dir / "pa_ibge_localities_2022.audit.json").write_text(
        json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
