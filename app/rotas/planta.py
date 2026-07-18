"""Entrada MANUAL da planta_normalizada (Fase 2, item 2) + o botão que dispara a
cadeia paramétrica.

FRONTEIRA (mesma da tela de orçamento): aqui é CRUD do grafo (níveis → nós →
paredes → vãos) e chamada de motor. Nenhuma regra de engenharia: perfil vem da
lista do banco, kg vem do `derivar_quantitativos`, pendência vem do
`derivar_cargas`. Número que nascesse aqui seria bug de arquitetura (CLAUDE.md).
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import usuario_logado
from app.db import conexao
from app.rotas.quantitativos import _numero_ptbr

router = APIRouter()

# nós a menos de 5 mm um do outro são o MESMO canto: a tolerância de digitação,
# não de engenharia (o encadeador de contorno do gerador usa 2 cm)
_TOL_NO_M = 0.005


def _coord_ptbr(texto: str) -> float:
    """Coordenada de planta: como _numero_ptbr, mas aceita negativa."""
    t = texto.strip()
    if t.startswith("-"):
        return -_numero_ptbr(t[1:])
    return _numero_ptbr(t)


def _projeto_ou_404(con, projeto_id: int):
    projeto = con.execute(
        "SELECT id, codigo, nome FROM projeto WHERE id = ?", (projeto_id,)
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")
    return projeto


def _nivel_do_projeto_ou_404(con, projeto_id: int, nivel_id: int):
    nivel = con.execute(
        "SELECT id FROM nivel WHERE id = ? AND projeto_id = ?",
        (nivel_id, projeto_id)).fetchone()
    if nivel is None:
        raise HTTPException(status_code=404, detail="nível não é deste projeto")
    return nivel


def _parede_do_projeto_ou_404(con, projeto_id: int, parede_id: int):
    parede = con.execute(
        "SELECT p.id FROM parede p JOIN nivel n ON n.id = p.nivel_id"
        " WHERE p.id = ? AND n.projeto_id = ?", (parede_id, projeto_id)).fetchone()
    if parede is None:
        raise HTTPException(status_code=404, detail="parede não é deste projeto")
    return parede


def _no(con, nivel_id: int, x: float, y: float) -> int:
    """Canto é NÓ do grafo (migração 004): reusa o nó existente no mesmo lugar —
    duas paredes que se encontram em (6,0) apontam para o MESMO nó."""
    linha = con.execute(
        "SELECT id FROM no_planta WHERE nivel_id = ?"
        " AND ABS(x - ?) < ? AND ABS(y - ?) < ?",
        (nivel_id, x, _TOL_NO_M, y, _TOL_NO_M)).fetchone()
    if linha:
        return linha[0]
    return con.execute(
        "INSERT INTO no_planta (nivel_id, x, y, confianca) VALUES (?,?,?,'real')",
        (nivel_id, x, y)).lastrowid


def _dados_da_tela(con, projeto_id: int) -> dict:
    niveis = [dict(n) for n in con.execute(
        "SELECT id, indice, nome, pe_direito_m, cota_m FROM nivel"
        " WHERE projeto_id = ? ORDER BY indice", (projeto_id,))]
    for nivel in niveis:
        nivel["paredes"] = [dict(p) for p in con.execute(
            "SELECT p.id, p.externa, p.portante, p.perfil_codigo,"
            "       a.x AS x0, a.y AS y0, b.x AS x1, b.y AS y1"
            "  FROM parede p"
            "  JOIN no_planta a ON a.id = p.no_a"
            "  JOIN no_planta b ON b.id = p.no_b"
            " WHERE p.nivel_id = ? ORDER BY p.id", (nivel["id"],))]
        for parede in nivel["paredes"]:
            parede["vaos"] = con.execute(
                "SELECT id, tipo, posicao_m, largura_m, altura_m, peitoril_m"
                "  FROM vao WHERE parede_id = ? ORDER BY posicao_m",
                (parede["id"],)).fetchall()
    perfis = [r[0] for r in con.execute(
        "SELECT codigo FROM perfil_lsf WHERE codigo LIKE 'Ue%' ORDER BY codigo")]
    return {"niveis": niveis, "perfis": perfis}


def _tela(request, con, usuario, projeto_id, status_code=200,
          erro=None, resultado=None):
    projeto = _projeto_ou_404(con, projeto_id)
    return request.app.state.templates.TemplateResponse(
        request, "planta.html",
        {"projeto": projeto, "usuario": usuario, "erro": erro,
         "resultado": resultado, **_dados_da_tela(con, projeto_id)},
        status_code=status_code)


@router.get("/projetos/{projeto_id}/planta", response_class=HTMLResponse)
def planta(projeto_id: int, request: Request,
           con: sqlite3.Connection = Depends(conexao),
           usuario: dict = Depends(usuario_logado)):
    return _tela(request, con, usuario, projeto_id)


@router.post("/projetos/{projeto_id}/planta/niveis")
def criar_nivel(projeto_id: int,
                indice: int = Form(...), nome: str = Form(...),
                pe_direito: str = Form(...), cota: str = Form("0"),
                con: sqlite3.Connection = Depends(conexao),
                usuario: dict = Depends(usuario_logado)):
    _projeto_ou_404(con, projeto_id)
    try:
        con.execute(
            "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m, cota_m)"
            " VALUES (?,?,?,?,?)",
            (projeto_id, indice, nome, _numero_ptbr(pe_direito),
             _coord_ptbr(cota)))
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=400, detail=f"nível inválido: {e}")
    con.commit()
    return RedirectResponse(f"/projetos/{projeto_id}/planta", status_code=303)


@router.post("/projetos/{projeto_id}/planta/paredes")
def criar_parede(projeto_id: int,
                 nivel_id: int = Form(...),
                 x0: str = Form(...), y0: str = Form(...),
                 x1: str = Form(...), y1: str = Form(...),
                 perfil_codigo: str = Form(...),
                 externa: int = Form(0), portante: int = Form(1),
                 con: sqlite3.Connection = Depends(conexao),
                 usuario: dict = Depends(usuario_logado)):
    _projeto_ou_404(con, projeto_id)
    _nivel_do_projeto_ou_404(con, projeto_id, nivel_id)
    ax, ay = _coord_ptbr(x0), _coord_ptbr(y0)
    bx, by = _coord_ptbr(x1), _coord_ptbr(y1)
    no_a = _no(con, nivel_id, ax, ay)
    no_b = _no(con, nivel_id, bx, by)
    try:
        con.execute(
            "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, portante,"
            " externa, perfil_codigo, origem, confianca)"
            " VALUES (?,?,?,0.14,?,?,?,'MANUAL','real')",
            (nivel_id, no_a, no_b, portante, externa, perfil_codigo))
    except sqlite3.IntegrityError as e:
        con.rollback()
        raise HTTPException(status_code=400, detail=f"parede inválida: {e}")
    con.commit()
    return RedirectResponse(f"/projetos/{projeto_id}/planta", status_code=303)


@router.post("/projetos/{projeto_id}/planta/paredes/{parede_id}/vaos")
def criar_vao(projeto_id: int, parede_id: int,
              tipo: str = Form(...), posicao: str = Form(...),
              largura: str = Form(...), altura: str = Form(...),
              peitoril: str = Form(""),
              con: sqlite3.Connection = Depends(conexao),
              usuario: dict = Depends(usuario_logado)):
    _projeto_ou_404(con, projeto_id)
    _parede_do_projeto_ou_404(con, projeto_id, parede_id)
    try:
        con.execute(
            "INSERT INTO vao (parede_id, tipo, posicao_m, largura_m, altura_m,"
            " peitoril_m, confianca) VALUES (?,?,?,?,?,?,'real')",
            (parede_id, tipo, _numero_ptbr(posicao), _numero_ptbr(largura),
             _numero_ptbr(altura),
             _numero_ptbr(peitoril) if peitoril.strip() else None))
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=400, detail=f"vão inválido: {e}")
    con.commit()
    return RedirectResponse(f"/projetos/{projeto_id}/planta", status_code=303)


@router.post("/projetos/{projeto_id}/planta/paredes/{parede_id}/excluir")
def excluir_parede(projeto_id: int, parede_id: int,
                   con: sqlite3.Connection = Depends(conexao),
                   usuario: dict = Depends(usuario_logado)):
    _projeto_ou_404(con, projeto_id)
    _parede_do_projeto_ou_404(con, projeto_id, parede_id)
    nos = con.execute("SELECT no_a, no_b FROM parede WHERE id = ?",
                      (parede_id,)).fetchone()
    con.execute("DELETE FROM vao WHERE parede_id = ?", (parede_id,))
    con.execute("DELETE FROM parede WHERE id = ?", (parede_id,))
    for no_id in set(nos):
        em_uso = con.execute(
            "SELECT 1 FROM parede WHERE no_a = ? OR no_b = ?",
            (no_id, no_id)).fetchone()
        if em_uso is None:
            con.execute("DELETE FROM no_planta WHERE id = ?", (no_id,))
    con.commit()
    return RedirectResponse(f"/projetos/{projeto_id}/planta", status_code=303)


@router.post("/projetos/{projeto_id}/planta/derivar", response_class=HTMLResponse)
def derivar(projeto_id: int, request: Request,
            con: sqlite3.Connection = Depends(conexao),
            usuario: dict = Depends(usuario_logado)):
    """Dispara a cadeia paramétrica (D3): gerador de estrutura → kg PARAMETRICO
    na EAP; takedown de cargas → pendências no gate. Dado ausente é 409 com a
    mensagem do motor, não 500 (D4.1: erro barulhento, nunca silêncio)."""
    from lsf.geradores.estrutura import DadoIndisponivel, derivar_quantitativos
    from lsf.motores.cargas import derivar_cargas
    from lsf.motores.fundacao import derivar_fundacao

    _projeto_ou_404(con, projeto_id)
    try:
        quantitativo = derivar_quantitativos(con, projeto_id)
        cargas = derivar_cargas(con, projeto_id)
    except DadoIndisponivel as e:
        return _tela(request, con, usuario, projeto_id, status_code=409,
                     erro=f"A derivação parou: {e}")
    # a fundação depende de um input a mais (classe de solo): a falta dele não
    # pode derrubar a estrutura já derivada — vira o próximo passo na tela
    fundacao = None
    fundacao_erro = None
    try:
        fundacao = derivar_fundacao(con, projeto_id)
    except DadoIndisponivel as e:
        fundacao_erro = str(e)
    resultado = {
        "kg_comprado": quantitativo["kg_comprado"],
        "confianca": quantitativo["confianca"],
        "gravado": quantitativo["gravado"],
        "preservado": quantitativo.get("preservado"),
        "alertas": quantitativo.get("alertas", []),
        "pendencias": (quantitativo.get("pendencias_estruturais", [])
                       + cargas["pendencias"]
                       + (fundacao["pendencias"] if fundacao else [])),
        "n_cargas": len(cargas["cargas"]),
        "fundacao": fundacao,
        "fundacao_erro": fundacao_erro,
    }
    return _tela(request, con, usuario, projeto_id, resultado=resultado)
