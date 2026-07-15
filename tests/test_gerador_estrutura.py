"""Gerador de estrutura de paredes — porta fiel do gerarPecas do v7 (unitários)."""
import pytest


def test_parede_lisa_tem_guias_montantes_e_extremos(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=2.0, pd=3.10))          # 1 painel, sem vãos
    tipos = {}
    for p in r.pecas:
        tipos[p.tipo] = tipos.get(p.tipo, 0) + 1
    assert tipos["guia"] == 2                                  # TBOT + TTOP (2m < barra 6m)
    assert tipos["montante_ext"] == 2                          # x=0 e x=comp
    assert tipos["montante"] == 4                              # 0.40, 0.80, 1.20, 1.60
    assert r.n_paineis == 1 and r.juntas == []


def test_parede_longa_panelizada_com_montantes_de_junta(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=7.0))                    # ceil(7/3.6) = 2 painéis
    assert r.n_paineis == 2
    assert r.juntas == [3.5]
    # cada junta traz um PAR de montantes de borda [OBRA layout]
    extras = [p for p in r.pecas if p.tipo == "montante_ext" and 3.3 < p.x0 < 3.7]
    assert len(extras) == 2
    # guias por painel: 2 painéis × (TBOT+TTOP), cada segmento < 6m
    assert sum(1 for p in r.pecas if p.tipo == "guia") == 4


def test_guia_de_parede_muito_longa_segmenta_em_barras_de_6m(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=13.0))                   # 4 painéis de 3.25m
    guias = [p for p in r.pecas if p.tipo == "guia"]
    assert all(p.comp <= 6.0 + 1e-9 for p in guias)


def test_perfil_ausente_e_erro_nao_silencio(con, planta):
    from lsf.geradores.estrutura import DadoIndisponivel, gerar_parede

    pid = planta()
    con.execute("UPDATE parede SET perfil_codigo = NULL WHERE id = ?", (pid,))
    with pytest.raises(DadoIndisponivel):
        gerar_parede(con, pid)


def _degenerada(con, planta):
    """Nós distintos no MESMO ponto: passa no CHECK (no_a<>no_b compara ids),
    mas comp=0 — o gerador tem que recusar."""
    planta()                                       # garante nível existente
    nivel_id = con.execute("SELECT id FROM nivel LIMIT 1").fetchone()[0]
    a = con.execute("INSERT INTO no_planta (nivel_id,x,y) VALUES (?,1,1)", (nivel_id,)).lastrowid
    b = con.execute("INSERT INTO no_planta (nivel_id,x,y) VALUES (?,1,1)", (nivel_id,)).lastrowid
    return con.execute(
        "INSERT INTO parede (nivel_id,no_a,no_b,espessura_m,portante,externa,"
        " perfil_codigo,origem,confianca) VALUES (?,?,?,0.14,1,0,'Ue90#0.95','MANUAL','real')",
        (nivel_id, a, b),
    ).lastrowid


def test_parede_degenerada_e_erro(con, planta):
    from lsf.geradores.estrutura import DadoIndisponivel, gerar_parede

    with pytest.raises(DadoIndisponivel):
        gerar_parede(con, _degenerada(con, planta))


def test_confianca_propagada_pior_dos_inputs(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(confianca="estimado")
    assert gerar_parede(con, pid).confianca == "estimado"
