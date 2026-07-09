"""Item 4 do contrato da Fase 1: BDI decomposto (fórmula TCU) e preço de venda."""
import pytest

from lsf.motores.orcamento import (
    OrcamentoError,
    ParametrosBDI,
    aplicar_bdi,
    bdi_tcu,
    carregar_parametros_bdi,
    custo_direto_projeto,
)
from test_custo_direto import QTD, _analitica_96359

# Parâmetros do spike 3 — mesmos valores da migração 002
PARAMS_SPIKE3 = ParametrosBDI(ac=0.04, s=0.008, r=0.0127, g=0.0113, df=0.0139, l=0.0740, i=0.0865)


@pytest.fixture
def projeto(con):
    _analitica_96359(con)
    pid = con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf) VALUES ('109.1506', 'Máximo', '2026-06', 'SP')"
    ).lastrowid
    for codigo, qtd in QTD.items():
        eap = con.execute("SELECT id FROM eap_item WHERE codigo = ?", (codigo,)).fetchone()[0]
        con.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem, confianca)"
            " VALUES (?, ?, ?, 'MANUAL', 'real')",
            (pid, eap, qtd),
        )
    return pid


# ---------- fórmula TCU (regressão contra o spike 3) ----------

def test_bdi_tcu_reproduz_spike3():
    assert bdi_tcu(PARAMS_SPIKE3) * 100 == pytest.approx(27.79, abs=0.005)


def test_bdi_imposto_maior_que_1_falha():
    with pytest.raises(OrcamentoError, match="fora de"):
        bdi_tcu(ParametrosBDI(ac=0.04, s=0.008, r=0.0127, g=0.0113, df=0.0139, l=0.0740, i=1.0))


def test_bdi_componente_negativo_falha():
    with pytest.raises(OrcamentoError, match="negativo"):
        bdi_tcu(ParametrosBDI(ac=-0.01, s=0.008, r=0.0127, g=0.0113, df=0.0139, l=0.0740, i=0.0865))


# ---------- carga de parametros_globais (migração 002) ----------

def test_carregar_parametros_do_banco_bate_com_spike3(con):
    params = carregar_parametros_bdi(con)
    assert params == ParametrosBDI(**{
        k: getattr(PARAMS_SPIKE3, k) for k in ("ac", "s", "r", "g", "df", "l", "i")
    }, confianca="estimado")
    assert bdi_tcu(params) * 100 == pytest.approx(27.79, abs=0.005)


def test_chave_de_bdi_faltando_falha(con):
    con.execute("DELETE FROM parametros_globais WHERE chave = 'bdi_l'")
    with pytest.raises(OrcamentoError, match="bdi_l"):
        carregar_parametros_bdi(con)


# ---------- aplicar_bdi ----------

def test_propriedade_preco_total_e_custo_vezes_1_mais_bdi(con, projeto):
    orc = custo_direto_projeto(con, projeto)
    venda = aplicar_bdi(orc, carregar_parametros_bdi(con))
    assert venda.preco_total == pytest.approx(orc.total * (1 + venda.bdi), abs=0.01)
    # e linha a linha, com custo direto e BDI% visíveis separadamente
    for lv, lo in zip(venda.linhas, orc.linhas):
        assert lv.custo_direto == lo.custo_total
        assert lv.preco_venda == pytest.approx(lo.custo_total * (1 + venda.bdi), abs=0.01)
    assert sum(l.preco_venda for l in venda.linhas) == pytest.approx(venda.preco_total, abs=0.01)


def test_bdi_estimado_rebaixa_preco_de_linha_real(con, projeto):
    """D4: o preço herda a incerteza do markup — linha 06.01 é 'real', o preço não é."""
    venda = aplicar_bdi(custo_direto_projeto(con, projeto), carregar_parametros_bdi(con))
    linha = next(l for l in venda.linhas if l.eap_codigo == "06.01")
    assert linha.confianca == "estimado"


def test_linha_pendente_nao_ganha_preco(con, projeto):
    comp = con.execute("SELECT id FROM composicao WHERE codigo_fonte = '96359'").fetchone()[0]
    con.execute("DELETE FROM composicao_item WHERE composicao_id = ?", (comp,))
    venda = aplicar_bdi(custo_direto_projeto(con, projeto), carregar_parametros_bdi(con))
    linha = next(l for l in venda.linhas if l.eap_codigo == "06.01")
    assert linha.preco_venda is None and linha.pendencia
    assert venda.preco_total is None  # preço de venda também se recusa a fechar
