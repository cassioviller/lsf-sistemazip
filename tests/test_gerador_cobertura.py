"""Task 8 — `gerar_cobertura`: porta fiel de v7:949-1041 (gerarPecasCobertura).

Duas águas ao longo de x sobre o footprint do 3º pav, recuado pela faixa de
varanda descoberta. Tesouras (banzos + montantes @0,40 + diagonais Pratt) no
grupo 1TS; painéis no plano inclinado no grupo 1CB.
"""
from collections import Counter

import pytest


def test_cobertura_pecas_por_grupo_tipo_e_perfil_batem_com_o_oraculo(
        projeto_109_estrutura, oraculo):
    from lsf.geradores.estrutura import gerar_cobertura

    con, _ = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura ORDER BY id LIMIT 1").fetchone()[0]
    pecas, _, _ = gerar_cobertura(con, cid)
    ref = oraculo["sistemas"]["cobertura"]["pecas"]
    assert (Counter((p.grupo, p.tipo, p.perfil) for p in pecas)
            == Counter((p["grupo"], p["tipo"], p["perfil"]) for p in ref))


def test_cobertura_kg_dentro_de_10pct_do_v7(projeto_109_estrutura, oraculo):
    from lsf.geradores.estrutura import _perfil, gerar_cobertura

    con, _ = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura ORDER BY id LIMIT 1").fetchone()[0]
    pecas, _, _ = gerar_cobertura(con, cid)
    kg = sum(p.comp * _perfil(con, p.perfil)["massa_kg_m"] for p in pecas)
    ref = oraculo["sistemas"]["cobertura"]["kg_liquido"]
    assert abs(kg - ref) <= 0.10 * ref


def test_cobertura_acessorios_batem_com_o_oraculo(projeto_109_estrutura, oraculo):
    """Telha desconta o pátio descoberto e aplica perda; gusset conta por nó."""
    from lsf.geradores.estrutura import gerar_cobertura

    con, _ = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura ORDER BY id LIMIT 1").fetchone()[0]
    _, acess, _ = gerar_cobertura(con, cid)
    obtido = {(a.item, a.un): a.qtd for a in acess}
    esperado = {(a["item"], a["un"]): a["qtd"]
                for a in oraculo["sistemas"]["cobertura"]["acess"]}
    assert obtido == esperado


def test_cobertura_area_descoberta_vira_alerta(projeto_109_estrutura):
    """Faixa de varanda recua o telhado e o pátio abre vão: os dois são alerta."""
    from lsf.geradores.estrutura import gerar_cobertura

    con, _ = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura ORDER BY id LIMIT 1").fetchone()[0]
    _, _, alertas = gerar_cobertura(con, cid)
    assert any("varanda" in a for a in alertas), alertas
    assert any("descoberta" in a for a in alertas), alertas


def test_cobertura_recua_o_telhado_pela_faixa_descoberta(projeto_109_estrutura, oraculo):
    """Sem o recuo, o telhado cobriria a varanda: nenhuma peça a oeste da faixa."""
    from lsf.geradores.estrutura import gerar_cobertura

    con, _ = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura ORDER BY id LIMIT 1").fetchone()[0]
    faixa = next(d for d in oraculo["projeto"]["descobertas"] if d["tipo"] == "faixa")
    limite = faixa["x"] + faixa["w"]
    pecas, _, _ = gerar_cobertura(con, cid)
    tesouras = [p for p in pecas if p.grupo == "1TS"]
    assert tesouras
    assert min(p.x0 for p in tesouras) == pytest.approx(limite, abs=1e-6)


def test_cobertura_confianca_nunca_melhor_que_estimado(projeto_109_estrutura):
    from lsf.geradores.estrutura import gerar_cobertura

    con, _ = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura ORDER BY id LIMIT 1").fetchone()[0]
    pecas, _, _ = gerar_cobertura(con, cid)
    assert pecas
    assert all(p.confianca in ("estimado", "parametrico") for p in pecas)
