"""Task 6 — `gerar_laje`: porta fiel de v7:801-889 (gerarPecasLaje).

O oráculo fixa a contagem por tipo peça a peça: divergência aqui é erro de port
num `scan`/`cortar_span`/passo, não "tolerância de modelagem".
"""
from collections import Counter

import pytest


def _kg(con, pecas):
    from lsf.geradores.estrutura import _perfil

    return sum(p.comp * _perfil(con, p.perfil)["massa_kg_m"] for p in pecas)


def _laje_id(con, id_laje):
    return con.execute("SELECT id FROM laje WHERE id_laje = ?", (id_laje,)).fetchone()[0]


def test_contorno_pavimento_deriva_o_footprint_das_paredes_externas(
        projeto_109_estrutura, oraculo):
    """O footprint NÃO é dado de entrada: sai das paredes externas (D3)."""
    from lsf.geradores.estrutura import contorno_pavimento

    con, pid = projeto_109_estrutura
    for pav in (0, 1, 2):
        assert contorno_pavimento(con, pid, pav) == [
            tuple(p) for p in oraculo["projeto"]["footprint"][pav]]


@pytest.mark.parametrize("grupo", ["1LJ", "2LJ"])
def test_laje_pecas_por_tipo_batem_com_o_oraculo(projeto_109_estrutura, oraculo, grupo):
    from lsf.geradores.estrutura import gerar_laje

    con, _ = projeto_109_estrutura
    pecas, _, _ = gerar_laje(con, _laje_id(con, grupo))
    ref = [p for p in oraculo["sistemas"]["laje"]["pecas"] if p["grupo"] == grupo]
    assert Counter(p.tipo for p in pecas) == Counter(p["tipo"] for p in ref)


@pytest.mark.parametrize("grupo", ["1LJ", "2LJ"])
def test_laje_perfil_por_peca_bate_com_o_oraculo(projeto_109_estrutura, oraculo, grupo):
    """Escalonamento do perfil (vão efetivo → Ue200/Ue250) e par viga/bloqueador."""
    from lsf.geradores.estrutura import gerar_laje

    con, _ = projeto_109_estrutura
    pecas, _, _ = gerar_laje(con, _laje_id(con, grupo))
    ref = [p for p in oraculo["sistemas"]["laje"]["pecas"] if p["grupo"] == grupo]
    assert (Counter((p.tipo, p.perfil) for p in pecas)
            == Counter((p["tipo"], p["perfil"]) for p in ref))


def test_laje_kg_total_dentro_de_10pct_do_v7(projeto_109_estrutura, oraculo):
    from lsf.geradores.estrutura import gerar_laje

    con, _ = projeto_109_estrutura
    todas = []
    for (lid,) in con.execute("SELECT id FROM laje ORDER BY id").fetchall():
        pecas, _, _ = gerar_laje(con, lid)
        todas += pecas
    ref = oraculo["sistemas"]["laje"]["kg_liquido"]
    assert abs(_kg(con, todas) - ref) <= 0.10 * ref


def test_laje_acessorios_batem_com_o_oraculo(projeto_109_estrutura, oraculo):
    """Parafusos por bloqueador/enrijecedor e chapa de piso pela área do polígono."""
    from lsf.geradores.estrutura import gerar_laje

    con, _ = projeto_109_estrutura
    acess = []
    for (lid,) in con.execute("SELECT id FROM laje ORDER BY id").fetchall():
        _, a, _ = gerar_laje(con, lid)
        acess += a
    obtido = {(a.item, a.un): a.qtd for a in acess}
    esperado = {(a["item"], a["un"]): a["qtd"] for a in oraculo["sistemas"]["laje"]["acess"]}
    assert obtido == esperado


def test_laje_alerta_de_viga_laminada_nao_e_silencioso(projeto_109_estrutura):
    """A 109.1506 reprova até viga dupla (v7: modo 'laminada') — isso vira alerta."""
    from lsf.geradores.estrutura import gerar_laje

    con, _ = projeto_109_estrutura
    _, _, alertas = gerar_laje(con, _laje_id(con, "1LJ"))
    assert any("laminada" in a for a in alertas), alertas


def test_laje_confianca_nunca_melhor_que_estimado(projeto_109_estrutura):
    """Regras sem calibração de obra: nenhuma peça sai como 'real' (D4)."""
    from lsf.geradores.estrutura import gerar_laje

    con, _ = projeto_109_estrutura
    pecas, _, _ = gerar_laje(con, _laje_id(con, "1LJ"))
    assert pecas
    assert all(p.confianca in ("estimado", "parametrico") for p in pecas)


def test_peca_de_parede_continua_com_comp_2d(con, planta):
    """`Peca` ganhou z0/z1: parede fica em z=0 e o comp não pode mudar (hypot 3D)."""
    import math

    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=4.0, pd=3.10))
    assert r.pecas
    for p in r.pecas:
        assert p.z0 == 0.0 and p.z1 == 0.0
        assert p.comp == pytest.approx(math.hypot(p.x1 - p.x0, p.y1 - p.y0), abs=1e-4)
