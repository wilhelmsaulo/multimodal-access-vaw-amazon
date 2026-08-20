from __future__ import annotations

import base64
import gzip
import hashlib
import json
from io import BytesIO
from pathlib import Path

import pandas as pd


CNES_CORE = Path("data/snapshots/cnes_pa_service165_core_attributes_2026-08-19.csv")
CNES_EVIDENCE_MANIFEST = Path("data/snapshots/cnes_pa_vaw_service_relations_202607.manifest.json")
CREAS_SNAPSHOT = Path("data/snapshots/creas_sagi_pa_2026-08-19.csv.gz.b64")
CREAS_MANIFEST = Path("data/snapshots/creas_sagi_pa_2026-08-19.manifest.json")

SPECIALIZED_SERVICE = "165"
COMPLEMENTARY_SERVICES = {"110", "112", "115", "140"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_creas() -> tuple[pd.DataFrame, dict]:
    encoded = CREAS_SNAPSHOT.read_text(encoding="utf-8").strip()
    csv_bytes = gzip.decompress(base64.b64decode(encoded))
    frame = pd.read_csv(BytesIO(csv_bytes), dtype=str)
    manifest = json.loads(CREAS_MANIFEST.read_text(encoding="utf-8"))
    expected = manifest.get("para_snapshot_sha256")
    if expected and sha256_bytes(csv_bytes) != expected:
        raise ValueError("CREAS snapshot SHA-256 mismatch")
    return frame, manifest


def load_cnes_evidence_manifest() -> dict:
    manifest = json.loads(CNES_EVIDENCE_MANIFEST.read_text(encoding="utf-8"))
    specialized = manifest.get("specialized_service", {})
    if str(specialized.get("code")) != SPECIALIZED_SERVICE:
        raise ValueError("CNES evidence manifest does not identify service 165 as the specialized service")
    if int(specialized.get("unique_establishments_para", -1)) != 71:
        raise ValueError("CNES evidence manifest must report 71 unique Pará establishments for service 165")
    if int(manifest.get("retained_rows", -1)) != 3190:
        raise ValueError("CNES evidence manifest retained-row count differs from the audited July 2026 snapshot")
    return manifest


def build_cnes(out_dir: Path) -> dict:
    core = pd.read_csv(CNES_CORE, dtype=str)
    if len(core) != 71 or core["codigo_cnes"].nunique() != 71:
        raise ValueError("CNES service-165 core snapshot must contain 71 unique establishments")

    evidence_manifest = load_cnes_evidence_manifest()
    specialized = evidence_manifest["specialized_service"]
    complementary = evidence_manifest.get("complementary_services", {})

    core["vaw_health_function"] = "specialized_sexual_violence_response"
    core["primary_function_eligible"] = True
    core["validation_status"] = "function_validated_from_cnes_service_165"
    core["cnes_vaw_specialized_service_165"] = True

    core.to_csv(out_dir / "cnes_pa_active_raw.csv", index=False)
    core.to_csv(out_dir / "cnes_pa_vaw_health_specialized.csv", index=False)
    core.to_csv(out_dir / "cnes_pa_vaw_health_candidates.csv", index=False)

    lat = pd.to_numeric(core["latitude_estabelecimento_decimo_grau"], errors="coerce")
    lon = pd.to_numeric(core["longitude_estabelecimento_decimo_grau"], errors="coerce")
    valid_coords = lat.between(-90, 90) & lon.between(-180, 180)

    classification_counts = {
        str(k): int(v) for k, v in specialized.get("classification_counts", {}).items()
    }
    complementary_by_service = {
        code: int(complementary.get(code, {}).get("unique_establishments_para", 0))
        for code in sorted(COMPLEMENTARY_SERVICES)
    }

    audit = {
        "source_snapshot": evidence_manifest.get("source_file"),
        "source_sha256": evidence_manifest.get("source_sha256"),
        "retained_relation_rows": int(evidence_manifest.get("retained_rows", 0)),
        "retained_unique_establishments_all_selected_services": int(
            evidence_manifest.get("retained_unique_establishments", 0)
        ),
        "specialized_service_code": SPECIALIZED_SERVICE,
        "specialized_establishments_para": int(len(core)),
        "specialized_classification_rows_para": int(specialized.get("relation_rows_para", 0)),
        "specialized_classification_counts": classification_counts,
        "complementary_service_codes": sorted(COMPLEMENTARY_SERVICES),
        "complementary_unique_establishments_by_service": complementary_by_service,
        "interpretation": (
            "CNES service 165 defines the primary specialized health-response layer. "
            "Services 110, 112, 115 and 140 are retained in the provenance manifest as a separate "
            "complementary network and are not substitutes for service 165. The primary workflow uses "
            "the versioned 71-establishment specialized-core snapshot directly, so the large relation "
            "table is not a runtime dependency."
        ),
    }
    (out_dir / "cnes_vaw_service_evidence_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    manifest = {
        "source": "CNES official establishment attributes + CNES July 2026 service/classification evidence",
        "source_mode": "versioned_specialized_core_snapshot",
        "primary_health_layer_rule": "CNES specialized service 165",
        "rows_vaw_health_primary_specialized": int(len(core)),
        "rows_with_valid_coordinates": int(valid_coords.sum()),
        "rows_without_valid_coordinates": int((~valid_coords).sum()),
        "service_evidence_snapshot": evidence_manifest.get("source_file"),
        "service_evidence_source_sha256": evidence_manifest.get("source_sha256"),
        "service_evidence_filtered_snapshot_sha256": evidence_manifest.get("filtered_snapshot_sha256"),
        "attribute_snapshot_file": str(CNES_CORE),
        "attribute_snapshot_sha256": sha256_bytes(CNES_CORE.read_bytes()),
        "live_establishment_api_used": False,
        "live_beds_endpoint_used": False,
        "large_relation_snapshot_runtime_dependency": False,
        "capacity_rule": "Bed capacity is not required for the primary analysis and no live beds endpoint is queried in the default workflow.",
        "temporal_note": "Service eligibility is fixed to CNES July 2026 service/classification data; establishment attributes are a versioned official extract successfully retrieved on 2026-08-19.",
    }
    (out_dir / "cnes_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "hospital_beds_pa_raw.csv").write_text("", encoding="utf-8")
    (out_dir / "hospital_beds_pa_by_cnes.csv").write_text("", encoding="utf-8")
    return manifest


def build_creas(out_dir: Path) -> dict:
    frame, source_manifest = load_creas()
    frame.to_csv(out_dir / "creas_sagi_pa.csv", index=False)
    georef = frame["georef_location"].astype("string").str.strip()
    manifest = {
        "source": "MDS/SAGI equipment registry",
        "source_mode": "versioned_official_snapshot",
        "endpoint": source_manifest.get("source_url"),
        "download_date": source_manifest.get("download_date"),
        "raw_sha256": source_manifest.get("raw_sha256"),
        "snapshot_sha256": source_manifest.get("para_snapshot_sha256"),
        "source_status": "snapshot_available",
        "rows_para": int(len(frame)),
        "rows_para_with_georef": int(georef.notna().sum()),
        "rows_para_without_georef": int(georef.isna().sum()),
        "unique_equipment_ids": int(frame["id_equipamento"].nunique()),
        "primary_supply_rule": "One validated CREAS physical unit equals one supply opportunity within the CREAS category.",
    }
    (out_dir / "creas_sagi_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    out_dir = Path("artifacts/service_inventory")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"cnes": build_cnes(out_dir), "creas": build_creas(out_dir)}
    (out_dir / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
