"""Publicação da proposta: pré-flight dos gates + congelamento do snapshot.

Gates (spec §8) BLOQUEIAM, não avisam:
  - pendência de custo (total None) → recusa. Nunca publica custo parcial (D4.1).
  - macroetapa zerada → recusa. Escopo vazado em preço fechado é prejuízo (R7).
  - pendência ESTRUTURAL (tabela `pendencia`, motor=estrutura) → recusa. O motor
    disse que a solução por trás do kg não fecha: vão que reprova na verificação,
    furo em viga, peça fora do envelope. O preço existe, a estrutura não.
    Por que recusa em vez de carimbar: a 109 é a prova do custo do erro — o
    gerador exige viga laminada 1VG + pilares 1AL nas duas lajes, a obra foi
    construída com eles, e o orçamento de referência não tem linha para nenhum
    dos dois. Vender isso fechado é o "escopo vazado = prejuízo" acontecendo.
  - sondagem pendente → NÃO bloqueia; carimba a proposta e aparece como gate aberto.
    (A diferença: sondagem rebaixa a CONFIANÇA de um número que existe; a pendência
    estrutural diz que falta escopo no preço.)

Congelamento (D5): a proposta guarda o JSON do OrcamentoVenda e o HTML renderizado.
A rota pública serve o HTML gravado — nunca recalcula.
"""
from __future__ import annotations

import dataclasses
import json
import secrets

from lsf.relatorios import relatorio_html

from app.servicos.orcamento import montar

TAMANHO_TOKEN = 32


class PublicacaoBloqueada(Exception):
    def __init__(self, motivos: list[str]):
        self.motivos = motivos
        super().__init__("; ".join(motivos))


def motivos_de_bloqueio(con, projeto_id: int) -> list[str]:
    visao = montar(con, projeto_id)
    motivos: list[str] = []
    for pendencia in visao.pendencias:
        motivos.append(f"Pendência de custo: {pendencia}")
    for codigo in visao.macroetapas_zeradas:
        subtotal = next(
            s for s in visao.venda.orcamento.subtotais if s.eap_codigo == codigo
        )
        motivos.append(f"Macroetapa {codigo} ({subtotal.descricao}) sem quantitativo (R7)")
    for motor, mensagem in con.execute(
        "SELECT motor, mensagem FROM pendencia WHERE projeto_id = ? ORDER BY id",
        (projeto_id,),
    ):
        motivos.append(f"Pendência estrutural ({motor}): {mensagem}")
    if visao.venda.preco_total is None and not motivos:
        motivos.append("O orçamento não fecha um preço total")
    return motivos


def publicar(con, projeto_id: int, usuario_id: int, renderizar_pagina=None) -> dict:
    """`renderizar_pagina(snapshot, tabela_html) -> str` é injetado pela rota (Task 8).
    Sem ele, congela só a tabela analítica. O serviço nunca importa FastAPI."""
    motivos = motivos_de_bloqueio(con, projeto_id)
    if motivos:
        raise PublicacaoBloqueada(motivos)

    visao = montar(con, projeto_id)
    projeto = con.execute(
        "SELECT codigo, nome, cliente, sondagem_pendente FROM projeto WHERE id = ?",
        (projeto_id,),
    ).fetchone()

    snapshot_dict = {
        "venda": dataclasses.asdict(visao.venda),
        "projeto": {
            "codigo": projeto["codigo"],
            "nome": projeto["nome"],
            "cliente": projeto["cliente"],
            "sondagem_pendente": bool(projeto["sondagem_pendente"]),
        },
        # Sondagem pendente NÃO bloqueia — carimba e aparece como gate aberto (spec §8).
        "gates_abertos": (
            ["Sondagem pendente — a fundação sai com confiança rebaixada"]
            if projeto["sondagem_pendente"] else []
        ),
    }
    snapshot = json.dumps(snapshot_dict, ensure_ascii=False, default=str)

    tabela_html = relatorio_html(visao.venda)
    html = (
        renderizar_pagina(snapshot_dict, tabela_html)
        if renderizar_pagina else tabela_html
    )

    versao = (
        con.execute(
            "SELECT COALESCE(MAX(versao), 0) + 1 FROM proposta WHERE projeto_id = ?",
            (projeto_id,),
        ).fetchone()[0]
    )
    token = secrets.token_urlsafe(TAMANHO_TOKEN)

    # A versão anterior não some — passa a "superada" (spec §6).
    con.execute(
        "UPDATE proposta SET status = 'revogada' WHERE projeto_id = ? AND status = 'ativa'",
        (projeto_id,),
    )
    cur = con.execute(
        "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
        " html, total_venda, bdi_pct) VALUES (?,?,?,?,?,?,?,?)",
        (projeto_id, versao, token, usuario_id, snapshot, html,
         visao.venda.preco_total, visao.venda.bdi),
    )
    con.commit()
    return {"id": cur.lastrowid, "versao": versao, "token": token}
