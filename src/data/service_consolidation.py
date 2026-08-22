from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import numpy as np
import pandas as pd


STANDARD_COLUMNS = [
    "service_id", "service_name", "service_type", "provider_source",
    "municipality_code", "municipality_name", "address_public", "latitude",
    "longitude", "capacity", "capacity_type", "capacity_source", "reference_date",
    "validation_status", "redistribution_status",
]


@dataclass(frozen=True)
class ConsolidationAudit:
    rows_total: int
    rows_by_source: pd.Series
    rows_by_type: pd.Series
    missing_coordinates: int
    missing_capacity: int
    duplicate_service_ids: int


def _first_existing(frame: pd.DataFrame, candidates: Iterable[str]) -> pd.Series:
    for col in candidates:
        if col in frame.columns:
            return frame[col]
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _clean_text(series: pd.Series) -> pd.Series:
    return (
        series.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
        .replace({"": pd.NA, "NAN": pd.NA, "<NA>": pd.NA})
    )


def _slug(value: object) -> str:
    text = str(value or "").upper()
    text = re.sub(r"[^A-Z0-9]+", "-", text).strip("-")
    return text or "UNKNOWN"


def normalize_cnes_candidates(frame: pd.DataFrame, reference_date: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    out = pd.DataFrame(index=frame.index)
    cnes = _first_existing(frame, ["codigo_cnes", "cnes", "CO_CNES", "codigo_estabelecimento"])
    name = _first_existing(frame, ["nome_fantasia", "nome_razao_social", "nome_empresarial", "NO_FANTASIA", "nome"])
    muni_code = _first_existing(frame, ["codigo_municipio", "codigo_municipio_ibge", "CO_MUNICIPIO_GESTOR"])
    muni_name = _first_existing(frame, ["nome_municipio", "municipio", "NO_MUNICIPIO"])
    address = _first_existing(frame, ["logradouro", "endereco", "NO_LOGRADOURO", "endereco_estabelecimento"])
    number = _first_existing(frame, ["numero_endereco", "numero", "NU_ENDERECO", "numero_estabelecimento"])
    lat = _first_existing(frame, ["latitude", "nu_latitude", "LATITUDE", "latitude_estabelecimento_decimo_grau"])
    lon = _first_existing(frame, ["longitude", "nu_longitude", "LONGITUDE", "longitude_estabelecimento_decimo_grau"])
    status = _first_existing(frame, ["validation_status"])

    out["service_id"] = [f"CNES-{_slug(v)}" for v in cnes]
    out["service_name"] = _clean_text(name)
    out["service_type"] = "health"
    out["provider_source"] = "CNES"
    out["municipality_code"] = _clean_text(muni_code)
    out["municipality_name"] = _clean_text(muni_name)
    out["address_public"] = _clean_text(address.astype("string") + ", " + number.astype("string"))
    out["latitude"] = pd.to_numeric(lat, errors="coerce")
    out["longitude"] = pd.to_numeric(lon, errors="coerce")
    out["capacity"] = np.nan
    out["capacity_type"] = pd.NA
    out["capacity_source"] = pd.NA
    out["reference_date"] = reference_date
    out["validation_status"] = status.fillna("candidate_requires_function_validation")
    out["redistribution_status"] = "review_required"
    return out[STANDARD_COLUMNS]


def apply_cnes_bed_capacity(inventory: pd.DataFrame, beds: pd.DataFrame) -> pd.DataFrame:
    if inventory.empty or beds.empty:
        return inventory.copy()
    required = {"codigo_cnes", "capacity", "capacity_type", "capacity_source"}
    missing = required.difference(beds.columns)
    if missing:
        raise ValueError(f"Bed-capacity table missing columns: {sorted(missing)}")
    out = inventory.copy()
    bedmap = beds.copy()
    bedmap["service_id"] = "CNES-" + bedmap["codigo_cnes"].astype("string").str.replace(r"\.0$", "", regex=True).map(_slug)
    bedmap = bedmap[["service_id", "capacity", "capacity_type", "capacity_source"]].drop_duplicates("service_id")
    out = out.merge(bedmap, on="service_id", how="left", suffixes=("", "_beds"), validate="one_to_one")
    health = out["service_type"].eq("health")
    for col in ["capacity", "capacity_type", "capacity_source"]:
        bed_col = f"{col}_beds"
        if col == "capacity":
            current = pd.to_numeric(out[col], errors="coerce")
            replacement = pd.to_numeric(out[bed_col], errors="coerce")
            out.loc[health & current.isna() & replacement.notna(), col] = replacement
        else:
            mask = health & out[col].isna() & out[bed_col].notna()
            out.loc[mask, col] = out.loc[mask, bed_col]
        out = out.drop(columns=[bed_col])
    return out


def normalize_tjpa(frame: pd.DataFrame, reference_date: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    out = pd.DataFrame(index=frame.index)
    name = _clean_text(_first_existing(frame, ["service_name", "name"]))
    city = _clean_text(_first_existing(frame, ["municipality_name", "city"]))
    out["service_id"] = [f"TJPA-{_slug(n)}-{_slug(c)}" for n, c in zip(name, city)]
    out["service_name"] = name
    out["service_type"] = "specialized_justice"
    out["provider_source"] = "TJPA"
    out["municipality_code"] = pd.NA
    out["municipality_name"] = city
    out["address_public"] = _clean_text(_first_existing(frame, ["address_public", "address", "endereco"]))
    out["latitude"] = pd.to_numeric(_first_existing(frame, ["latitude"]), errors="coerce")
    out["longitude"] = pd.to_numeric(_first_existing(frame, ["longitude"]), errors="coerce")
    out["capacity"] = np.nan
    out["capacity_type"] = pd.NA
    out["capacity_source"] = pd.NA
    out["reference_date"] = reference_date
    out["validation_status"] = _first_existing(frame, ["validation_status"]).fillna("official_directory_candidate")
    out["redistribution_status"] = "review_required"
    return out[STANDARD_COLUMNS]


def normalize_manual_standard(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in STANDARD_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[STANDARD_COLUMNS]


def _parse_sagi_georef(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    text = series.astype("string").str.strip().str.replace(r"\\,", ",", regex=True)
    parts = text.str.split(",", n=1, expand=True)
    if parts.shape[1] < 2:
        return pd.Series(np.nan, index=series.index), pd.Series(np.nan, index=series.index)
    return pd.to_numeric(parts[0], errors="coerce"), pd.to_numeric(parts[1], errors="coerce")


def infer_creas_units(frame: pd.DataFrame, reference_date: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    name = _first_existing(frame, ["nome", "Nome da Unidade", "Nome Unidade", "nome_unidade", "NO_UNIDADE", "Identificação da Unidade"])
    code = _first_existing(frame, ["id_equipamento", "ID CREAS", "id_creas", "codigo_unidade", "Código da Unidade", "NU_IDENTIFICADOR"])
    city = _first_existing(frame, ["cidade", "Município", "municipio", "Nome do Município", "NO_MUNICIPIO"])
    city_code = _first_existing(frame, ["ibge", "IBGE", "Código IBGE", "codigo_ibge", "Código do Município", "CODMUNICIPIO"])
    address = _first_existing(frame, ["endereco", "Endereço", "Logradouro", "NO_LOGRADOURO"])
    georef = _first_existing(frame, ["georef_location"])
    source_date = _first_existing(frame, ["data_atualizacao"])

    recognized = name.notna() | code.notna()
    if not recognized.any():
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    name, code = _clean_text(name[recognized]), code[recognized]
    city, city_code = _clean_text(city[recognized]), _clean_text(city_code[recognized])
    address, georef = _clean_text(address[recognized]), georef[recognized]
    source_date = _clean_text(source_date[recognized])
    lat, lon = _parse_sagi_georef(georef)

    out = pd.DataFrame(index=name.index)
    out["service_id"] = [f"CREAS-{_slug(c if pd.notna(c) else n)}" for c, n in zip(code, name)]
    out["service_name"] = name.fillna("CREAS")
    out["service_type"] = "creas"
    out["provider_source"] = "MDS/SAGI"
    out["municipality_code"] = city_code
    out["municipality_name"] = city
    out["address_public"] = address
    out["latitude"], out["longitude"] = lat, lon
    out["capacity"] = np.nan
    out["capacity_type"], out["capacity_source"] = pd.NA, pd.NA
    out["reference_date"] = source_date.fillna(reference_date)
    has_coords = lat.notna() & lon.notna()
    out["validation_status"] = np.where(has_coords, "official_sagi_georeference_requires_routing_validation", "official_sagi_unit_requires_geocoding")
    out["redistribution_status"] = "review_required"
    return out[STANDARD_COLUMNS]


def validate_consolidated_inventory(frame: pd.DataFrame) -> None:
    missing = set(STANDARD_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Consolidated inventory missing columns: {sorted(missing)}")
    if frame["service_id"].isna().any():
        raise ValueError("service_id cannot be missing")
    if frame["service_id"].duplicated().any():
        dup = frame.loc[frame["service_id"].duplicated(keep=False), "service_id"].tolist()
        raise ValueError(f"Duplicate service_id values: {dup[:10]}")
    cap = pd.to_numeric(frame["capacity"], errors="coerce")
    if (cap.dropna() < 0).any():
        raise ValueError("capacity cannot be negative")
    lat, lon = pd.to_numeric(frame["latitude"], errors="coerce"), pd.to_numeric(frame["longitude"], errors="coerce")
    if ((lat.dropna() < -90) | (lat.dropna() > 90)).any():
        raise ValueError("Invalid latitude")
    if ((lon.dropna() < -180) | (lon.dropna() > 180)).any():
        raise ValueError("Invalid longitude")


def consolidate_service_frames(frames: Iterable[pd.DataFrame]) -> tuple[pd.DataFrame, ConsolidationAudit]:
    valid = [normalize_manual_standard(f) for f in frames if f is not None and len(f)]
    inventory = pd.concat(valid, ignore_index=True, sort=False) if valid else pd.DataFrame(columns=STANDARD_COLUMNS)
    inventory["service_name"] = _clean_text(inventory["service_name"])
    inventory["municipality_name"] = _clean_text(inventory["municipality_name"])
    inventory = inventory.drop_duplicates(subset=["service_id"], keep="first").reset_index(drop=True)
    validate_consolidated_inventory(inventory)
    audit = ConsolidationAudit(
        rows_total=int(len(inventory)),
        rows_by_source=inventory["provider_source"].value_counts(dropna=False),
        rows_by_type=inventory["service_type"].value_counts(dropna=False),
        missing_coordinates=int(inventory[["latitude", "longitude"]].isna().any(axis=1).sum()),
        missing_capacity=int(pd.to_numeric(inventory["capacity"], errors="coerce").isna().sum()),
        duplicate_service_ids=int(inventory["service_id"].duplicated().sum()),
    )
    return inventory, audit


def load_and_consolidate_artifact(artifact_dir: Path, reference_date: str) -> tuple[pd.DataFrame, ConsolidationAudit]:
    frames: list[pd.DataFrame] = []
    cnes = artifact_dir / "cnes_pa_vaw_health_candidates.csv"
    if cnes.exists():
        cnes_frame = normalize_cnes_candidates(pd.read_csv(cnes), reference_date)
        beds_path = artifact_dir / "hospital_beds_pa_by_cnes.csv"
        if beds_path.exists():
            cnes_frame = apply_cnes_bed_capacity(cnes_frame, pd.read_csv(beds_path))
        frames.append(cnes_frame)
    tjpa = artifact_dir / "tjpa_specialized_vaw_units.csv"
    if tjpa.exists():
        frames.append(normalize_tjpa(pd.read_csv(tjpa), reference_date))
    creas_sagi, creas_legacy = artifact_dir / "creas_sagi_pa.csv", artifact_dir / "creas_2024_para_extracted.csv"
    if creas_sagi.exists():
        frames.append(infer_creas_units(pd.read_csv(creas_sagi, low_memory=False), "MDS/SAGI"))
    elif creas_legacy.exists():
        frames.append(infer_creas_units(pd.read_csv(creas_legacy, low_memory=False), "Censo SUAS 2024"))
    manual = artifact_dir / "ligue180_services_curated.csv"
    if manual.exists():
        frames.append(normalize_manual_standard(pd.read_csv(manual)))
    return consolidate_service_frames(frames)
