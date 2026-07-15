"""Conexão SQLite por request. Uma conexão por request; sem pool, sem ORM."""
from __future__ import annotations

import sqlite3

from fastapi import Request


def abrir(db_path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")   # D4.1 começa aqui: FK é lei, não sugestão
    con.row_factory = sqlite3.Row
    return con


def conexao(request: Request):
    """Dependência FastAPI: conexão viva durante o request, fechada ao final."""
    con = abrir(request.app.state.db_path)
    try:
        yield con
        con.commit()
    finally:
        con.close()
