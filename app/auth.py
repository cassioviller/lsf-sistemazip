"""Senha (scrypt, stdlib) e sessão (cookie assinado por SessionMiddleware).

Sem dependência de criptografia externa: hashlib.scrypt é padrão da linguagem.
Formato armazenado: scrypt$n$r$p$salt_hex$hash_hex
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response

from app.db import conexao

N, R, P, DKLEN = 2**14, 8, 1, 32


class NaoAutenticado(Exception):
    """Levantada quando não há sessão; o handler do app redireciona a /login."""


def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.scrypt(senha.encode(), salt=sal, n=N, r=R, p=P, dklen=DKLEN)
    return f"scrypt${N}${R}${P}${sal.hex()}${dk.hex()}"


def senha_confere(senha: str, hash_armazenado: str) -> bool:
    try:
        marca, n, r, p, sal_hex, esperado_hex = hash_armazenado.split("$")
        if marca != "scrypt":
            return False
        dk = hashlib.scrypt(
            senha.encode(), salt=bytes.fromhex(sal_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(esperado_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), esperado_hex)


def autenticar(con: sqlite3.Connection, email: str, senha: str) -> sqlite3.Row | None:
    linha = con.execute(
        "SELECT id, email, nome, senha_hash, ativo FROM usuario WHERE email = ?", (email,)
    ).fetchone()
    if linha is None or not linha["ativo"]:
        return None
    if not senha_confere(senha, linha["senha_hash"]):
        return None
    return linha


def usuario_logado(request: Request, con: sqlite3.Connection = Depends(conexao)) -> dict:
    """Dependência: devolve o usuário da sessão ou levanta NaoAutenticado."""
    usuario_id = request.session.get("usuario_id")
    if usuario_id is None:
        raise NaoAutenticado()
    linha = con.execute(
        "SELECT id, email, nome FROM usuario WHERE id = ? AND ativo = 1", (usuario_id,)
    ).fetchone()
    if linha is None:
        request.session.clear()
        raise NaoAutenticado()
    return dict(linha)


def redirecionar_ao_login(request: Request, exc: NaoAutenticado) -> Response:
    """303 para navegação normal; em requisição htmx (header HX-Request), 401 com
    HX-Redirect — o XHR do htmx segue o 303 e faria swap da página de login inteira
    dentro do alvo (ex.: <tr>). O htmx vendored (1.x) processa HX-Redirect antes de
    olhar o status, então o 401 não atrapalha e sinaliza corretamente a sessão ausente."""
    if request.headers.get("HX-Request"):
        return Response(status_code=401, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)
