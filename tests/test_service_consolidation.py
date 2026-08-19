import pandas as pd
import pytest

from src.data.service_consolidation import (
    apply_cnes_bed_capacity,
    consolidate_service_frames,
    infer_creas_units,
    normalize_cnes_candidates,
    normalize_tjpa,
    validate_consolidated_inventory,
)
from src.data.service_readiness import audit_service_readiness


def test_normalize_and_consolidate_sources():
    cnes = pd.DataFrame(
        {
            "codigo_cnes": [12345],
            "nome_fantasia": ["Hospital da Mulher"],
            "nome_municipio": ["Belém"],
            "latitude": [-1.45],
            "longitude": [-48.49],
        }
    )
    tjpa = pd.DataFrame(
        {
            "service_name": ["Vara de Violência Doméstica"],
            "municipality_name": ["Santarém"],
        }
    )
    creas_raw = pd.DataFrame(
        {
            "ID CREAS": ["150001"],
            "Nome da Unidade": ["CREAS Centro"],
            "Município": ["Óbidos"],
            "IBGE": [1505106],
        }
    )
    frames = [
        normalize_cnes_candidates(cnes, "2026-08-18"),
        normalize_tjpa(tjpa, "2026-08-18"),
        infer_creas_units(creas_raw, "Censo SUAS 2024"),
    ]
    inventory, audit = consolidate_service_frames(frames)
    assert len(inventory) == 3
    assert set(inventory["service_type"]) == {"health", "specialized_justice", "creas"}
    assert audit.duplicate_service_ids == 0
    assert audit.rows_total == 3


def test_demas_cnes_field_aliases_are_preserved():
    cnes = pd.DataFrame(
        {
            "codigo_cnes": [9633758],
            "nome_fantasia": ["Hospital Geral"],
            "codigo_municipio": [150345],
            "endereco_estabelecimento": ["Av. Principal"],
            "numero_estabelecimento": ["123"],
            "latitude_estabelecimento_decimo_grau": [-2.559786],
            "longitude_estabelecimento_decimo_grau": [-47.498322],
        }
    )
    out = normalize_cnes_candidates(cnes, "2026-08-18")
    row = out.iloc[0]
    assert row["latitude"] == pytest.approx(-2.559786)
    assert row["longitude"] == pytest.approx(-47.498322)
    assert row["address_public"] == "Av. Principal, 123"
    assert str(row["municipality_code"]) == "150345"


def test_sagi_creas_georeference_is_preserved_without_inventing_capacity():
    creas = pd.DataFrame(
        {
            "id_equipamento": [1506801932],
            "ibge": [150680],
            "uf": ["PA"],
            "cidade": ["Santarém"],
            "nome": ["CREAS Municipal"],
            "endereco": ["SILVA JARDIM - 460"],
            "georef_location": [r"-2.4227511666704946\,-54.721895634702385"],
            "data_atualizacao": ["2026-08-14T04:28:43.318Z"],
        }
    )
    out = infer_creas_units(creas, "MDS/SAGI")
    row = out.iloc[0]
    assert row["service_id"] == "CREAS-1506801932"
    assert row["provider_source"] == "MDS/SAGI"
    assert str(row["municipality_code"]) == "150680"
    assert row["latitude"] == pytest.approx(-2.4227511666704946)
    assert row["longitude"] == pytest.approx(-54.721895634702385)
    assert pd.isna(row["capacity"])
    assert row["validation_status"] == "official_sagi_georeference_requires_routing_validation"


def test_primary_readiness_uses_unit_supply_not_capacity():
    inventory = pd.DataFrame(
        {
            "service_id": ["S-1"],
            "service_name": ["Validated service"],
            "service_type": ["creas"],
            "provider_source": ["official"],
            "municipality_name": ["Santarém"],
            "address_public": ["Rua A, 1"],
            "latitude": [-2.43],
            "longitude": [-54.70],
            "capacity": [pd.NA],
            "capacity_type": [pd.NA],
            "validation_status": ["validated"],
        }
    )
    readiness, audit = audit_service_readiness(inventory)
    row = readiness.iloc[0]
    assert bool(row["ready_for_routing"])
    assert bool(row["ready_for_e2sfca_primary"])
    assert row["primary_supply_weight"] == 1.0
    assert "capacity" not in row["readiness_blockers"]
    assert audit.missing_capacity == 1
    assert audit.ready_for_e2sfca_primary == 1


def test_exact_cnes_match_attaches_registered_beds():
    cnes = pd.DataFrame(
        {"codigo_cnes": [12345, 67890], "nome_fantasia": ["Hospital A", "Hospital B"]}
    )
    inventory = normalize_cnes_candidates(cnes, "2026-08-18")
    beds = pd.DataFrame(
        {
            "codigo_cnes": ["12345"],
            "capacity": [42.0],
            "capacity_type": ["registered_beds"],
            "capacity_source": ["DEMAS hospitais-e-leitos"],
        }
    )
    out = apply_cnes_bed_capacity(inventory, beds)
    matched = out.loc[out["service_id"] == "CNES-12345"].iloc[0]
    unmatched = out.loc[out["service_id"] == "CNES-67890"].iloc[0]
    assert matched["capacity"] == 42.0
    assert matched["capacity_type"] == "registered_beds"
    assert pd.isna(unmatched["capacity"])


def test_invalid_capacity_is_rejected():
    frame = pd.DataFrame(
        {
            "service_id": ["X-1"],
            "service_name": ["Unit"],
            "service_type": ["health"],
            "provider_source": ["test"],
            "municipality_code": [pd.NA],
            "municipality_name": ["Belém"],
            "address_public": [pd.NA],
            "latitude": [-1.4],
            "longitude": [-48.5],
            "capacity": [-1],
            "capacity_type": ["beds"],
            "capacity_source": ["test"],
            "reference_date": ["2026-08-18"],
            "validation_status": ["validated"],
            "redistribution_status": ["review_required"],
        }
    )
    with pytest.raises(ValueError, match="capacity cannot be negative"):
        validate_consolidated_inventory(frame)
