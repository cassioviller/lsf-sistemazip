"""Tela do cronograma + download MSPDI. FRONTEIRA (D6): a rota chama os
motores e formata; nenhum cálculo de rede/curva nasce aqui."""
from __future__ import annotations

import datetime
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.auth import usuario_logado
from app.db import conexao

router = APIRouter()


def _projeto_ou_404(con, projeto_id: int):
    projeto = con.execute(
        "SELECT id, codigo, nome FROM projeto WHERE id = ?", (projeto_id,)
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")
    return projeto


def _cronograma_ou_none(con, projeto_id: int):
    from lsf.geradores.estrutura import DadoIndisponivel
    from lsf.motores.cronograma import cronograma_projeto

    try:
        return cronograma_projeto(con, projeto_id), None
    except DadoIndisponivel as e:
        return None, str(e)


@router.get("/projetos/{projeto_id}/cronograma", response_class=HTMLResponse)
def tela(projeto_id: int, request: Request,
         con: sqlite3.Connection = Depends(conexao),
         usuario: dict = Depends(usuario_logado)):
    from lsf.motores.cronograma import curva_s
    from lsf.motores.orcamento import CustoIndisponivel

    projeto = _projeto_ou_404(con, projeto_id)
    crono, erro = _cronograma_ou_none(con, projeto_id)
    curva = None
    curva_erro = None
    semanas = []
    if crono is not None:
        try:
            curva = curva_s(con, projeto_id, crono)
            for i in range(0, len(curva.desembolso), 7):
                bloco = curva.desembolso[i:i + 7]
                semanas.append({
                    "semana": i // 7 + 1,
                    "desembolso": sum(bloco),
                    "acumulado": curva.acumulado[min(i + 6,
                                                     len(curva.acumulado) - 1)],
                })
        except CustoIndisponivel as e:
            curva_erro = str(e)
    return request.app.state.templates.TemplateResponse(
        request, "cronograma.html",
        {"projeto": projeto, "usuario": usuario, "crono": crono, "erro": erro,
         "curva": curva, "curva_erro": curva_erro, "semanas": semanas})


@router.get("/projetos/{projeto_id}/cronograma.xml")
def baixar_mspdi(projeto_id: int, inicio: str | None = None,
                 con: sqlite3.Connection = Depends(conexao),
                 usuario: dict = Depends(usuario_logado)):
    from lsf.relatorios import exportar_mspdi

    projeto = _projeto_ou_404(con, projeto_id)
    crono, erro = _cronograma_ou_none(con, projeto_id)
    if crono is None:
        raise HTTPException(status_code=409, detail=erro)
    try:
        data_inicio = (datetime.date.fromisoformat(inicio) if inicio
                       else datetime.date.today())
    except ValueError:
        raise HTTPException(status_code=400, detail="inicio deve ser AAAA-MM-DD")
    xml = exportar_mspdi(crono, data_inicio)
    return Response(
        content=xml, media_type="application/xml",
        headers={"Content-Disposition":
                 f'attachment; filename="cronograma_{projeto["codigo"]}.xml"'})
