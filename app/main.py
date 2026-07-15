"""Fábrica do app. O db_path é injetado — é o que permite o TestClient rodar
contra um banco temporário sem variável de ambiente global."""
from __future__ import annotations

import os
import pathlib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NaoAutenticado, redirecionar_ao_login
from app.rotas import auth as rotas_auth
from app.rotas import projetos as rotas_projetos

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
    app.mount("/static", StaticFiles(directory=str(AQUI / "static")), name="static")
    app.include_router(rotas_auth.router)
    app.include_router(rotas_projetos.router)
    return app
