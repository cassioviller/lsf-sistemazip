"""planta_normalizada (migração 004): grafo níveis/nós/paredes/vãos com D4.
Só o schema — os motores da Fase 2 (gerador de estrutura, cargas) vêm depois."""
import sqlite3

import pytest


@pytest.fixture
def projeto(con):
    return con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf) VALUES ('P1', 'teste', '2026-06', 'SP')"
    ).lastrowid


@pytest.fixture
def terreo(con, projeto):
    return con.execute(
        "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m) VALUES (?, 0, 'Térreo', 2.8)",
        (projeto,),
    ).lastrowid


def _no(con, nivel, x, y):
    return con.execute(
        "INSERT INTO no_planta (nivel_id, x, y, confianca) VALUES (?, ?, ?, 'real')",
        (nivel, x, y),
    ).lastrowid


def test_parede_em_l_compartilha_no(con, terreo):
    """Duas paredes em L: 3 nós, canto compartilhado — a estrutura do grafo."""
    a, b, c = _no(con, terreo, 0, 0), _no(con, terreo, 6, 0), _no(con, terreo, 0, 4)
    for no1, no2 in ((a, b), (a, c)):
        con.execute(
            "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, origem, confianca)"
            " VALUES (?, ?, ?, 0.14, 'MANUAL', 'real')",
            (terreo, no1, no2),
        )
    grau = con.execute(
        "SELECT COUNT(*) FROM parede WHERE no_a = ? OR no_b = ?", (a, a)
    ).fetchone()[0]
    assert grau == 2  # o canto é um nó de grau 2, não dois pontos duplicados


def test_vao_dentro_da_parede(con, terreo):
    a, b = _no(con, terreo, 0, 0), _no(con, terreo, 9.2, 0)
    pid = con.execute(
        "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, origem) "
        " VALUES (?, ?, ?, 0.14, 'MANUAL')",
        (terreo, a, b),
    ).lastrowid
    con.execute(
        "INSERT INTO vao (parede_id, tipo, posicao_m, largura_m, altura_m, peitoril_m)"
        " VALUES (?, 'JANELA', 3.0, 1.2, 1.2, 1.0)",
        (pid,),
    )
    assert con.execute("SELECT COUNT(*) FROM vao").fetchone()[0] == 1


def _falha(con, sql, args):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(sql, args)


def test_parede_degenerada_mesmo_no_falha(con, terreo):
    a = _no(con, terreo, 0, 0)
    _falha(con, "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, origem)"
                " VALUES (?, ?, ?, 0.14, 'MANUAL')", (terreo, a, a))


def test_parede_com_nos_de_niveis_diferentes_falha(con, projeto, terreo):
    superior = con.execute(
        "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m) VALUES (?, 1, '1º pav', 2.8)",
        (projeto,),
    ).lastrowid
    a, b = _no(con, terreo, 0, 0), _no(con, superior, 6, 0)
    _falha(con, "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, origem)"
                " VALUES (?, ?, ?, 0.14, 'MANUAL')", (terreo, a, b))


def test_dominios_e_checks(con, terreo):
    a, b = _no(con, terreo, 0, 0), _no(con, terreo, 6, 0)
    casos = [
        ("espessura zero", "INSERT INTO parede (nivel_id,no_a,no_b,espessura_m,origem)"
                           " VALUES (?,?,?,0,'MANUAL')", (terreo, a, b)),
        ("origem inválida", "INSERT INTO parede (nivel_id,no_a,no_b,espessura_m,origem)"
                            " VALUES (?,?,?,0.14,'CHUTE')", (terreo, a, b)),
        ("perfil inexistente", "INSERT INTO parede (nivel_id,no_a,no_b,espessura_m,origem,perfil_codigo)"
                               " VALUES (?,?,?,0.14,'MANUAL','Ue999#9')", (terreo, a, b)),
        ("nível duplicado", "INSERT INTO nivel (projeto_id,indice,nome,pe_direito_m)"
                            " SELECT projeto_id, 0, 'de novo', 2.8 FROM nivel LIMIT 1", ()),
    ]
    for rotulo, sql, args in casos:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql, args), rotulo


def test_regras_de_panelizacao_estao_no_banco(con):
    """A régua comercial da colheita virou dado consultável, não constante em código."""
    regras = dict(con.execute(
        "SELECT chave, valor FROM regra_lsf WHERE chave LIKE '%painel%' OR chave LIKE 'junta_%'"
    ))
    assert regras == {
        "largura_painel_max_m": 3.6,
        "painel_comp_max_transporte_m": 6.0,
        "junta_folga_vao_m": 0.30,
        "largura_painel_min_m": 0.60,
        "passo_conex_painel_m": 0.20,
    }
