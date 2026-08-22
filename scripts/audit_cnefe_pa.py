from __future__ import annotations

import json
from pathlib import Path
import re
import zipfile
from io import BytesIO

import httpx
import pandas as pd

CNEFE_PA_URL = (
    "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
    "Censo_Demografico_2022/Coordenadas_enderecos/UF/15_PA.zip"
)


def _norm(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def find_columns(columns: list[str], tokens: tuple[str, ...]) -> list[str]:
    out = []
    for col in columns:
        normalized = _norm(col)
        if all(token in normalized for token in tokens):
            out.append(col)
    return out


def read_member(data: bytes, name: str) -> pd.DataFrame:
    low = name.lower()
    if low.endswith(".csv"):
        for sep in (";", ",", "\t"):
            for enc in ("utf-8", "latin1"):
                try:
                    frame = pd.read_csv(BytesIO(data), sep=sep, encoding=enc, dtype="string", low_memory=False)
                    if len(frame.columns) > 3:
                        return frame
                except Exception:
                    pass
        raise ValueError(f"Could not parse CNEFE CSV member: {name}")
    if low.endswith(('.json', '.geojson')):
        payload = json.loads(data.decode("utf-8"))
        features = payload.get("features", []) if isinstance(payload, dict) else []
        rows = []
        for feature in features:
            props = dict(feature.get("properties") or {})
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") if geom.get("type") == "Point" else None
            if coords and len(coords) >= 2:
                props.setdefault("_geometry_longitude", coords[0])
                props.setdefault("_geometry_latitude", coords[1])
            rows.append(props)
        return pd.DataFrame(rows)
    return pd.DataFrame()


def audit_frame(frame: pd.DataFrame, source_member: str) -> dict:
    columns = [str(c) for c in frame.columns]
    sector_candidates = find_columns(columns, ("SETOR",))
    species_candidates = [
        c for c in columns if "ESPEC" in _norm(c) or "TIPOESPEC" in _norm(c)
    ]
    geo_level_candidates = [
        c for c in columns if "NVGEO" in _norm(c) or "NIVELGEO" in _norm(c)
    ]
    latitude_candidates = [c for c in columns if "LAT" in _norm(c)]
    longitude_candidates = [c for c in columns if "LONG" in _norm(c) or "LON" == _norm(c)]

    def counts(candidates: list[str], top: int = 50) -> dict[str, dict[str, int]]:
        result = {}
        for col in candidates:
            result[col] = {
                str(k): int(v)
                for k, v in frame[col].astype("string").fillna("<NA>").value_counts().head(top).items()
            }
        return result

    return {
        "source_member": source_member,
        "rows": int(len(frame)),
        "columns": columns,
        "sector_candidates": sector_candidates,
        "species_candidates": species_candidates,
        "geo_level_candidates": geo_level_candidates,
        "latitude_candidates": latitude_candidates,
        "longitude_candidates": longitude_candidates,
        "species_value_counts": counts(species_candidates),
        "geo_level_value_counts": counts(geo_level_candidates),
        "sector_unique_counts": {
            col: int(frame[col].nunique(dropna=True)) for col in sector_candidates
        },
        "missingness": {
            col: int(frame[col].isna().sum())
            for col in dict.fromkeys(
                sector_candidates
                + species_candidates
                + geo_level_candidates
                + latitude_candidates
                + longitude_candidates
            )
        },
    }


def main() -> None:
    out_dir = Path("artifacts/cnefe_pa_audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    response = httpx.get(CNEFE_PA_URL, timeout=180, follow_redirects=True)
    response.raise_for_status()
    archive_bytes = response.content

    members_audit = []
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        members = [n for n in archive.namelist() if not n.endswith("/")]
        for member in members:
            if not member.lower().endswith((".csv", ".json", ".geojson")):
                continue
            frame = read_member(archive.read(member), member)
            if frame.empty:
                continue
            members_audit.append(audit_frame(frame, member))

    if not members_audit:
        raise RuntimeError("No readable tabular CNEFE members found in 15_PA.zip")

    payload = {
        "source": "IBGE CNEFE Censo Demografico 2022 - Coordenadas de enderecos",
        "source_url": CNEFE_PA_URL,
        "state": "PA",
        "members": members_audit,
        "privacy_note": (
            "This artifact contains schema/value-count diagnostics only. Raw address-level "
            "coordinates are intentionally not uploaded or committed."
        ),
        "methodological_goal": (
            "Identify documented residential species and coordinate-quality fields before "
            "deriving one inhabited representative origin per census sector."
        ),
    }
    (out_dir / "cnefe_pa_schema_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
