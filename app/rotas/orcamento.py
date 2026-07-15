"""Tela de orçamento analítico."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth import usuario_logado
from app.db import conexao
from app.servicos.orcamento import montar

router = APIRouter()


@router.get("/projetos/{projeto_id}/orcamento", response_class=HTMLResponse)
def tela(
    projeto_id: int,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projeto = con.execute(
        "SELECT id, codigo, nome FROM projeto WHERE id = ?", (projeto_id,)
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")

    visao = montar(con, projeto_id)
    subtotais = visao.venda.orcamento.subtotais
    completas = sum(1 for s in subtotais if not s.zerada)
    return request.app.state.templates.TemplateResponse(
        request, "orcamento.html",
        {
            "projeto": projeto, "visao": visao, "usuario": usuario,
            "subtotais": subtotais,
            "completude": f"{completas}/{len(subtotais)}",
            "bdi_pct": visao.venda.bdi * 100,
        },
    )
