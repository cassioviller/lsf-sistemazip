"""Migração 008: tabelas de projeto da estrutura — laje/escada/cobertura/
area_descoberta/forro. Inputs que o arquitetônico não dá (esp de laje,
inclinação de cobertura, vãos de escada, áreas descobertas). O footprint NÃO
é gravado — deriva das paredes externas (D3). Instância da 109.1506 é
seedada por fixture em tarefa futura, não aqui."""
import sqlite3

import pytest

from db.build_db import construir


def _cols(con, tabela):
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}


def test_tabelas_de_projeto_existem(tmp_path):
    dbp = tmp_path / "t.db"
    construir(dbp)  # construir(db_path: pathlib.Path, recriar=False) -> dict
    con = sqlite3.connect(dbp)
    tabelas = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"laje", "laje_abertura", "laje_extensao", "escada",
            "cobertura", "area_descoberta", "forro"} <= tabelas


def test_laje_tem_colunas_esperadas(tmp_path):
    dbp = tmp_path / "t.db"
    construir(dbp)  # construir(db_path: pathlib.Path, recriar=False) -> dict
    con = sqlite3.connect(dbp)
    assert {"projeto_id", "id_laje", "grupo", "pav_base", "nivel", "esp_m",
            "perfil_viga", "perfil_enrijecedor", "bloqueador_max_m",
            "confianca"} <= _cols(con, "laje")


def test_cobertura_referencia_perfis_por_texto(tmp_path):
    dbp = tmp_path / "t.db"
    construir(dbp)  # construir(db_path: pathlib.Path, recriar=False) -> dict
    con = sqlite3.connect(dbp)
    assert {"banzo_perfil", "alma_perfil", "guia_banzo_perfil",
            "inclinacao", "beiral_m", "confianca"} <= _cols(con, "cobertura")


def test_area_descoberta_check_tipo(tmp_path):
    dbp = tmp_path / "t.db"
    construir(dbp)  # construir(db_path: pathlib.Path, recriar=False) -> dict
    con = sqlite3.connect(dbp)
    pid = con.execute(
        "INSERT INTO projeto (codigo,nome,referencia,uf,desonerado)"
        " VALUES ('X','x','2024-01','SP',1)").lastrowid
    con.execute("INSERT INTO area_descoberta (projeto_id,nome,x,z,w,d,tipo,confianca)"
                " VALUES (?,?,?,?,?,?,?,?)", (pid, "v", 0, 0, 1, 1, "faixa", "estimado"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO area_descoberta (projeto_id,nome,x,z,w,d,tipo,confianca)"
                    " VALUES (?,?,?,?,?,?,?,?)", (pid, "q", 0, 0, 1, 1, "porao", "estimado"))
