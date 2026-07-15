"""Migração 005: tabelas de instância do app (usuario, proposta)."""
import sqlite3

import pytest


def test_usuario_email_unico(con):
    con.execute(
        "INSERT INTO usuario (email, senha_hash, nome) VALUES ('a@veks.com', 'x', 'A')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO usuario (email, senha_hash, nome) VALUES ('a@veks.com', 'y', 'B')"
        )


def _projeto(con):
    cur = con.execute(
        "INSERT INTO projeto (codigo, nome, cliente, referencia, uf, desonerado)"
        " VALUES ('109.1506', 'Edifício', 'Cliente X', '2026-06', 'SP', 0)"
    )
    return cur.lastrowid


def _usuario(con):
    cur = con.execute(
        "INSERT INTO usuario (email, senha_hash, nome) VALUES ('c@veks.com', 'x', 'C')"
    )
    return cur.lastrowid


def test_versao_unica_por_projeto(con):
    p, u = _projeto(con), _usuario(con)
    con.execute(
        "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
        " html, total_venda, bdi_pct) VALUES (?,1,'tok1',?,'{}','<h1/>',100.0,0.2779)",
        (p, u),
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
            " html, total_venda, bdi_pct) VALUES (?,1,'tok2',?,'{}','<h1/>',100.0,0.2779)",
            (p, u),
        )


def test_token_unico_entre_projetos(con):
    p, u = _projeto(con), _usuario(con)
    con.execute(
        "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
        " html, total_venda, bdi_pct) VALUES (?,1,'mesmo',?,'{}','<h1/>',100.0,0.2779)",
        (p, u),
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
            " html, total_venda, bdi_pct) VALUES (?,2,'mesmo',?,'{}','<h1/>',100.0,0.2779)",
            (p, u),
        )


def test_status_so_aceita_ativa_ou_revogada(con):
    p, u = _projeto(con), _usuario(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
            " html, total_venda, bdi_pct, status)"
            " VALUES (?,1,'t',?,'{}','<h1/>',100.0,0.2779,'rascunho')",
            (p, u),
        )


def test_proposta_exige_total_de_venda(con):
    """D4.1 na fronteira do banco: proposta sem preço não existe."""
    p, u = _projeto(con), _usuario(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
            " html, bdi_pct) VALUES (?,1,'t',?,'{}','<h1/>',0.2779)",
            (p, u),
        )
