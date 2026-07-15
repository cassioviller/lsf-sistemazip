"""Publicação e revogação. O gate mora aqui, do lado do servidor: um botão
desabilitado no HTML é cosmético — a recusa é o 409."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth import usuario_logado
from app.db import conexao
from app.rotas.publico import render_proposta
from app.servicos.publicacao import PublicacaoBloqueada, publicar

router = APIRouter()


@router.post("/projetos/{projeto_id}/publicar")
def publicar_proposta(
    projeto_id: int,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projeto = con.execute(
        "SELECT id, codigo FROM projeto WHERE id = ?", (projeto_id,)
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")

    def renderizar(snapshot, tabela_html):
        return render_proposta(request.app.state.templates, snapshot, tabela_html)

    try:
        proposta = publicar(con, projeto_id, usuario["id"], renderizar)
    except PublicacaoBloqueada as bloqueio:
        return request.app.state.templates.TemplateResponse(
            request, "publicacao_bloqueada.html",
            {"projeto": projeto, "motivos": bloqueio.motivos, "usuario": usuario},
            status_code=409,
        )
    return RedirectResponse(f"/projetos/{projeto_id}", status_code=303)


@router.post("/propostas/{proposta_id}/revogar")
def revogar(
    proposta_id: int,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    linha = con.execute(
        "SELECT projeto_id FROM proposta WHERE id = ?", (proposta_id,)
    ).fetchone()
    if linha is None:
        raise HTTPException(status_code=404, detail="proposta não existe")
    con.execute("UPDATE proposta SET status = 'revogada' WHERE id = ?", (proposta_id,))
    con.commit()
    return RedirectResponse(f"/projetos/{linha['projeto_id']}", status_code=303)
