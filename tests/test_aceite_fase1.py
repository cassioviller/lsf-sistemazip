"""ACEITE DA FASE 1 (portão do roteiro): reproduzir o orçamento real da obra
109.1506 (Máximo Tintas) com desvio ≤ 2%.

Referência: tests/fixtures/orcamento_v7_109_1506.json — o engine do calculador v7
executado headless (node), com as quantidades e preços oficiais da obra. Os
quantitativos entram origem=MANUAL, isolando erro de preço de erro de regra."""
import json
import pathlib
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))

from carregar_orcamento_v7 import (  # noqa: E402
    carregar,
    carregar_fixture,
    parametros_bdi_da_obra,
    tabela_desvio,
)
from lsf.motores.orcamento import aplicar_bdi, bdi_tcu, custo_direto_projeto  # noqa: E402


@pytest.fixture(scope="module")
def fixture_v7():
    return carregar_fixture()


@pytest.fixture
def venda(con, fixture_v7):
    pid = carregar(con, fixture_v7)
    return aplicar_bdi(custo_direto_projeto(con, pid), parametros_bdi_da_obra(fixture_v7))


def test_fixture_e_internamente_consistente(fixture_v7):
    """O JSON extraído do v7 fecha consigo mesmo (guarda contra fixture corrompida)."""
    soma = sum(l["total"] for l in fixture_v7["linhas"])
    assert soma == pytest.approx(fixture_v7["custo_direto"], rel=1e-9)
    assert fixture_v7["custo_direto"] * (1 + fixture_v7["bdi"]) == pytest.approx(
        fixture_v7["total_com_bdi"], rel=1e-9
    )
    for l in fixture_v7["linhas"]:
        assert l["total"] == pytest.approx(
            l["qtd"] * l["preco_unit"] * (1 + fixture_v7["perda_extra"]), rel=1e-9
        )


def test_bdi_da_obra_e_22_pct(fixture_v7):
    assert bdi_tcu(parametros_bdi_da_obra(fixture_v7)) == pytest.approx(0.22, abs=1e-12)


def test_aceite_desvio_total_menor_que_2_pct(venda, fixture_v7):
    """O critério oficial da fase."""
    _, (nosso, v7, desvio_pct) = tabela_desvio(venda, fixture_v7)
    assert abs(desvio_pct) <= 2.0, f"desvio {desvio_pct:.4f}% > 2%"
    # e na prática a reprodução é exata (mesma aritmética): qualquer folga real
    # que aparecer aqui é bug de agregação, não 'diferença de arredondamento'
    assert nosso == pytest.approx(v7, rel=1e-9)


def test_aceite_linha_a_linha(venda, fixture_v7):
    linhas, _ = tabela_desvio(venda, fixture_v7)
    assert len(linhas) == 10
    for eap, item, nosso, v7, desvio_pct in linhas:
        assert abs(desvio_pct) <= 2.0, f"{eap} {item}: desvio {desvio_pct:.4f}%"
        assert nosso == pytest.approx(v7, rel=1e-9), f"{eap} {item}"


def test_custo_direto_bate_com_v7(venda, fixture_v7):
    assert venda.orcamento.total == pytest.approx(fixture_v7["custo_direto"], rel=1e-9)


def test_confianca_do_orcamento_e_estimado_nao_real(venda):
    """Preços de referência sem calibração de obra (R6) não podem sair como 'real'."""
    assert venda.confianca == "estimado"
    assert all(l.confianca == "estimado" for l in venda.linhas)


def test_macroetapas_zeradas_continuam_visiveis(venda):
    """O orçamento da obra cobre estrutura/fechamento/acabamento; o gate R7 tem que
    continuar apontando o que o turn-key ainda não precificou."""
    assert set(venda.orcamento.macroetapas_zeradas) == {"01", "02", "05", "07", "08"}
