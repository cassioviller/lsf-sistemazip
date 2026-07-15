"""Fábrica do app. O db_path é injetado — é o que permite o TestClient rodar
contra um banco temporário sem variável de ambiente global."""
from __future__ import annotations

import os
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NaoAutenticado, redirecionar_ao_login
from app.rotas import auth as rotas_auth
from app.rotas import projetos as rotas_projetos
from app.rotas import orcamento as rotas_orcamento
from app.rotas import quantitativos as rotas_quantitativos

AQUI = pathlib.Path(__file__).parent
RAIZ = AQUI.parent


def criar_app(db_path=None, secret: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("LSF_DB", RAIZ / "db" / "lsf_base.db")
    secret = secret or os.environ.get("LSF_SECRET")
    if not secret:
        raise RuntimeError("LSF_SECRET não definido — a sessão seria assinável por qualquer um")

    app = FastAPI(title="Orçamento LSF — Veks")
    app.state.db_path = pathlib.Path(db_path)
    app.state.templates = Jinja2Templates(directory=str(AQUI / "templates"))

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="lsf_sessao",
        https_only=os.environ.get("LSF_HTTPS_ONLY", "0") == "1",
        same_site="lax",
    )
    app.add_exception_handler(NaoAutenticado, redirecionar_ao_login)

    @app.exception_handler(HTTPException)
    def erro_html(request, exc: HTTPException):
        if exc.status_code == 404:
            return HTMLResponse(f"<h1>404</h1><p>{exc.detail}</p>", status_code=404)
        return HTMLResponse(
            f'<p class="erro" role="alert">{exc.detail}</p>', status_code=exc.status_code
        )

    app.mount("/static", StaticFiles(directory=str(AQUI / "static")), name="static")
    app.include_router(rotas_auth.router)
    app.include_router(rotas_projetos.router)
    app.include_router(rotas_quantitativos.router)
    app.include_router(rotas_orcamento.router)
    return app
