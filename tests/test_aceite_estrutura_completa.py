"""Task 10 — kg do edifício inteiro (paredes + 4 sistemas) vs o v7.

CUIDADO ao ler este arquivo como "aceite da Fase 2". Há DUAS referências, e elas
não concordam:

  * `estrutura_v7_109_1506.json` (`total_edificio`) — o GERADOR do v7 rodado
    headless: 23.673 kg líquido / 27.412 kg comprado. É contra ela que os testes
    aqui medem, e o que eles provam é FIDELIDADE DA PORTA.
  * `orcamento_v7_109_1506.json` (`aco_comprado_kg`) — o aço REALMENTE COMPRADO
    da obra, quantidade MANUAL que fechou o aceite da Fase 1: 31.345 kg. É a
    referência que o CLAUDE.md nomeia no critério de aceite da Fase 2.

O líquido bate nas duas (23.673, 0,0%). O comprado não: nosso 25.710 fica -18,0%
da obra, e o PRÓPRIO v7 headless (27.412) fica -12,5%. Ou seja, nenhuma porta fiel
do gerador alcança o comprado da obra — a diferença é o modelo de perda/compra
(obra: 32,4% sobre o líquido; nesting em barra de 6 m: 8,6% global / 15,8% por
sistema), não a geometria. Fechar essa lacuna é calibração contra obra (R6) e é
decisão humana — ver `test_lacuna_do_kg_comprado_vs_obra_esta_medida`.
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


def test_lacuna_do_kg_comprado_vs_obra_esta_medida(projeto_109_estrutura):
    """Trava a lacuna REAL contra o critério do CLAUDE.md (≤10% vs 31.345 kg da
    obra), para que ela não passe despercebida nem seja 'fechada' por acidente.

    Hoje a lacuna existe e é conhecida (R6, calibração pendente): o líquido bate
    exato e o comprado fica ~18% abaixo do que a obra comprou. Se alguém calibrar
    a perda e fechar o gate, este teste falha e deve ser trocado por um aceite de
    verdade — falhar aqui é notícia BOA, mas exige o humano declarar a fase."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    obra = json.loads((pathlib.Path(__file__).parent / "fixtures"
                       / "orcamento_v7_109_1506.json").read_text())

    assert abs(est.kg_liquido - obra["aco_liquido_kg"]) / obra["aco_liquido_kg"] <= 0.10

    desvio = (est.kg_comprado - obra["aco_comprado_kg"]) / obra["aco_comprado_kg"]
    assert desvio < -0.10, (
        f"o kg comprado passou a ficar dentro de 10% da obra (desvio {desvio:.1%}). "
        "O gate da Fase 2 pode ter fechado — reavaliar com o humano e substituir "
        "este teste pelo aceite definitivo.")


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
