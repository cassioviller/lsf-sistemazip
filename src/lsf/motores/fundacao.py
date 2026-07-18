"""MOTOR 4 — Pré-dimensionamento de fundação (Fase 3).

Fecha a cadeia D3: takedown de cargas (motor 3) → largura de baldrame corrido
por parede portante do MENOR nível (o radier é o menor nível, não o índice 0)
→ m³ de concreto para a folha 02.01.

Física provada no spike 4 e mantida aqui (I3): LSF é LEVE — a largura teórica
`carga / tensão_adm` quase sempre perde para o mínimo construtivo de 0,30 m.
Por isso `largura = max(teorica, minimo)` com o `governa` registrado: quando a
tensão do solo passar a governar, isso é informação de engenharia, não detalhe.

origem_regra: NBR 6122 (tensão admissível presumida por classe de solo,
conservadora) + NBR 6120 (as ações vêm do takedown). O produto emite
PRÉ-DIMENSIONAMENTO para orçamento, nunca projeto: S1 BLOQUEIA (aterro não
controlado não ganha número nenhum) e sondagem pendente REBAIXA a confiança de
toda a fundação para `parametrico` — a etiqueta comunica a incerteza (D4).
"""
from __future__ import annotations

from dataclasses import dataclass

from lsf.geradores.estrutura import (DadoIndisponivel, MARCA_PENDENCIA,
                                     _regra, _regras)
from lsf.motores.cargas import takedown_por_parede
from lsf.motores.orcamento import pior_confianca


@dataclass(frozen=True)
class FundacaoParede:
    parede_id: int
    comp_m: float
    carga_kn_m: float
    largura_teorica_m: float
    largura_m: float
    governa: str               # 'mínimo construtivo' | 'tensão do solo'
    volume_m3: float
    confianca: str
    origem_regra: str


@dataclass(frozen=True)
class ResultadoFundacao:
    paredes: list[FundacaoParede]
    volume_m3: float | None    # None quando bloqueado (S1) — nunca zero (D4.1)
    confianca: str | None
    bloqueado: bool
    pendencias: list[str]
    origem_regra: str


def largura_baldrame(carga_kn_m: float, tensao_adm_kpa: float,
                     larg_min_m: float) -> tuple[float, str]:
    """Largura da sapata corrida [NBR 6122]: kN/m ÷ kN/m² = m; nunca abaixo do
    mínimo executivo (I3 — em LSF o mínimo governa quase sempre)."""
    teorica = carga_kn_m / tensao_adm_kpa
    if teorica < larg_min_m:
        return larg_min_m, "mínimo construtivo"
    return teorica, "tensão do solo"


def pre_dimensionar(con, projeto_id: int) -> ResultadoFundacao:
    projeto = con.execute(
        "SELECT p.sondagem_pendente, s.classe, s.tensao_adm_kpa, s.observacao"
        "  FROM projeto p LEFT JOIN classe_solo s ON s.id = p.classe_solo_id"
        " WHERE p.id = ?", (projeto_id,)).fetchone()
    if projeto is None:
        raise DadoIndisponivel(f"projeto {projeto_id} não existe")
    sondagem_pendente, classe, tensao, observacao = tuple(projeto)
    if classe is None:
        raise DadoIndisponivel(
            f"projeto {projeto_id} sem classe de solo — fundação sem solo não é"
            " fundação com solo default (D4.1)")

    origem = (f"NBR 6122: tensão presumida {classe}={tensao:.0f} kPa"
              f" ({observacao}) + I3: largura = max(teórica, mínimo construtivo)")

    if classe == "S1":
        return ResultadoFundacao(
            paredes=[], volume_m3=None, confianca=None, bloqueado=True,
            pendencias=[
                f"{MARCA_PENDENCIA} Solo S1 ({observacao.split(':')[0]}):"
                " BLOQUEIA o pré-dimensionamento — aterro não controlado não"
                " recebe número nenhum. Exige sondagem + projeto de fundação"
                " [NBR 6122]."],
            origem_regra=origem)

    R = _regras(con)
    larg_min = _regra(R, "fund_larg_min_m")
    altura = _regra(R, "fund_altura_baldrame_m")

    cargas = takedown_por_parede(con, projeto_id)
    menor_nivel = min(c.nivel_indice for c in cargas)

    paredes: list[FundacaoParede] = []
    for c in cargas:
        if c.nivel_indice != menor_nivel:
            continue
        largura, governa = largura_baldrame(c.total_kn_m, tensao, larg_min)
        conf = pior_confianca(c.confianca, "estimado")
        if sondagem_pendente:
            conf = pior_confianca(conf, "parametrico")
        paredes.append(FundacaoParede(
            parede_id=c.parede_id, comp_m=c.comp_m, carga_kn_m=c.total_kn_m,
            largura_teorica_m=round(c.total_kn_m / tensao, 4),
            largura_m=round(largura, 3), governa=governa,
            volume_m3=round(largura * altura * c.comp_m, 4),
            confianca=conf,
            origem_regra=(f"{origem} · baldrame {largura:.2f}×{altura:.2f} m"
                          f" [prática 30×40]")))
    if not paredes:
        raise DadoIndisponivel(
            f"projeto {projeto_id}: takedown não devolveu parede portante no"
            f" nível {menor_nivel} — não há onde apoiar a fundação")

    confianca = pior_confianca(*(f.confianca for f in paredes))
    pendencias: list[str] = []
    if sondagem_pendente:
        pendencias.append(
            "Sondagem pendente: tensão do solo é PRESUMIDA (conservadora) e toda"
            " a fundação sai com confiança rebaixada — não bloqueia, etiqueta."
            " Confirmar por sondagem SPT antes do contrato [NBR 6122/8036].")

    return ResultadoFundacao(
        paredes=paredes,
        volume_m3=round(sum(f.volume_m3 for f in paredes), 3),
        confianca=confianca, bloqueado=False, pendencias=pendencias,
        origem_regra=origem)
