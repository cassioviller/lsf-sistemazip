"""Verificação de vento/ancoragem (NBR 6123 simplificada — cálculo próprio
autorizado em 2026-07-18; envelope conservador, generalizado da planta em vez
das dimensões chumbadas do v7)."""
import pytest

from lsf.geradores.estrutura import DadoIndisponivel
from lsf.motores.fundacao import verificar_vento


def _solo(con, pid, classe="S3"):
    con.execute(
        "UPDATE projeto SET classe_solo_id ="
        " (SELECT id FROM classe_solo WHERE classe = ?) WHERE id = ?",
        (classe, pid))
    con.commit()


def test_caixa_6x4_na_conta_de_mao(con, caixa_6x4):
    """F = q·altura·largura_da_fachada_normal [NBR 6123 simplificada]:
    dir x → fachada de 4 m: 0,61 × 3,10 × 4 =  7,56 kN
    dir z → fachada de 6 m: 0,61 × 3,10 × 6 = 11,35 kN
    Por linha (2 linhas): máx 5,67 kN ÷ 17,9 kN/fita → 1 fita; adota o mínimo 3."""
    pid, _ = caixa_6x4
    r = verificar_vento(con, pid)
    forcas = {d.direcao: d.f_kn for d in r.direcoes}
    assert forcas["x"] == pytest.approx(7.56, abs=0.05)
    assert forcas["z"] == pytest.approx(11.35, abs=0.05)
    for d in r.direcoes:
        assert d.fitas_necessarias == 1
        assert d.fitas_adotadas == 3          # nunca abaixo do mínimo da norma
    assert not r.pendencias
    assert r.confianca == "parametrico"
    assert "NBR 6123" in r.origem_regra


def test_109_reproduz_a_ordem_do_v7(projeto_109_estrutura):
    """No v7: F ≈ 101 kN (com 10,5 m chumbados) → 'mínimo 3 fitas X por linha'.
    Generalizado da planta: altura 7,07+3,10−0,57 = 9,6 m, fachadas 15,8/14,3 m
    → F máx = 0,61 × 9,6 × 15,8 = 92,5 kN → 92,5/(2×17,9) = 2,58 → 3 fitas.
    Mesma conclusão da obra, sem dimensão chumbada."""
    con, pid = projeto_109_estrutura
    r = verificar_vento(con, pid)
    assert max(d.f_kn for d in r.direcoes) == pytest.approx(92.5, abs=1.0)
    assert all(d.fitas_necessarias == 3 for d in r.direcoes)
    assert not r.pendencias                   # 3 necessárias ≤ 3 mínimas


def test_hold_downs_sao_por_extremo_de_linha_e_canto(con, caixa_6x4):
    """4 linhas × 2 extremos × 2 un + 4 cantos × 2 un = 24 — a MESMA conta que
    fecha os 24 un do v7 na 109, derivada em vez de chumbada."""
    pid, _ = caixa_6x4
    assert verificar_vento(con, pid).hold_downs_un == 24


def test_demanda_acima_do_minimo_vira_pendencia(con, caixa_6x4):
    """Se a pressão de vento subir (ou o prédio crescer) até as 3 fitas mínimas
    não fecharem, isso NÃO pode sair calado: pendência com o n necessário."""
    pid, _ = caixa_6x4
    con.execute("UPDATE regra_lsf SET valor = 15.0"
                " WHERE chave = 'vento_pressao_kn_m2'")
    con.commit()
    r = verificar_vento(con, pid)
    assert r.pendencias
    assert any("fitas" in p and "3" in p for p in r.pendencias)


def test_sem_paredes_externas_e_erro(con):
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, desonerado)"
        " VALUES ('SEM-EXT', 'x', '2026-06', 0)")
    pid = con.execute("SELECT id FROM projeto WHERE codigo='SEM-EXT'").fetchone()[0]
    con.commit()
    with pytest.raises(DadoIndisponivel):
        verificar_vento(con, pid)
