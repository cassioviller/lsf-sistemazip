"""Projetos. O projeto trava a REFERÊNCIA (D5.1): YYYY-MM + UF + desonerado."""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import usuario_logado
from app.db import conexao

router = APIRouter()

RE_REFERENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/projetos", response_class=HTMLResponse)
def listar(
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projetos = con.execute(
        "SELECT id, codigo, nome, cliente, referencia, uf FROM projeto ORDER BY criado_em DESC"
    ).fetchall()
    return request.app.state.templates.TemplateResponse(
        request, "projetos.html", {"projetos": projetos, "usuario": usuario}
    )


@router.get("/projetos/novo", response_class=HTMLResponse)
def form_novo(
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    solos = con.execute(
        "SELECT id, classe, descricao FROM classe_solo ORDER BY classe"
    ).fetchall()
    return request.app.state.templates.TemplateResponse(
        request, "projeto_novo.html", {"solos": solos, "usuario": usuario, "erro": None}
    )


def _erro_form(request, con, usuario, mensagem):
    solos = con.execute(
        "SELECT id, classe, descricao FROM classe_solo ORDER BY classe"
    ).fetchall()
    return request.app.state.templates.TemplateResponse(
        request, "projeto_novo.html",
        {"solos": solos, "usuario": usuario, "erro": mensagem},
        status_code=400,
    )


@router.post("/projetos")
def criar(
    request: Request,
    codigo: str = Form(...),
    nome: str = Form(...),
    referencia: str = Form(...),
    desonerado: int = Form(0),
    sondagem_pendente: int = Form(1),
    cliente: str = Form(""),
    uf: str = Form(""),
    classe_solo_id: int | None = Form(None),
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    if not RE_REFERENCIA.match(referencia):
        return _erro_form(
            request, con, usuario,
            "Referência deve estar no formato AAAA-MM (ex.: 2026-06)."
        )
    try:
        cur = con.execute(
            "INSERT INTO projeto (codigo, nome, cliente, referencia, uf, desonerado,"
            " classe_solo_id, sondagem_pendente) VALUES (?,?,?,?,?,?,?,?)",
            (codigo, nome, cliente or None, referencia, uf or None,
             desonerado, classe_solo_id, sondagem_pendente),
        )
    except sqlite3.IntegrityError:
        return _erro_form(request, con, usuario, f"O código {codigo} já existe.")
    con.commit()
    return RedirectResponse(f"/projetos/{cur.lastrowid}", status_code=303)


@router.get("/projetos/{projeto_id}", response_class=HTMLResponse)
def detalhe(
    projeto_id: int,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projeto = con.execute(
        "SELECT p.*, s.classe AS solo_classe FROM projeto p"
        " LEFT JOIN classe_solo s ON s.id = p.classe_solo_id WHERE p.id = ?",
        (projeto_id,),
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")
    propostas = con.execute(
        "SELECT versao, token, status, total_venda, publicada_em FROM proposta"
        " WHERE projeto_id = ? ORDER BY versao DESC",
        (projeto_id,),
    ).fetchall()
    return request.app.state.templates.TemplateResponse(
        request, "projeto.html",
        {"projeto": projeto, "propostas": propostas, "usuario": usuario},
    )
