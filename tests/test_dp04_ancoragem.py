"""REGRA DP-04 — ancoragem só no radier.

v7 (montarProjeto): `if(f.fi>0 && /Parabolt|Ancorador/i.test(a.item)) return;`
com o comentário "DP-04: ancoragem só no radier; sup.: painel-sobre-painel
[OBRA p.8-9]". Parede de pavimento superior não é chumbada no concreto — ela
aparafusa no painel de baixo. Sem esta regra a 109 orçava ancoragem para as 53
paredes em vez das 19 do térreo: 2.910 un contra 950, ou 3,06x de chumbador
Parabolt a mais no preço fechado.
"""
import pytest

ITENS_ANCORAGEM = ("Ancorador chapa #3,00 190x50x50",
                   'Chumbador Parabolt 5/16"x4-1/4"',
                   "Parafuso sextavado 4,8x19 (ancoradores)")


def _ancoragem(acessorios):
    return [a for a in acessorios if a.item in ITENS_ANCORAGEM]


def test_parede_do_terreo_leva_ancoragem(projeto_109_estrutura):
    from lsf.geradores.estrutura import gerar_parede

    con, pid = projeto_109_estrutura
    pid_terreo = con.execute(
        "SELECT p.id FROM parede p JOIN nivel n ON n.id = p.nivel_id"
        " WHERE n.projeto_id = ? AND n.indice = 0 ORDER BY p.id", (pid,)).fetchone()[0]
    assert _ancoragem(gerar_parede(con, pid_terreo).acessorios)


def test_parede_de_pavimento_superior_nao_leva_ancoragem(projeto_109_estrutura):
    """Painel-sobre-painel: quem ancora no radier é o térreo."""
    from lsf.geradores.estrutura import gerar_parede

    con, pid = projeto_109_estrutura
    pid_sup = con.execute(
        "SELECT p.id FROM parede p JOIN nivel n ON n.id = p.nivel_id"
        " WHERE n.projeto_id = ? AND n.indice > 0 ORDER BY p.id", (pid,)).fetchone()[0]
    assert _ancoragem(gerar_parede(con, pid_sup).acessorios) == []


def test_radier_e_o_menor_nivel_do_projeto_nao_o_indice_zero(projeto_109_estrutura):
    """Se o projeto for renumerado (subsolo em -1, ou pavimentos 1..3), a regra
    escrita como `indice == 0` sumiria com a ancoragem inteira em silêncio — o
    mesmo erro da DP-04, de sinal trocado. O radier é o MENOR nível."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    antes = sum(a.qtd for a in _ancoragem(gerar_estrutura(con, pid).acessorios))
    assert antes == pytest.approx(950)

    # renumera os pavimentos 0,1,2 → 1,2,3 (nenhum índice 0 sobra)
    for i in (2, 1, 0):
        con.execute("UPDATE nivel SET indice = ? WHERE projeto_id = ? AND indice = ?",
                    (i + 1, pid, i))
    depois = sum(a.qtd for a in _ancoragem(gerar_estrutura(con, pid).acessorios))
    assert depois == pytest.approx(antes), (
        "renumerar os pavimentos não pode mudar a ancoragem do prédio")


def test_ancoragem_do_edificio_bate_com_o_v7(projeto_109_estrutura):
    """Números da 109 medidos no v7 headless: 19 paredes de térreo ancoradas,
    950 unidades no total (ancorador + parabolt + parafusos)."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    anc = _ancoragem(est.acessorios)

    # 3 itens de ancoragem × 19 paredes de térreo
    assert len(anc) == 3 * 19
    assert sum(a.qtd for a in anc) == pytest.approx(950)
