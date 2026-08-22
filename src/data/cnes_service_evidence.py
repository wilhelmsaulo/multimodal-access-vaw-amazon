from __future__ import annotations

import base64
import gzip
import hashlib
import json
from io import BytesIO
from pathlib import Path

import pandas as pd


CNES_VAW_RELATIONS_SNAPSHOT = Path("data/snapshots/cnes_pa_vaw_service_relations_202607.csv.gz.b64")
CNES_VAW_RELATIONS_MANIFEST = Path("data/snapshots/cnes_pa_vaw_service_relations_202607.manifest.json")
CNES_VAW_RELATIONS_SHA256 = "3b3419c928a5be0b753f4198b7c1d7fd7082e4c053c52283839bfcc1f266c8ed"

SPECIALIZED_SERVICE = "165"
COMPLEMENTARY_SERVICES = {"110", "112", "115", "140"}


def load_cnes_vaw_service_relations() -> tuple[pd.DataFrame, dict]:
    """Load the versioned Pará-only CNES service/classification snapshot."""
    encoded = CNES_VAW_RELATIONS_SNAPSHOT.read_text(encoding="utf-8").strip()
    csv_bytes = gzip.decompress(base64.b64decode(encoded))
    digest = hashlib.sha256(csv_bytes).hexdigest()
    if digest != CNES_VAW_RELATIONS_SHA256:
        raise ValueError(
            f"CNES VAW relations snapshot SHA-256 mismatch: expected {CNES_VAW_RELATIONS_SHA256}, got {digest}"
        )
    frame = pd.read_csv(BytesIO(csv_bytes), dtype=str)
    frame["CO_UNIDADE"] = frame["CO_UNIDADE"].astype("string").str.strip()
    frame["CO_SERVICO"] = frame["CO_SERVICO"].astype("string").str.zfill(3)
    frame["CO_CLASSIFICACAO"] = frame["CO_CLASSIFICACAO"].astype("string").str.zfill(3)
    manifest = json.loads(CNES_VAW_RELATIONS_MANIFEST.read_text(encoding="utf-8"))
    return frame, manifest


def annotate_cnes_with_vaw_service_evidence(
    establishments: pd.DataFrame,
    relations: pd.DataFrame,
) -> pd.DataFrame:
    """Attach direct CNES service evidence without treating service groups as substitutes.

    Service 165 is the specialized health-response core. Services 110, 112, 115
    and 140 are complementary response-network evidence only. Establishments can
    belong to both groups, but complementary services never upgrade a facility to
    specialized status.
    """
    if establishments.empty:
        return establishments.copy()
    if "codigo_estabelecimento_saude" not in establishments.columns:
        raise ValueError("CNES establishments missing codigo_estabelecimento_saude")
    required = {"CO_UNIDADE", "CO_SERVICO", "CO_CLASSIFICACAO"}
    missing = required.difference(relations.columns)
    if missing:
        raise ValueError(f"CNES service relations missing columns: {sorted(missing)}")

    out = establishments.copy()
    key = out["codigo_estabelecimento_saude"].astype("string").str.strip()
    rel = relations.copy()
    rel["CO_UNIDADE"] = rel["CO_UNIDADE"].astype("string").str.strip()
    rel["CO_SERVICO"] = rel["CO_SERVICO"].astype("string").str.zfill(3)
    rel["CO_CLASSIFICACAO"] = rel["CO_CLASSIFICACAO"].astype("string").str.zfill(3)

    specialized = rel.loc[rel["CO_SERVICO"].eq(SPECIALIZED_SERVICE)]
    specialized_ids = set(specialized["CO_UNIDADE"].dropna())
    complementary = rel.loc[rel["CO_SERVICO"].isin(COMPLEMENTARY_SERVICES)]

    by_unit_services = (
        complementary.groupby("CO_UNIDADE")["CO_SERVICO"]
        .agg(lambda s: "|".join(sorted(set(s.dropna()))))
        .to_dict()
    )
    by_unit_classes = (
        specialized.groupby("CO_UNIDADE")["CO_CLASSIFICACAO"]
        .agg(lambda s: "|".join(sorted(set(s.dropna()))))
        .to_dict()
    )

    out["cnes_vaw_specialized_service_165"] = key.isin(specialized_ids)
    out["cnes_vaw_specialized_classifications"] = key.map(by_unit_classes).fillna("")
    out["cnes_vaw_complementary_services"] = key.map(by_unit_services).fillna("")
    out["cnes_vaw_has_complementary_service"] = out["cnes_vaw_complementary_services"].ne("")
    out["cnes_vaw_service_tier"] = "no_selected_service_evidence"
    out.loc[out["cnes_vaw_has_complementary_service"], "cnes_vaw_service_tier"] = "complementary_response_network"
    out.loc[out["cnes_vaw_specialized_service_165"], "cnes_vaw_service_tier"] = "specialized_sexual_violence_response"
    return out
