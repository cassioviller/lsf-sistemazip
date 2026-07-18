"""Seed da Fase 3: regras de fundação/vento, composição própria VK-C-005 e a
folha 02.01 — a macroetapa 02 deixa de ser um agrupador vazio (que o R7 bloqueava
sem oferecer caminho) e ganha a folha que o motor de fundação preenche."""
import pytest

from lsf.motores.orcamento import custo_composicao


def test_regras_de_fundacao_e_vento_com_referencia(con):
    regras = {chave: (valor, ref) for chave, valor, ref in con.execute(
        "SELECT chave, valor, referencia FROM regra_lsf WHERE chave LIKE 'fund%'"
        " OR chave LIKE 'vento%' OR chave LIKE 'fita%'")}
    assert regras["fund_larg_min_m"][0] == pytest.approx(0.30)
    assert regras["fund_altura_baldrame_m"][0] == pytest.approx(0.40)
    assert regras["vento_pressao_kn_m2"][0] == pytest.approx(0.61)
    assert regras["fita_trd_kn"][0] == pytest.approx(17.9)
    assert regras["fitas_min_por_linha"][0] == pytest.approx(3)
    for chave, (_, ref) in regras.items():
        assert ref, f"regra de engenharia '{chave}' sem referência anotada"


def test_folha_02_01_tem_composicao_e_custo_que_fecha(con):
    folha = con.execute(
        "SELECT e.unidade, c.codigo_fonte, c.id FROM eap_item e"
        " JOIN composicao c ON c.id = e.composicao_id"
        " WHERE e.codigo = '02.01'").fetchone()
    assert folha is not None, "folha 02.01 ausente — macroetapa 02 ficaria vazia"
    unidade, codigo, composicao_id = folha
    assert unidade == "m3"
    assert codigo == "VK-C-005"

    custo_unitario, confianca = custo_composicao(con, composicao_id, "2026-06", "SP", 0)
    # baldrame armado: ordem de 1.200-1.800 R$/m³ na praça — fora disso o
    # coeficiente ou o preço está errado em 10x, não em 10%
    assert 800 < custo_unitario < 2500
    assert confianca == "estimado"


def test_mapeamento_fundacao_deixou_de_ser_todo(con):
    linha = con.execute(
        "SELECT c.codigo_fonte FROM mapeamento_item m"
        " JOIN composicao c ON c.id = m.composicao_id"
        " WHERE m.item_derivado = 'fundacao.concreto_fck30_m3'").fetchone()
    assert linha is not None, (
        "mapeamento 'fundacao.concreto_fck30_m3' segue NULL — pendência de custo"
        " que a Fase 3 veio fechar")
    assert linha[0] == "VK-C-005"


def test_seed_reaplicado_nao_duplica(con):
    import pathlib
    seed = (pathlib.Path(__file__).resolve().parents[1] / "db" / "seed.sql").read_text()
    antes = {tabela: con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
             for tabela in ("insumo", "composicao", "composicao_item",
                            "eap_item", "regra_lsf", "insumo_preco")}
    con.executescript(seed)
    depois = {tabela: con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
              for tabela in antes}
    assert antes == depois, "seed não idempotente: conhecimento duplicado"
