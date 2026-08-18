import pandas as pd
import pytest

from src.data.service_consolidation import (
    consolidate_service_frames,
    infer_creas_units,
    normalize_cnes_candidates,
    normalize_tjpa,
    validate_consolidated_inventory,
)


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
