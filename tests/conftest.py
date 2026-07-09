"""Fixtures comuns. Sem pyproject/instalação: `src/` entra no sys.path aqui."""
import pathlib
import sqlite3
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))


@pytest.fixture
def con():
    """Banco em memória, construído de schema.sql + seed.sql (nunca do artefato .db)."""
    c = sqlite3.connect(":memory:")
    c.executescript((RAIZ / "db" / "schema.sql").read_text())
    c.executescript((RAIZ / "db" / "seed.sql").read_text())
    for migracao in sorted((RAIZ / "db" / "migrations").glob("*.sql")):
        c.executescript(migracao.read_text())
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


@pytest.fixture
def base():
    """Referência travada pelo projeto (D5), no formato que o motor recebe."""
    return {"referencia": "2026-06", "uf": "SP", "desonerado": 0}


@pytest.fixture
def db_veks(con):
    """id da data-base VEKS/2026-06 — para cadastrar preços nos testes."""
    return con.execute(
        "SELECT db.id FROM data_base db JOIN fonte f ON f.id = db.fonte_id"
        " WHERE f.sigla = 'VEKS' AND db.referencia = '2026-06'"
    ).fetchone()[0]


@pytest.fixture
def id_de(con):
    """id_de('VK-C-001') -> id da composição; id_de.insumo('VK-I-001') -> id do insumo."""

    def composicao(codigo):
        return con.execute(
            "SELECT id FROM composicao WHERE codigo_fonte = ?", (codigo,)
        ).fetchone()[0]

    composicao.insumo = lambda codigo: con.execute(
        "SELECT id FROM insumo WHERE codigo_fonte = ?", (codigo,)
    ).fetchone()[0]
    return composicao
