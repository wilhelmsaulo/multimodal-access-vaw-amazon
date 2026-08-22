from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile

import pandas as pd

LOCALITIES_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/"
    "localidades/Localidades_do_Brasil/2022/Localidades_UFs_gpkg.zip"
)

# Published/reference snapshot used only for audit comparison. The current official
# GeoPackage is authoritative and must not be rejected merely because IBGE revised one row.
PARA_REFERENCE_CATEGORY_COUNTS = {
    "Cidade": 144,
    "Vila": 116,
    "Lugarejo": 600,
    "Núcleo Rural": 24,
    "Povoado": 1452,
    "Agrovila do PA": 93,
    "Localidades Indígenas": 879,
    "Localidades Quilombolas": 959,
    "Núcleo Urbano (AUI em 2010)": 157,
    "Outras Localidades": 413,
}
PARA_REFERENCE_TOTAL = sum(PARA_REFERENCE_CATEGORY_COUNTS.values())


@dataclass(frozen=True)
class LocalitySectorAudit:
    localities_para: int
    sectors_total: int
    sectors_with_zero_localities: int
    sectors_with_one_locality: int
    sectors_with_multiple_localities: int
    max_localities_in_sector: int


def find_para_gpkg(extracted_dir: Path) -> Path:
    candidates = sorted(extracted_dir.rglob("*.gpkg"))
    for path in candidates:
        name = path.name.upper()
        if name.startswith("PA_") or "PARA" in name:
            return path
    if len(candidates) == 27:
        pa_candidates = [p for p in candidates if any(part.upper() == "PA" for part in p.parts)]
        if len(pa_candidates) == 1:
            return pa_candidates[0]
    raise FileNotFoundError("Could not identify Pará GeoPackage in IBGE Localidades archive")


def extract_localities_archive(zip_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(output_dir)
    return find_para_gpkg(output_dir)


def read_para_localities(gpkg_path: Path):
    import geopandas as gpd

    layers = gpd.list_layers(gpkg_path)
    if layers.empty:
        raise ValueError("IBGE locality GeoPackage contains no layers")
    frame = gpd.read_file(gpkg_path, layer=layers.iloc[0]["name"])
    required = {
        "CD_UF",
        "SIGLA_UF",
        "CD_MUN",
        "NM_MUN",
        "CT_LOCALIDADE",
        "SCT_LOCALIDADE",
        "CD_LOCALIDADE",
        "NM_LOCALIDADE",
        "LAT_LOCALIDADE",
        "LONG_LOCALIDADE",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"IBGE locality file missing columns: {sorted(missing)}")
    pa = frame[frame["SIGLA_UF"].astype(str).str.upper().eq("PA")].copy()
    if len(pa) < 4_000:
        raise ValueError(f"Implausibly low number of Pará localities in official extract: {len(pa)}")

    # The current official file may contain repeated CD_LOCALIDADE values. Preserve every
    # official record and create a stable record identifier for spatial operations rather than
    # silently dropping one row. CD_LOCALIDADE remains unchanged as a source attribute.
    occurrence = pa.groupby("CD_LOCALIDADE", dropna=False).cumcount().astype(int)
    pa["LOCALITY_RECORD_ID"] = (
        pa["CD_LOCALIDADE"].astype("string").fillna("MISSING")
        + "#"
        + occurrence.astype("string")
    )
    if pa["LOCALITY_RECORD_ID"].duplicated().any():
        raise ValueError("Could not construct unique locality record identifiers")

    pa.attrs["reference_total"] = PARA_REFERENCE_TOTAL
    pa.attrs["observed_total"] = int(len(pa))
    pa.attrs["reference_total_difference"] = int(len(pa) - PARA_REFERENCE_TOTAL)
    pa.attrs["duplicate_locality_code_rows"] = int(pa["CD_LOCALIDADE"].duplicated(keep=False).sum())
    pa.attrs["duplicate_locality_code_values"] = int(
        pa.loc[pa["CD_LOCALIDADE"].duplicated(keep=False), "CD_LOCALIDADE"].nunique(dropna=True)
    )
    return pa


def spatial_join_localities_to_sectors(localities, sectors):
    import geopandas as gpd

    if localities.crs is None or sectors.crs is None:
        raise ValueError("Both localities and sectors must have CRS")
    localities = localities.to_crs(sectors.crs)
    point_cols = [
        "LOCALITY_RECORD_ID",
        "CD_LOCALIDADE",
        "NM_LOCALIDADE",
        "CT_LOCALIDADE",
        "SCT_LOCALIDADE",
        "CD_MUN",
        "NM_MUN",
        localities.geometry.name,
    ]
    sector_cols = ["CD_SETOR", "CD_MUN", "NM_MUN", "SITUACAO", sectors.geometry.name]
    joined = gpd.sjoin(
        localities[point_cols],
        sectors[sector_cols],
        how="left",
        predicate="within",
        lsuffix="locality",
        rsuffix="sector",
    )
    if joined["CD_SETOR"].isna().any():
        unresolved = joined[joined["CD_SETOR"].isna()].drop(columns=["index_sector"], errors="ignore")
        resolved = gpd.sjoin(
            unresolved[point_cols],
            sectors[sector_cols],
            how="left",
            predicate="intersects",
            lsuffix="locality",
            rsuffix="sector",
        )
        resolved = resolved.sort_values(["LOCALITY_RECORD_ID", "CD_SETOR"]).drop_duplicates(
            "LOCALITY_RECORD_ID", keep="first"
        )
        joined = joined[joined["CD_SETOR"].notna()].copy()
        joined = pd.concat([joined, resolved], ignore_index=True)
    if joined["CD_SETOR"].isna().any():
        raise ValueError("Some IBGE localities could not be assigned to a census sector")
    if joined["LOCALITY_RECORD_ID"].duplicated().any():
        raise ValueError("A locality record was assigned to more than one sector")
    return gpd.GeoDataFrame(joined, geometry=localities.geometry.name, crs=sectors.crs)


def audit_localities_per_sector(joined, sectors) -> tuple[pd.DataFrame, LocalitySectorAudit]:
    counts = joined.groupby("CD_SETOR").size().rename("locality_count")
    base_cols = ["CD_SETOR", "CD_MUN", "NM_MUN", "SITUACAO"]
    sector_audit = sectors[base_cols].drop_duplicates("CD_SETOR").merge(
        counts, on="CD_SETOR", how="left", validate="one_to_one"
    )
    sector_audit["locality_count"] = sector_audit["locality_count"].fillna(0).astype(int)
    audit = LocalitySectorAudit(
        localities_para=int(len(joined)),
        sectors_total=int(len(sector_audit)),
        sectors_with_zero_localities=int((sector_audit["locality_count"] == 0).sum()),
        sectors_with_one_locality=int((sector_audit["locality_count"] == 1).sum()),
        sectors_with_multiple_localities=int((sector_audit["locality_count"] > 1).sum()),
        max_localities_in_sector=int(sector_audit["locality_count"].max()),
    )
    return sector_audit, audit
