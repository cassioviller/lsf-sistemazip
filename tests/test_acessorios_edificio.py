"""Acessórios de nível de EDIFÍCIO — blocos do `montarProjeto` do v7 que a porta
não tinha. Achados auditando a nossa saída contra o v7 headless depois do caso
BOX-003: 14 itens que o v7 orça e nós não. Item que falta em preço fechado é
escopo vazado — prejuízo, não arredondamento (CLAUDE.md).

Portados aqui (regra geral, verificável):
  * A5 [DX-11 p.40]  — parafuso de verga @200mm (sext. nos montantes-I, flang. nas guias)
  * DX-06 [OBRA p.6/8] — Chapa L de elevação de laje + cantoneira viga-borda
  * AD/BX [OBRA p.7-24] — perfis avulsos do kit, 2% do kg (é AÇO, ~473 kg na 109)
  * descobertas [folha 102 / NBR 14718] — impermeabilização + guarda-corpo

NÃO portados, de propósito (ver o commit):
  * instalações — exige tabela nova (pontos hidro/gás/elétrica não estão no schema)
  * vento NBR 6123 hold-down — o v7 chumba as dimensões da 109 (`vento*10,5*15,8`)
    e a quantidade (24 un). Não generaliza, e o CLAUDE.md exige engenheiro
    estrutural para a fórmula de vento (Fase 3).
"""
import pytest


def _itens(est, trecho):
    return [a for a in est.acessorios if trecho.lower() in a.item.lower()]


def test_parafuso_de_verga_a5_dx11(projeto_109_estrutura):
    """n = ceil(ml de verga / 0,20), em DUAS linhas: sextavado nos montantes-I e
    flangeado nas guias — o v7 emite as duas com a mesma quantidade."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)

    sext = _itens(est, "verga DX-11 (montantes-I")
    flang = _itens(est, "verga DX-11 (guias")
    assert len(sext) == 1 and len(flang) == 1
    assert sext[0].qtd == flang[0].qtd > 0

    ml_verga = sum(p.comp for p in est.pecas
                   if p.sistema == "parede" and "verga" in p.tipo)
    assert ml_verga > 0
    import math
    assert sext[0].qtd == math.ceil(ml_verga / 0.20)


def test_chapa_l_e_cantoneira_da_laje_dx06(projeto_109_estrutura):
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)

    # uma linha por laje (a 109 tem 2). Filtro específico: a escada também tem uma
    # "Chapa L", de reforço lateral — não é a de elevação de laje.
    chapas = _itens(est, "Chapa L #1,25 35×190×3000 (elevação de laje)")
    cant = _itens(est, "Cantoneira #1,25 89×89×89")
    assert len(chapas) == 2
    assert len(cant) == 2
    assert all(a.qtd > 0 for a in chapas)
    assert all(a.sistema == "laje" for a in cant)


def test_perfis_adbx_sao_2pct_do_kg_e_saem_em_kg(projeto_109_estrutura):
    """AD/BX é AÇO avulso do kit, não parafuso: sai em kg e pesa ~473 kg na 109."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)

    adbx = _itens(est, "AD/BX")
    assert len(adbx) == 1
    assert adbx[0].un == "kg"
    assert adbx[0].qtd == pytest.approx(round(est.kg_liquido * 0.02), abs=1)


def test_adbx_usa_perda_perfil_pct_e_avisa_do_coef_da_composicao(con, projeto_109_estrutura):
    """Armadilha de 2%: a composição VK-C-001 já consome 1,02 kg de perfil por kg
    de estrutura — os MESMOS 2% do AD/BX. Precificar o acessório à parte infla o
    aço em 2% em silêncio (o v7 lista o item e NÃO o soma ao orçamento).

    Por isso a fração tem que sair de `perda_perfil_pct`, cuja referência no seed
    carrega o aviso — uma chave nova esconderia. E a peça tem que dizer isso na
    origem, porque quem for ligar acessório→EAP lê a origem, não este teste."""
    from lsf.geradores.estrutura import gerar_estrutura

    con2, pid = projeto_109_estrutura
    adbx = _itens(gerar_estrutura(con2, pid), "AD/BX")[0]

    assert "INFORMATIVO" in adbx.origem_regra
    assert "1,02" in adbx.origem_regra and "VK-C-001" in adbx.origem_regra

    # a regra é a mesma que o coeficiente da composição embute
    pct = con2.execute(
        "SELECT valor FROM regra_lsf WHERE chave = 'perda_perfil_pct'").fetchone()[0]
    coef = con2.execute(
        "SELECT ci.coeficiente FROM composicao_item ci"
        " JOIN composicao co ON co.id = ci.composicao_id"
        " WHERE co.codigo_fonte = 'VK-C-001' AND ci.coeficiente > 1").fetchone()[0]
    assert coef == pytest.approx(1 + pct / 100), (
        "o coeficiente da VK-C-001 e a perda_perfil_pct saíram de sincronia —"
        " um dos dois está contando o AD/BX errado")


def test_descoberta_gera_impermeabilizacao_e_guarda_corpo(projeto_109_estrutura):
    """As duas áreas descobertas da 109 (varanda em faixa + pátio)."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)

    imp = _itens(est, "Impermeabilização laje exposta")
    gc = _itens(est, "Guarda-corpo")
    assert len(imp) == 2 and len(gc) == 2
    assert all(a.un == "m²" for a in imp)
    assert all(a.un == "m" for a in gc)

    # faixa: guarda-corpo em d + 2w; pátio: perímetro inteiro
    faixa = con.execute(
        "SELECT w, d FROM area_descoberta WHERE tipo = 'faixa'").fetchone()
    esperado = round(faixa[1] + 2 * faixa[0], 1)
    assert any(a.qtd == pytest.approx(esperado, abs=0.15) for a in gc)


def test_sem_area_descoberta_nao_ha_impermeabilizacao(projeto_109_estrutura):
    """A regra segue o dado: sem laje exposta, sem serviço (nem item fantasma)."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    con.execute("DELETE FROM area_descoberta")
    est = gerar_estrutura(con, pid)
    assert _itens(est, "Impermeabilização") == []
    assert _itens(est, "Guarda-corpo") == []
