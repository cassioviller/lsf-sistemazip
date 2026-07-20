"""Página pública da proposta. Sem sessão. Serve o HTML CONGELADO — nunca recalcula.

Se esta rota algum dia chamar um motor, o congelamento morreu e o cliente passa a ver
um preço que muda sozinho. Ela lê `proposta.html` e nada mais.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.db import conexao

router = APIRouter()

CABECALHO_SEM_INDEXACAO = {"X-Robots-Tag": "noindex, nofollow"}


def render_proposta(templates, snapshot: dict, tabela_html: str) -> str:
    """Renderiza a página que será CONGELADA. Chamada uma única vez, na publicação."""
    return templates.get_template("proposta_publica.html").render(
        projeto=snapshot["projeto"],
        venda=snapshot["venda"],
        # Faixa ±% do total congelada no snapshot (D4): None em 'real'.
        preco_total_min=snapshot.get("preco_total_min"),
        preco_total_max=snapshot.get("preco_total_max"),
        gates_abertos=snapshot["gates_abertos"],
        tabela_html=tabela_html,
    )


@router.get("/p/{token}", response_class=HTMLResponse)
def proposta_publica(
    token: str,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
):
    linha = con.execute(
        "SELECT p.html, p.status, p.versao, j.codigo FROM proposta p"
        " JOIN projeto j ON j.id = p.projeto_id WHERE p.token = ?",
        (token,),
    ).fetchone()
    if linha is None:
        return HTMLResponse(
            "<h1>404</h1><p>Proposta não encontrada.</p>",
            status_code=404, headers=CABECALHO_SEM_INDEXACAO,
        )
    if linha["status"] == "revogada":
        pagina = request.app.state.templates.get_template(
            "proposta_revogada.html"
        ).render(versao=linha["versao"], codigo=linha["codigo"])
        return HTMLResponse(pagina, status_code=410, headers=CABECALHO_SEM_INDEXACAO)

    return HTMLResponse(linha["html"], headers=CABECALHO_SEM_INDEXACAO)
