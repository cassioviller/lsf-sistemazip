"""Task 7 — `gerar_escada`: porta fiel de v7:893-946 (gerarPecasEscada).

U com 2 lances + patamar. As duas escadas da 109.1506 compartilham o grupo 1ES,
então a comparação com o oráculo é feita no agregado das duas.
"""
from collections import Counter


def _todas(con):
    from lsf.geradores.estrutura import gerar_escada

    pecas, acess, alertas = [], [], []
    for (eid,) in con.execute("SELECT id FROM escada ORDER BY id").fetchall():
        p, a, al = gerar_escada(con, eid)
        pecas += p
        acess += a
        alertas += al
    return pecas, acess, alertas


def test_escada_pecas_por_tipo_e_perfil_batem_com_o_oraculo(projeto_109_estrutura, oraculo):
    con, _ = projeto_109_estrutura
    pecas, _, _ = _todas(con)
    ref = oraculo["sistemas"]["escada"]["pecas"]
    assert (Counter((p.tipo, p.perfil) for p in pecas)
            == Counter((p["tipo"], p["perfil"]) for p in ref))


def test_escada_kg_dentro_de_10pct_do_v7(projeto_109_estrutura, oraculo):
    from lsf.geradores.estrutura import _perfil

    con, _ = projeto_109_estrutura
    pecas, _, _ = _todas(con)
    kg = sum(p.comp * _perfil(con, p.perfil)["massa_kg_m"] for p in pecas)
    ref = oraculo["sistemas"]["escada"]["kg_liquido"]
    assert abs(kg - ref) <= 0.10 * ref


def test_escada_acessorios_batem_com_o_oraculo(projeto_109_estrutura, oraculo):
    con, _ = projeto_109_estrutura
    _, acess, _ = _todas(con)
    obtido = sorted((a.item, a.qtd, a.un) for a in acess)
    esperado = sorted((a["item"], a["qtd"], a["un"])
                      for a in oraculo["sistemas"]["escada"]["acess"])
    assert obtido == esperado


def test_escada_geometria_bate_com_o_info_do_v7(projeto_109_estrutura, oraculo):
    """nDeg/espelho/piso são o coração do dimensionamento — o v7 os expõe em _info."""
    from lsf.geradores.estrutura import gerar_escada

    con, _ = projeto_109_estrutura
    ids = [r[0] for r in con.execute("SELECT id FROM escada ORDER BY id").fetchall()]
    for eid, ref in zip(ids, oraculo["projeto"]["escadas"]):
        _, _, _, info = gerar_escada(con, eid, com_info=True)
        assert info["n_degraus"] == ref["_info"]["nDeg"]
        assert info["espelho"] == ref["_info"]["espelho"]
        assert info["piso"] == ref["_info"]["piso"]


def test_escada_confianca_nunca_melhor_que_estimado(projeto_109_estrutura):
    con, _ = projeto_109_estrutura
    pecas, _, _ = _todas(con)
    assert pecas
    assert all(p.confianca in ("estimado", "parametrico") for p in pecas)


def test_escada_piso_apertado_vira_alerta(projeto_109_estrutura, con):
    """Poço curto força piso < mínimo: isso é alerta, não silêncio (v7 warns)."""
    from lsf.geradores.estrutura import gerar_escada

    con, pid = projeto_109_estrutura
    eid = con.execute("SELECT id FROM escada ORDER BY id LIMIT 1").fetchone()[0]
    con.execute("UPDATE escada SET vao_w = 1.2, vao_d = 1.0 WHERE id = ?", (eid,))
    _, _, alertas = gerar_escada(con, eid)
    assert any("piso" in a for a in alertas), alertas
