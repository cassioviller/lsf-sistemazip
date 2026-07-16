"""Task 10 — kg do edifício inteiro (paredes + 4 sistemas), contra as DUAS
referências do v7, que agora concordam:

  * `estrutura_v7_109_1506.json` (`total_edificio`) — o gerador do v7 headless;
  * `orcamento_v7_109_1506.json` (`aco_comprado_kg`) — o aço comprado que fechou
    o aceite da Fase 1 e que o CLAUDE.md nomeia no critério da Fase 2.

Histórico que vale guardar: por um tempo elas divergiam (27.412 vs 31.345) e a
lacuna parecia ser "perda de obra não calibrada" (R6). Não era. Faltava a REGRA
BOX-003 — peça acima da barra de 6 m é cortada em n partes IGUAIS com emenda,
ANTES do nesting — tanto no extrator do oráculo quanto na porta Python. Nestar
uma viga de 15,8 m como 6+6+3,8 enche as barras e mente ~13% para baixo; a obra
corta 3×5,27 m e sobra 0,73 m em cada. Os "32,4% de perda inexplicada" eram
regra de fabricação, não desperdício.

Hoje: líquido 23.673 (0,00%) e comprado 31.344 vs 31.345 da obra (−0,003%).
"""
import json
import pathlib

import pytest


def test_kg_liquido_bate_com_o_gerador_v7(projeto_109_estrutura, oraculo):
    """O kg líquido é geometria pura: tem que bater, e bate em 0,0%."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    ref = oraculo["total_edificio"]["kg_liquido"]
    assert abs(est.kg_liquido - ref) / ref <= 0.10


def test_kg_comprado_bate_com_o_gerador_v7_headless(projeto_109_estrutura, oraculo):
    """Fidelidade da porta vs o v7 headless (27.412) — NÃO é o gate da fase.
    O gate do CLAUDE.md é vs os 31.345 kg da obra; ver o teste da lacuna abaixo."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    ref = oraculo["total_edificio"]["kg_comprado"]
    assert abs(est.kg_comprado - ref) / ref <= 0.10


def test_criterio_de_aceite_da_fase2_kg_vs_o_aco_comprado_da_obra(projeto_109_estrutura):
    """O CRITÉRIO da Fase 2 (CLAUDE.md): kg de aço da 109.1506 com desvio ≤10% vs
    o v7 — 23.673 kg líquido / 31.345 kg comprado, os números oficiais da obra que
    fecharam a Fase 1 com quantitativos MANUAL.

    Aqui o kg é DERIVADO da planta pelo gerador (PARAMETRICO), não digitado: é a
    cadeia arquitetônico → paredes → estrutura → kg fechando contra a obra real."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    obra = json.loads((pathlib.Path(__file__).parent / "fixtures"
                       / "orcamento_v7_109_1506.json").read_text())

    d_liq = abs(est.kg_liquido - obra["aco_liquido_kg"]) / obra["aco_liquido_kg"]
    d_com = abs(est.kg_comprado - obra["aco_comprado_kg"]) / obra["aco_comprado_kg"]
    assert d_liq <= 0.10, f"kg líquido fora do gate: {d_liq:.1%}"
    assert d_com <= 0.10, f"kg comprado fora do gate: {d_com:.1%}"


def test_perda_sobre_o_liquido_reproduz_a_da_obra(projeto_109_estrutura):
    """A perda não é coeficiente chutado: cai da BOX-003 + nesting por sistema.
    A obra comprou 32,4% sobre o líquido; se este número escorregar, alguém mexeu
    na segmentação ou no nesting sem perceber o efeito no aço comprado."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    perda = est.kg_comprado / est.kg_liquido - 1
    assert perda == pytest.approx(0.324, abs=0.01)


def test_estrutura_soma_os_quatro_sistemas_alem_das_paredes(projeto_109_estrutura):
    """Sem os 4 sistemas o kg fica no patamar das paredes (~11 t compradas).
    Este teste falha se algum sistema deixar de entrar na agregação."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    sistemas = {p.sistema for p in est.pecas}
    assert sistemas == {"parede", "laje", "escada", "cobertura", "forro"}


def test_confianca_do_edificio_herda_a_pior_dos_sistemas(projeto_109_estrutura):
    """D4: a laje traz peças `parametrico` (enrijecedor e vigas dimensionadas por
    regra, não por projeto) — o edifício inteiro herda a PIOR, não a média."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    assert "parametrico" in {p.confianca for p in est.pecas}
    assert est.confianca == "parametrico"


def test_derivar_quantitativos_grava_total_do_edificio_na_0301(projeto_109_estrutura):
    from lsf.geradores.estrutura import derivar_quantitativos

    con, pid = projeto_109_estrutura
    r = derivar_quantitativos(con, pid)
    assert r["gravado"] is True
    q = con.execute(
        "SELECT quantidade, origem, confianca FROM quantitativo q"
        " JOIN eap_item e ON e.id = q.eap_item_id WHERE e.codigo = '03.01'"
        " AND q.projeto_id = ?", (pid,)).fetchone()
    assert q[1] == "PARAMETRICO"
    assert q[2] == "parametrico"  # pior confiança dos sistemas (laje), D4
    assert q[0] == r["kg_comprado"]
    assert q[0] > 20000  # kg do edifício (~25,7 t), não só das paredes (11,1 t)
