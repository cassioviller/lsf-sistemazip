"""Acessórios de instalações — porta de `gerarAcessoriosInstalacoes` (v7).

Fecha os 4 últimos itens que a auditoria contra o v7 headless apontou como
ausentes na porta. Precisou de schema (migração 011): a contagem de pontos
hidro/gás/elétrica é input de PROJETO, como o solo — o arquitetônico não a dá.

O furo em viga é o ponto sensível: a REGRA HID-FURO-001/003 limita a 12 cm ou
h/3 na zona de tração. Furo acima disso não é acessório, é decisão estrutural —
por isso vira alerta marcado como pendência, não um item silencioso na lista.
"""
import pytest


def _itens(acess, trecho):
    return [a for a in acess if trecho.lower() in a.item.lower()]


def test_furo_de_servico_e_parafusos_por_ponto(projeto_109_estrutura):
    """n = hidro+gás+ele = 14+2+0 = 16 pontos → 32 furos → 32*8 = 256 parafusos."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)

    furos = _itens(est.acessorios, "Furo de serviço")
    paraf = _itens(est.acessorios, "chapas de reforço")
    assert len(furos) == 1 and furos[0].qtd == 32
    assert len(paraf) == 1 and paraf[0].qtd == 256


def test_tubo_luva_so_com_ponto_de_gas(projeto_109_estrutura):
    """2 pontos de GLP × 2,5 m = 5 m. Sem gás, o item não existe."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    luva = _itens(est.acessorios, "Tubo-luva PVC")
    assert len(luva) == 1 and luva[0].qtd == pytest.approx(5.0)
    assert any("Gás" in a or "gás" in a for a in est.alertas)

    con.execute("UPDATE instalacao SET pontos_gas = 0 WHERE projeto_id = ?", (pid,))
    assert _itens(gerar_estrutura(con, pid).acessorios, "Tubo-luva PVC") == []


def test_furo_critico_vira_chapa_de_reforco_e_pendencia(projeto_109_estrutura):
    """A 109 tem 1 furo crítico numa viga de 0,25 m da 1LJ. O v7 marca sev='alta';
    aqui isso é PENDÊNCIA ESTRUTURAL — furo em viga não passa calado."""
    from lsf.geradores.estrutura import MARCA_PENDENCIA, gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)

    chapas = _itens(est.acessorios, "Chapa de reforço p/ furo crítico")
    assert len(chapas) == 1 and chapas[0].qtd == 1
    assert chapas[0].sistema == "laje"

    pend = [p for p in est.pendencias_estruturais if "furo" in p.lower()]
    assert pend, "furo em viga tem que virar pendência, não item silencioso"
    assert all(p.startswith(MARCA_PENDENCIA) for p in pend)
    # limite = min(12cm, h/3) → viga de 0,25m: h/3 = 83mm < 120mm → 83mm
    assert "83" in pend[0]


def test_projeto_sem_instalacoes_nao_inventa_acessorio(projeto_109_estrutura):
    """Sem pontos cadastrados não há furo nem luva — e nada de item fantasma."""
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    con.execute("DELETE FROM furo_critico")
    con.execute("DELETE FROM instalacao")
    est = gerar_estrutura(con, pid)
    for trecho in ("Furo de serviço", "Tubo-luva", "chapas de reforço"):
        assert _itens(est.acessorios, trecho) == []
