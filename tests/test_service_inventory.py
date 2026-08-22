import httpx
import pandas as pd

from src.data.service_inventory import (
    fetch_cnes_establishments_pa,
    filter_cnes_vaw_relevant,
    harmonize_manual_service_table,
    parse_tjpa_specialized_units,
)


def test_fetch_cnes_paginates_and_filters_state_params():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        offset = int(request.url.params["offset"])
        if offset == 0:
            return httpx.Response(200, json=[{"codigo_cnes": 1}, {"codigo_cnes": 2}])
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    df = fetch_cnes_establishments_pa(client=client, page_size=2)
    assert len(df) == 2
    assert calls[0]["codigo_uf"] == "15"
    assert calls[0]["status"] == "1"


def test_filter_cnes_vaw_relevant_is_conservative():
    df = pd.DataFrame(
        {
            "nome_fantasia": ["Hospital Regional", "Unidade Básica Centro", "CAPS II"],
            "descricao_tipo_unidade": ["Hospital", "UBS", "Centro Psicossocial"],
        }
    )
    out = filter_cnes_vaw_relevant(df)
    assert set(out["nome_fantasia"]) == {"Hospital Regional", "CAPS II"}


def test_parse_tjpa_specialized_units():
    html = """
    <div>SECRETARIA DA 1ª VARA VIOLÊNCIA DOMÉSTICA E FAMILIAR CONTRA A MULHER
    Cidade : Belém | Tipo : Judicial 1º Grau</div>
    <div>VARA ÚNICA DE CHAVES Cidade : Chaves | Tipo : Judicial 1º Grau</div>
    """
    out = parse_tjpa_specialized_units(html)
    assert len(out) == 1
    assert out.iloc[0]["municipality_name"] == "Belém"
    assert out.iloc[0]["service_type"] == "specialized_justice"


def test_harmonize_manual_service_table_preserves_missing_capacity():
    raw = pd.DataFrame(
        {
            "service_id": ["x1"],
            "service_name": ["CREAS Teste"],
            "service_type": ["creas"],
            "municipality_name": ["Teste"],
        }
    )
    out = harmonize_manual_service_table(raw, provider_source="Censo SUAS", reference_date="2024")
    assert pd.isna(out.iloc[0]["capacity"])
    assert out.iloc[0]["validation_status"] == "needs_validation"
