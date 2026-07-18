"""REGRA BOX-003 — peça linear acima da barra comercial de 6 m é segmentada em
partes IGUAIS, com emenda rastreada, ANTES do plano de corte.

Porta do bloco de `montarProjeto` do v7 ("REGRA BOX-003: peça linear > barra
comercial (6m) → segmentar + emenda rastreada", regra `barra_m` = 6,0 m,
referência 'REGRA BOX-003 [mont. p.53: peça 8583mm → emenda/pré-corte]').

O detalhe que define o resultado: `n = ceil(comp/6)` e cada segmento vale
`comp/n` — partes iguais, NÃO 6+6+resto. Uma viga de 7,9 m vira 2×3,95 m, e cada
3,95 m deixa 2,05 m de sobra numa barra de 6 m. É essa regra — e não perda de
obra — que explica os 32,4% de aço comprado sobre o líquido na 109.
"""
import pytest


def test_peca_acima_da_barra_vira_n_partes_iguais(con):
    from lsf.geradores.estrutura import Peca, segmentar_box003

    p = Peca("1LJ-VIG1", "viga_laje", "Ue250#2.00", 0.0, 3.0, 15.8, 3.0, 15.8,
             "origem", "laje", "1LJ", 0.0, 0.0, "estimado")
    segs, emendas = segmentar_box003(con, [p])

    # comp é arredondado a 4 casas como no v7 (`+(p.comp/n).toFixed(4)`), então a
    # soma dos segmentos volta a 15,8 a menos de 1e-4 m — 0,1 mm, não aço perdido.
    assert len(segs) == 3                      # ceil(15,8/6)
    assert all(s.comp == pytest.approx(15.8 / 3, abs=1e-4) for s in segs)  # iguais
    assert sum(s.comp for s in segs) == pytest.approx(15.8, abs=1e-3)      # não cria aço
    assert emendas == {"laje": 2}              # n-1 emendas


def test_peca_dentro_da_barra_nao_e_tocada(con):
    from lsf.geradores.estrutura import Peca, segmentar_box003

    p = Peca("1LJ-VIG1", "viga_laje", "Ue250#2.00", 0.0, 3.0, 5.0, 3.0, 5.0,
             "origem", "laje", "1LJ", 0.0, 0.0, "estimado")
    segs, emendas = segmentar_box003(con, [p])
    assert segs == [p]
    assert emendas == {}


def test_segmento_fica_na_geometria_da_peca_original(con):
    """Os segmentos são a peça original repartida, não peças novas soltas: o
    primeiro começa onde ela começava e o último termina onde ela terminava."""
    from lsf.geradores.estrutura import Peca, segmentar_box003

    p = Peca("1CB-TRA1", "travessa_1CB", "Ue90#0.95", 0.0, 0.0, 12.0, 6.0, 13.4164,
             "origem", "cobertura", "1CB", 0.0, 0.0, "estimado")
    segs, _ = segmentar_box003(con, [p])

    assert (segs[0].x0, segs[0].y0, segs[0].z0) == (p.x0, p.y0, p.z0)
    assert (segs[-1].x1, segs[-1].y1, segs[-1].z1) == (p.x1, p.y1, p.z1)
    # emendam sem vão nem sobreposição
    for a, b in zip(segs, segs[1:]):
        assert (a.x1, a.y1, a.z1) == pytest.approx((b.x0, b.y0, b.z0))


def test_segmentacao_preserva_kg_liquido_e_encarece_o_comprado(projeto_109_estrutura):
    """O efeito da BOX-003: mesmo aço líquido, mais aço COMPRADO — porque 2×3,95m
    não cabem numa barra de 6m como 7,9m em emenda caberiam."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    assert est.kg_liquido == pytest.approx(23673, rel=0.001)
    assert est.kg_comprado > est.kg_liquido * 1.25


def test_emenda_de_perfil_vira_acessorio(projeto_109_estrutura):
    """A emenda é material: peça cortada em 3 precisa de 2 luvas."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    emendas = [a for a in est.acessorios if "Emenda" in a.item]
    assert emendas, "peça acima de 6m sem emenda no romaneio"
    assert sum(a.qtd for a in emendas) > 0
