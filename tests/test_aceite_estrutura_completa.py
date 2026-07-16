"""Task 10 — aceite da Fase 2: kg do edifício inteiro (paredes + 4 sistemas).

Referência headless do v7 em `tests/fixtures/estrutura_v7_109_1506.json`
(`total_edificio`): 23.673 kg líquido / 27.412 kg comprado. Critério: ≤10%.
"""
import pytest


def test_kg_liquido_do_edificio_dentro_de_10pct(projeto_109_estrutura, oraculo):
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    ref = oraculo["total_edificio"]["kg_liquido"]
    assert abs(est.kg_liquido - ref) / ref <= 0.10


def test_kg_comprado_do_edificio_dentro_de_10pct(projeto_109_estrutura, oraculo):
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    ref = oraculo["total_edificio"]["kg_comprado"]
    assert abs(est.kg_comprado - ref) / ref <= 0.10


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
