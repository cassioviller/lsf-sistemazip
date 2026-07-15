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


def _tipos(r):
    t = {}
    for p in r.pecas:
        t[p.tipo] = t.get(p.tipo, 0) + 1
    return t


def test_porta_estreita_king_e_jack_simples(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=4.0, vaos=[{"tipo": "PORTA", "posicao_m": 1.5,
                                  "largura_m": 0.9, "altura_m": 2.1}])
    t = _tipos(gerar_parede(con, pid))
    assert t["king"] == 2 and t["jack"] == 2          # 1 por lado (0.9m <= 2.0m)
    assert t["verga_mont"] == 2 and t["verga_guia"] == 2   # caixa da verga


def test_vao_largo_king_e_jack_duplos_e_verga_escalonada(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=8.0, vaos=[{"tipo": "PORTA", "posicao_m": 2.0,
                                  "largura_m": 2.5, "altura_m": 2.1}])
    r = gerar_parede(con, pid)
    t = _tipos(r)
    assert t["king"] == 4 and t["jack"] == 4          # 2 por lado (2.5m > 2.0m)
    vergas = [p for p in r.pecas if p.tipo == "verga_mont"]
    assert all(p.perfil == "Ue250#2.00" for p in vergas)   # faixa >2.0m


def test_janela_tem_peitoril_e_cripples_dos_dois_lados(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=4.0, vaos=[{"tipo": "JANELA", "posicao_m": 1.2,
                                  "largura_m": 1.6, "altura_m": 1.2,
                                  "peitoril_m": 1.0}])
    r = gerar_parede(con, pid)
    t = _tipos(r)
    assert t["peitoril"] == 1
    # modulação 0.40 dentro do vão [1.2, 2.8]: x=1.6, 2.0, 2.4 → 3 cripples
    # em cima (sobre a verga) e 3 embaixo (sob o peitoril)
    assert t["cripple"] == 6
    # vão 1.6m >= diag_sobre_verga_min 1.0m → diagonais entre os nós dos cripples
    assert t["diagonal"] == 4                          # 3 cripples → 4 segmentos


def test_vao_pequeno_nao_ganha_diagonal_sobre_verga(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=4.0, vaos=[{"tipo": "PORTA", "posicao_m": 1.5,
                                  "largura_m": 0.9, "altura_m": 2.1}])
    assert "diagonal" not in _tipos(gerar_parede(con, pid))


def test_vao_que_nao_cabe_vira_alerta_e_sai_do_desenho(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=2.0, vaos=[{"tipo": "PORTA", "posicao_m": 0.1,
                                  "largura_m": 1.9, "altura_m": 2.1}])
    r = gerar_parede(con, pid)
    assert any("não cabe" in a for a in r.alertas)
    assert "king" not in _tipos(r)


def test_junta_de_painel_desvia_do_vao(con, planta):
    """A regra que custou caro: junta NUNCA a menos de 30cm da lateral de um vão."""
    from lsf.geradores.estrutura import gerar_parede

    # comp=7.2 → 2 painéis, junta natural em 3.6 — bem no meio de um vão [3.0, 4.2]
    pid = planta(comp=7.2, vaos=[{"tipo": "PORTA", "posicao_m": 3.0,
                                  "largura_m": 1.2, "altura_m": 2.1}])
    r = gerar_parede(con, pid)
    assert len(r.juntas) == 1
    xj = r.juntas[0]
    assert not (3.0 - 0.14 < xj < 4.2 + 0.14)          # fora do vão + folga
    # junta natural em 3.6 está EQUIDISTANTE das laterais (0.6 de cada); o v7
    # usa `<` estrito e empata para a DIREITA: min(comp-0.3, 4.2+0.15)
    assert xj == pytest.approx(4.35, abs=0.01)
