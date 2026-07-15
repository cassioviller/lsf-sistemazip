"""Login e logout. Sem cadastro aberto: usuário nasce por tools/criar_usuario.py."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import autenticar
from app.db import conexao

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def form_login(request: Request):
    return request.app.state.templates.TemplateResponse(
        request, "login.html", {"erro": None}
    )


@router.post("/login")
def entrar(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    con: sqlite3.Connection = Depends(conexao),
):
    usuario = autenticar(con, email, senha)
    if usuario is None:
        return request.app.state.templates.TemplateResponse(
            request, "login.html", {"erro": "E-mail ou senha inválidos."}, status_code=401
        )
    request.session["usuario_id"] = usuario["id"]
    return RedirectResponse("/projetos", status_code=303)


@router.post("/logout")
def sair(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
