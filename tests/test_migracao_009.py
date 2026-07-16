"""Migração 009 + seed: escalonamento de perfil da laje (par viga/bloqueador).

O par é conhecimento de obra (listas 1L da 109.1506), não algoritmo: mora no
banco, como o verga_escalonamento. O `guia_de` genérico NÃO serve aqui — ele
elegeria U252#2.00 pela espessura do montante, e a lista real usa U252#1.25.
"""
import sqlite3

import pytest


def test_pares_da_laje_seedados_com_origem(con):
    linhas = con.execute(
        "SELECT faixa_ate_m, perfil_viga, perfil_bloqueador, origem"
        "  FROM laje_escalonamento ORDER BY faixa_ate_m").fetchall()
    assert [(l[0], l[1], l[2]) for l in linhas] == [
        (4.0, "Ue200#1.25", "U202#0.95"),
        (99.0, "Ue250#2.00", "U252#1.25"),
    ]
    assert all(l[3] for l in linhas), "par sem origem anotada"


def test_faixa_e_unica(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO laje_escalonamento (faixa_ate_m, perfil_viga,"
            " perfil_bloqueador) VALUES (4.0, 'Ue200#1.25', 'U202#0.95')")


def test_perfis_do_par_existem_em_perfil_lsf(con):
    """Par apontando para perfil inexistente = kg silenciosamente errado."""
    orfaos = con.execute(
        "SELECT e.perfil_viga, e.perfil_bloqueador FROM laje_escalonamento e"
        " WHERE e.perfil_viga NOT IN (SELECT codigo FROM perfil_lsf)"
        "    OR e.perfil_bloqueador NOT IN (SELECT codigo FROM perfil_lsf)").fetchall()
    assert orfaos == []


def test_primeira_faixa_casa_com_a_regra_do_limiar(con):
    """A faixa 4,0 m é o mesmo limiar da regra `laje_vao_ue200` (v7: vão ef > 4m
    → Ue250). Se um dos dois mudar sozinho, o outro está mentindo."""
    limiar = con.execute(
        "SELECT valor FROM regra_lsf WHERE chave='laje_vao_ue200'").fetchone()[0]
    primeira = con.execute(
        "SELECT MIN(faixa_ate_m) FROM laje_escalonamento").fetchone()[0]
    assert primeira == limiar
