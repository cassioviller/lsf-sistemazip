"""Quantitativos MANUAL (D2: paramétrico e executivo diferem só na `origem`)."""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth import usuario_logado
from app.db import conexao

router = APIRouter()


def _numero_ptbr(texto: str) -> float:
    """Valida por regex e aceita ambos os formatos; o resto é erro 400, não 500.

    - pt-BR com milhar: '1.500,5' → 1500.5; '1.500' → 1500 (ambiguidade '1.500':
      a interpretação pt-BR ganha, porque a UI é pt-BR).
    - vírgula decimal simples: '31345,5' → 31345.5.
    - float puro: '1500.5' → 1500.5; '1.5' → 1.5 (antes, remover pontos
      transformava '1500.5' em 15005 — 10× por dígito decimal).
    """
    t = texto.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?", t):
        return float(t.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+(,\d+)?", t):
        return float(t.replace(",", "."))
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return float(t)
    raise HTTPException(status_code=400, detail="quantidade inválida")


def _quantidade_ptbr(valor: float | None) -> str:
    """Renderização estável para o round-trip do formulário: NUNCA ponto decimal.

    None → '' (sem quantitativo); 0 → '0' (zero legítimo aparece); inteiro sem
    casa morta ('31345', não '31345.0'); decimal com vírgula ('31345,5').
    """
    if valor is None:
        return ""
    if valor == int(valor):
        return str(int(valor))
    return str(valor).replace(".", ",")


def _arvore(con: sqlite3.Connection, projeto_id: int) -> list[dict]:
    """Macroetapas com TODAS as folhas (qualquer profundidade) e o quantitativo lançado.

    Folha = item com composição (migração 001). A macroetapa dona é achada subindo
    a cadeia pai_id até a raiz — '03.01.02' aparece sob a '03', com o código completo.
    """
    itens = con.execute(
        "SELECT e.id, e.codigo, e.descricao, e.unidade, e.pai_id, e.composicao_id,"
        "       q.quantidade, q.origem"
        "  FROM eap_item e"
        "  LEFT JOIN quantitativo q ON q.eap_item_id = e.id AND q.projeto_id = ?"
        " ORDER BY e.codigo",
        (projeto_id,),
    ).fetchall()
    por_id = {i["id"]: i for i in itens}
    macros = [dict(i, folhas=[]) for i in itens if i["pai_id"] is None]
    macros_por_id = {m["id"]: m for m in macros}
    for item in itens:
        if item["composicao_id"] is None:
            continue  # agrupador (macroetapa ou intermediário) não é quantificável
        raiz = item
        while raiz["pai_id"] is not None:
            raiz = por_id[raiz["pai_id"]]
        macros_por_id[raiz["id"]]["folhas"].append(
            dict(item, quantidade_ptbr=_quantidade_ptbr(item["quantidade"]))
        )
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
    origem: str = Form("MANUAL"),
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    valor = _numero_ptbr(quantidade)
    if valor < 0:
        raise HTTPException(status_code=400, detail="quantidade não pode ser negativa")
    # D2: os modos diferem só na origem. TAKEOFF = medido de projeto executivo —
    # é a migração proposta→contrato: trocar a linha (inclusive a PARAMETRICO
    # derivada), que os motores passam a PRESERVAR (guarda dos derivar_*).
    if origem not in ("MANUAL", "TAKEOFF"):
        raise HTTPException(status_code=400,
                            detail="origem deve ser MANUAL ou TAKEOFF")
    origem_regra = ("medido de projeto executivo (takeoff)"
                    if origem == "TAKEOFF" else None)

    try:
        # UNIQUE (projeto_id, eap_item_id): uma linha ativa por item (D2).
        # origem_regra do lançamento substitui a do gerador — editar linha
        # derivada não pode manter proveniência obsoleta.
        con.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem,"
            " confianca, origem_regra)"
            " VALUES (?,?,?,?,'real',?)"
            " ON CONFLICT (projeto_id, eap_item_id) DO UPDATE SET"
            "   quantidade=excluded.quantidade, origem=excluded.origem,"
            "   confianca=excluded.confianca, origem_regra=excluded.origem_regra",
            (projeto_id, eap_item_id, valor, origem, origem_regra),
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
        {"projeto": {"id": projeto_id},
         "item": dict(item, quantidade_ptbr=_quantidade_ptbr(item["quantidade"]))},
    )
