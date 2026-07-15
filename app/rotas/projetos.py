"""Projetos. Stub protegido — a Task 4 troca pelo CRUD real.

Existe já na Task 3 porque /projetos é o destino do login e a rota protegida
que prova o redirecionamento de sessão ausente.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import usuario_logado
from app.db import conexao

router = APIRouter()


@router.get("/projetos", response_class=HTMLResponse)
def listar(
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    return HTMLResponse("<h1>Projetos</h1>")
