from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "ibge_census2022_sectors.yml"
RAW_DIR = ROOT / "data" / "raw" / "ibge" / "censo2022_sector"
PROCESSED_DIR = ROOT / "data" / "processed" / "ibge"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def download_file(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha256(destination) == expected_sha256:
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    with httpx.stream("GET", url, timeout=180, follow_redirects=True) as response:
        response.raise_for_status()
        with temporary.open("wb") as stream:
            for chunk in response.iter_bytes():
                stream.write(chunk)
    observed = sha256(temporary)
    if observed != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise ValueError(
            f"SHA-256 mismatch for {destination.name}: expected {expected_sha256}, got {observed}"
        )
    temporary.replace(destination)


def acquire_inputs(config: dict[str, Any], raw_dir: Path = RAW_DIR) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    for source_id, metadata in config["files"].items():
        destination = raw_dir / metadata["filename"]
        download_file(metadata["url"], destination, metadata["sha256"])
        outputs[source_id] = destination
    return outputs


def read_pa_demography(
    archive_path: Path,
    *,
    state_code: str = "15",
    member: str = "Agregados_por_setores_demografia_BR.csv",
) -> pd.DataFrame:
    variables = ["V01006", "V01007", "V01008"] + [
        f"V{number:05d}" for number in range(1020, 1031)
    ]
    columns = ["CD_setor", *variables]
    parts: list[pd.DataFrame] = []
    with zipfile.ZipFile(archive_path) as archive, archive.open(member) as stream:
        for chunk in pd.read_csv(
            stream,
            sep=";",
            dtype="string",
            usecols=columns,
            chunksize=100_000,
            encoding="utf-8",
        ):
            selected = chunk[chunk["CD_setor"].str.startswith(state_code, na=False)].copy()
            if not selected.empty:
                parts.append(selected)
    if not parts:
        raise ValueError(f"No census sectors found for state code {state_code}")
    frame = pd.concat(parts, ignore_index=True)
    if frame["CD_setor"].duplicated().any():
        raise ValueError("Demography file contains duplicated census-sector keys")
    for column in variables:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def validate_demography(frame: pd.DataFrame) -> dict[str, int]:
    complete_sex = frame[["V01006", "V01007", "V01008"]].notna().all(axis=1)
    sex_mismatch = (
        frame.loc[complete_sex, "V01006"]
        != frame.loc[complete_sex, "V01007"] + frame.loc[complete_sex, "V01008"]
    )
    if sex_mismatch.any():
        raise ValueError(f"{int(sex_mismatch.sum())} sectors fail total = male + female")
    return {
        "rows": int(len(frame)),
        "unique_sectors": int(frame["CD_setor"].nunique()),
        "missing_total": int(frame["V01006"].isna().sum()),
        "missing_female": int(frame["V01008"].isna().sum()),
        "female_population_observed": int(frame["V01008"].sum()),
    }


def build_sector_origins(
    geometry_path: Path,
    demography: pd.DataFrame,
    output_path: Path,
) -> dict[str, Any]:
    import geopandas as gpd

    geometry = gpd.read_file(geometry_path)
    feature_count = len(geometry)
    unique_sector_count = int(geometry["CD_SETOR"].nunique())
    duplicate_features = feature_count - unique_sector_count

    non_geometry = [column for column in geometry.columns if column != geometry.geometry.name]
    conflicting = []
    for column in non_geometry:
        counts = geometry.groupby("CD_SETOR", dropna=False)[column].nunique(dropna=False)
        if (counts > 1).any():
            conflicting.append(column)
    if conflicting:
        raise ValueError(f"Conflicting attributes within multipart sectors: {conflicting}")

    sectors = geometry.dissolve(by="CD_SETOR", as_index=False, aggfunc="first")
    merged = sectors.merge(
        demography,
        left_on="CD_SETOR",
        right_on="CD_setor",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    geometry_only = merged["_merge"].eq("left_only")
    invalid_geometry_only = geometry_only & merged["v0001"].ne(0)
    if invalid_geometry_only.any():
        raise ValueError("Geometry-only sectors with nonzero basic population were found")

    for column in ["V01006", "V01007", "V01008"]:
        merged.loc[geometry_only, column] = 0

    merged["population_data_status"] = "observed"
    merged.loc[geometry_only, "population_data_status"] = "zero_population_not_in_demography"
    unavailable = merged["_merge"].eq("both") & merged["V01008"].isna()
    merged.loc[unavailable, "population_data_status"] = "female_population_unavailable"
    merged["female_population"] = merged["V01008"]
    merged["total_population"] = merged["V01006"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.drop(columns=["_merge", "CD_setor"]).to_file(
        output_path, layer="pa_census_sectors_2022", driver="GPKG"
    )

    audit = {
        "source_features": int(feature_count),
        "unique_geometry_sectors": unique_sector_count,
        "multipart_extra_features": int(duplicate_features),
        "output_sectors": int(len(merged)),
        "municipalities": int(merged["CD_MUN"].nunique()),
        "geometry_only_zero_population_sectors": int(geometry_only.sum()),
        "female_population_unavailable_sectors": int(unavailable.sum()),
        "female_population_observed": int(merged["female_population"].sum()),
        "crs": str(merged.crs),
    }
    audit_path = output_path.with_suffix(".audit.json")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


def main() -> None:
    config = load_config()
    inputs = acquire_inputs(config)
    demography = read_pa_demography(
        inputs["demography"],
        state_code=config["state_code"],
        member=config["files"]["demography"]["member"],
    )
    demographic_audit = validate_demography(demography)
    spatial_audit = build_sector_origins(
        inputs["geometry"],
        demography,
        PROCESSED_DIR / "pa_census_sectors_2022.gpkg",
    )
    print(json.dumps({"demography": demographic_audit, "spatial": spatial_audit}, indent=2))


if __name__ == "__main__":
    main()
