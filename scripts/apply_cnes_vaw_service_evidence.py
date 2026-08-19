from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.data.cnes_service_evidence import (
    COMPLEMENTARY_SERVICES,
    SPECIALIZED_SERVICE,
    annotate_cnes_with_vaw_service_evidence,
    load_cnes_vaw_service_relations,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts/service_inventory"))
    args = parser.parse_args()

    active_path = args.artifact_dir / "cnes_pa_active_raw.csv"
    screened_path = args.artifact_dir / "cnes_pa_vaw_health_candidates.csv"
    manifest_path = args.artifact_dir / "cnes_manifest.json"
    if not active_path.exists():
        raise FileNotFoundError(active_path)

    active = pd.read_csv(active_path, dtype=str, low_memory=False)
    relations, source_manifest = load_cnes_vaw_service_relations()
    annotated = annotate_cnes_with_vaw_service_evidence(active, relations)

    specialized = annotated.loc[annotated["cnes_vaw_specialized_service_165"].fillna(False)].copy()
    specialized["vaw_health_function"] = "specialized_sexual_violence_response"
    specialized["primary_function_eligible"] = True
    specialized["validation_status"] = "function_validated_from_cnes_service_165"
    specialized.to_csv(args.artifact_dir / "cnes_pa_vaw_health_specialized.csv", index=False)

    complementary = annotated.loc[
        annotated["cnes_vaw_has_complementary_service"].fillna(False)
        & ~annotated["cnes_vaw_specialized_service_165"].fillna(False)
    ].copy()
    complementary["vaw_health_function"] = "complementary_response_network"
    complementary["primary_function_eligible"] = False
    complementary["validation_status"] = "complementary_network_not_specialized"
    complementary.to_csv(args.artifact_dir / "cnes_pa_vaw_health_complementary.csv", index=False)

    # The consolidated primary health layer is now the direct CNES service-165 core.
    # The former text/type-screened table is retained separately for audit only.
    if screened_path.exists():
        screened = pd.read_csv(screened_path, dtype=str, low_memory=False)
        screened.to_csv(args.artifact_dir / "cnes_pa_vaw_health_text_type_screened_audit.csv", index=False)
    specialized.to_csv(screened_path, index=False)

    summary = {
        "source_snapshot": source_manifest.get("source_file"),
        "specialized_service_code": SPECIALIZED_SERVICE,
        "specialized_establishments_para": int(len(specialized)),
        "specialized_classification_rows_para": int(
            relations.loc[relations["CO_SERVICO"].eq(SPECIALIZED_SERVICE)].shape[0]
        ),
        "specialized_classification_counts": {
            str(k): int(v)
            for k, v in relations.loc[relations["CO_SERVICO"].eq(SPECIALIZED_SERVICE), "CO_CLASSIFICACAO"]
            .value_counts()
            .sort_index()
            .to_dict()
            .items()
        },
        "complementary_service_codes": sorted(COMPLEMENTARY_SERVICES),
        "complementary_establishments_excluding_specialized": int(len(complementary)),
        "complementary_unique_establishments_by_service": {
            code: int(relations.loc[relations["CO_SERVICO"].eq(code), "CO_UNIDADE"].nunique())
            for code in sorted(COMPLEMENTARY_SERVICES)
        },
        "interpretation": (
            "Service 165 defines the primary specialized health-response layer. "
            "Services 110, 112, 115 and 140 are retained as a separate complementary network and are not substitutes."
        ),
    }
    (args.artifact_dir / "cnes_vaw_service_evidence_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {}
    manifest.update(
        {
            "primary_health_layer_rule": "CNES specialized service 165",
            "rows_vaw_health_primary_specialized": int(len(specialized)),
            "rows_vaw_health_complementary_excluding_specialized": int(len(complementary)),
            "service_evidence_snapshot": source_manifest.get("source_file"),
            "service_evidence_source_sha256": source_manifest.get("source_sha256"),
            "service_evidence_note": (
                "The older name/type screening is retained only as an audit artifact. "
                "Direct CNES service evidence supersedes text screening for primary specialized-health inclusion."
            ),
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
