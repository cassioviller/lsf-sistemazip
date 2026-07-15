"""Quantitativos MANUAL (D2: paramétrico e executivo diferem só na `origem`)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth import usuario_logado
from app.db import conexao

router = APIRouter()


def _numero_ptbr(texto: str) -> float:
    """Aceita '1500,5' e '1500.5'. Erro vira 400, não 500."""
    try:
        return float(texto.strip().replace(".", "").replace(",", "."))
    except ValueError:
        raise HTTPException(status_code=400, detail="quantidade inválida")


def _arvore(con: sqlite3.Connection, projeto_id: int) -> list[dict]:
    """Macroetapas com suas folhas e o quantitativo já lançado (se houver)."""
    itens = con.execute(
        "SELECT e.id, e.codigo, e.descricao, e.unidade, e.pai_id, e.composicao_id,"
        "       q.quantidade, q.origem"
        "  FROM eap_item e"
        "  LEFT JOIN quantitativo q ON q.eap_item_id = e.id AND q.projeto_id = ?"
        " ORDER BY e.codigo",
        (projeto_id,),
    ).fetchall()
    macros = [dict(i, folhas=[]) for i in itens if i["pai_id"] is None]
    por_id = {m["id"]: m for m in macros}
    for item in itens:
        if item["pai_id"] is not None and item["pai_id"] in por_id:
            por_id[item["pai_id"]]["folhas"].append(dict(item))
    return macros


@router.get("/projetos/{projeto_id}/quantitativos", response_class=HTMLResponse)
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
    return request.app.state.templates.TemplateResponse(
        request, "quantitativos.html",
        {"projeto": projeto, "macroetapas": _arvore(con, projeto_id), "usuario": usuario},
    )


@router.post("/projetos/{projeto_id}/quantitativos", response_class=HTMLResponse)
def lancar(
    projeto_id: int,
    request: Request,
    eap_item_id: int = Form(...),
    quantidade: str = Form(...),
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    valor = _numero_ptbr(quantidade)
    if valor < 0:
        raise HTTPException(status_code=400, detail="quantidade não pode ser negativa")

    try:
        # UNIQUE (projeto_id, eap_item_id): uma linha ativa por item (D2).
        con.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem, confianca)"
            " VALUES (?,?,?,'MANUAL','real')"
            " ON CONFLICT (projeto_id, eap_item_id) DO UPDATE SET"
            "   quantidade=excluded.quantidade, origem=excluded.origem,"
            "   confianca=excluded.confianca",
            (projeto_id, eap_item_id, valor),
        )
    except sqlite3.IntegrityError as erro:
        # trg_quantitativo_so_em_folha: agrupador recebe soma, não quantidade.
        raise HTTPException(
            status_code=400,
            detail="Quantitativo só pode ser lançado em folha da EAP (item com composição).",
        ) from erro
    con.commit()

    item = con.execute(
        "SELECT e.id, e.codigo, e.descricao, e.unidade, e.composicao_id,"
        "       q.quantidade, q.origem"
        "  FROM eap_item e"
        "  LEFT JOIN quantitativo q ON q.eap_item_id = e.id AND q.projeto_id = ?"
        " WHERE e.id = ?",
        (projeto_id, eap_item_id),
    ).fetchone()
    return request.app.state.templates.TemplateResponse(
        request, "_linha_quantitativo.html",
        {"projeto": {"id": projeto_id}, "item": dict(item)},
    )
