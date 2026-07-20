"""View-model da tela de orçamento.

FRONTEIRA (spec §5): este módulo NÃO calcula preço. Ele chama os motores puros e
formata o resultado. A única aritmética aqui é a faixa ±% de exibição (D4), derivada
da confiança que o motor propagou — nunca inventada.
"""
from __future__ import annotations

from dataclasses import dataclass

from lsf.motores.orcamento import (
    OrcamentoVenda,
    aplicar_bdi,
    carregar_parametros_bdi,
    custo_direto_projeto,
)

FAIXA_PCT_DEFAULT = 0.15
CONFIANCAS_COM_FAIXA = ("estimado", "parametrico")


@dataclass(frozen=True)
class VisaoOrcamento:
    venda: OrcamentoVenda
    linhas: list[dict]
    macroetapas_zeradas: list[str]
    pendencias: list[str]
    pode_publicar: bool
    # Faixa ±% do TOTAL: presente só quando a confiança geral é 'estimado'/
    # 'parametrico' (D4). None em 'real' e enquanto o total não fecha. É o que
    # impede o número-manchete de sair seco no item mais caro (montagem LSF).
    preco_total_min: float | None
    preco_total_max: float | None


def montar(con, projeto_id: int, faixa_pct: float = FAIXA_PCT_DEFAULT) -> VisaoOrcamento:
    direto = custo_direto_projeto(con, projeto_id)
    venda = aplicar_bdi(direto, carregar_parametros_bdi(con))

    linhas = []
    for l in venda.linhas:
        com_faixa = l.preco_venda is not None and l.confianca in CONFIANCAS_COM_FAIXA
        linhas.append({
            "eap_codigo": l.eap_codigo,
            "descricao": l.descricao,
            "unidade": l.unidade,
            "quantidade": l.quantidade,
            "origem": l.origem,
            "custo_unitario": l.custo_unitario,
            "custo_direto": l.custo_direto,
            "preco_venda": l.preco_venda,
            "confianca": l.confianca,
            "pendencia": l.pendencia,
            "preco_min": l.preco_venda * (1 - faixa_pct) if com_faixa else None,
            "preco_max": l.preco_venda * (1 + faixa_pct) if com_faixa else None,
        })

    # Gate (spec §8): total pendente OU macroetapa zerada impede a publicação.
    pode_publicar = (
        venda.preco_total is not None
        and not direto.pendencias
        and not direto.macroetapas_zeradas
    )

    total_com_faixa = (
        venda.preco_total is not None and venda.confianca in CONFIANCAS_COM_FAIXA
    )
    return VisaoOrcamento(
        venda=venda,
        linhas=linhas,
        macroetapas_zeradas=list(direto.macroetapas_zeradas),
        pendencias=list(direto.pendencias),
        pode_publicar=pode_publicar,
        preco_total_min=venda.preco_total * (1 - faixa_pct) if total_com_faixa else None,
        preco_total_max=venda.preco_total * (1 + faixa_pct) if total_com_faixa else None,
    )
