"""Tela de orçamento analítico."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.auth import usuario_logado
from app.db import conexao
from app.servicos.orcamento import montar
from lsf.relatorios import proposta_docx

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


@router.get("/projetos/{projeto_id}/proposta.docx")
def baixar_proposta_docx(
    projeto_id: int,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    """Proposta .docx de TRABALHO (a congelada é o snapshot de /p/<token>).

    Não passa pelo gate do 409 de propósito: é o documento da negociação, e
    carrega as pendências como seção. Preço fechado só sai por /publicar."""
    projeto = con.execute(
        "SELECT codigo, nome, cliente, sondagem_pendente FROM projeto"
        " WHERE id = ?", (projeto_id,)).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")
    visao = montar(con, projeto_id)
    pendencias = [m for (m,) in con.execute(
        "SELECT mensagem FROM pendencia WHERE projeto_id = ? ORDER BY id",
        (projeto_id,))]
    conteudo = proposta_docx(visao.venda, dict(projeto), pendencias)
    return Response(
        content=conteudo,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"),
        headers={"Content-Disposition":
                 f'attachment; filename="proposta_{projeto["codigo"]}.docx"'})
