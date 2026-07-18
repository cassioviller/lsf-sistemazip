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

import math
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


@dataclass(frozen=True)
class DirecaoVento:
    direcao: str               # 'x' | 'z'
    f_kn: float                # cortante de fachada
    fitas_necessarias: int     # por linha de contraventamento
    fitas_adotadas: int        # nunca abaixo do mínimo da norma


@dataclass(frozen=True)
class ResultadoVento:
    direcoes: list[DirecaoVento]
    hold_downs_un: int
    pendencias: list[str]
    confianca: str
    origem_regra: str


def verificar_vento(con, projeto_id: int) -> ResultadoVento:
    """Verificação de vento/ancoragem [NBR 6123, SIMPLIFICADA — envelope
    conservador; cálculo próprio autorizado em 2026-07-18, não é projeto]:

      F = q_vento × altura_total × largura_da_fachada_normal, por direção;
      cada direção tem 2 linhas de contraventamento (as fachadas paralelas);
      fitas/linha = ceil(F / (2 · T_Rd)), nunca abaixo do mínimo da norma;
      hold-downs = 2 por extremo de linha (4 linhas × 2) + 2 por canto (4) = 24
      — a mesma conta que fecha os 24 un do v7 na 109, derivada da planta em
      vez de chumbada.

    O que ela NÃO faz: coeficientes de arrasto/rajada por zona (S1·S2·S3 da
    norma), sucção de cobertura, momento de tombamento. `q_vento` da regra é o
    envelope; demanda acima das fitas mínimas vira pendência, não silêncio."""
    R = _regras(con)
    q = _regra(R, "vento_pressao_kn_m2")
    trd = _regra(R, "fita_trd_kn")
    fitas_min = int(_regra(R, "fitas_min_por_linha"))

    niveis = con.execute(
        "SELECT indice, cota_m, pe_direito_m FROM nivel WHERE projeto_id = ?"
        " ORDER BY indice", (projeto_id,)).fetchall()
    if not niveis:
        raise DadoIndisponivel(f"projeto {projeto_id} sem níveis")
    menor = min(n[0] for n in niveis)
    cota_base = next(c for i, c, _ in niveis if i == menor)
    topo = max(c + pd for _, c, pd in niveis)
    altura = topo - cota_base

    externas = con.execute(
        "SELECT a.x, a.y, b.x, b.y FROM parede p"
        "  JOIN no_planta a ON a.id = p.no_a"
        "  JOIN no_planta b ON b.id = p.no_b"
        "  JOIN nivel n ON n.id = p.nivel_id"
        " WHERE n.projeto_id = ? AND n.indice = ? AND p.externa = 1",
        (projeto_id, menor)).fetchall()
    if not externas:
        raise DadoIndisponivel(
            f"projeto {projeto_id} sem paredes externas no nível {menor} — não"
            " há fachada para o vento nem linha de contraventamento")
    xs = [v for ax, _, bx, _ in externas for v in (ax, bx)]
    zs = [v for _, az, _, bz in externas for v in (az, bz)]
    larg_x, larg_z = max(xs) - min(xs), max(zs) - min(zs)

    origem = (f"NBR 6123 simplificada: q={q} kN/m² × h={altura:.1f} m ×"
              f" fachada; T_Rd={trd} kN/fita [NBR 14762]; mínimo"
              f" {fitas_min} fitas/linha")

    direcoes: list[DirecaoVento] = []
    pendencias: list[str] = []
    # vento na direção x atinge a fachada cuja largura é a extensão em z
    for direcao, largura in (("x", larg_z), ("z", larg_x)):
        f = q * altura * largura
        necessarias = max(1, math.ceil(f / (2 * trd)))
        direcoes.append(DirecaoVento(
            direcao=direcao, f_kn=round(f, 2),
            fitas_necessarias=necessarias,
            fitas_adotadas=max(necessarias, fitas_min)))
        if necessarias > fitas_min:
            pendencias.append(
                f"{MARCA_PENDENCIA} Vento na direção {direcao}: F={f:.0f} kN"
                f" exige {necessarias} fitas/linha — acima do mínimo de"
                f" {fitas_min} [NBR 6123 simplificada, T_Rd={trd} kN]."
                " O contraventamento padrão não fecha: exige verificação de"
                " engenheiro estrutural e reforço das linhas.")

    hold_downs = 4 * 2 * 2 + 4 * 2
    return ResultadoVento(direcoes=direcoes, hold_downs_un=hold_downs,
                          pendencias=pendencias, confianca="parametrico",
                          origem_regra=origem)


def derivar_fundacao(con, projeto_id: int) -> dict:
    """Pré-dimensiona, verifica o vento e grava: m³ na folha 02.01 (PARAMETRICO,
    com a guarda de linha MANUAL/TAKEOFF dos outros motores) + pendências
    BLOQUEANTES em `pendencia` (motor='fundacao': S1, vento acima do mínimo).

    Sondagem pendente NÃO entra na tabela: ela rebaixa a confiança e vira
    carimbo na proposta — bloquear todo projeto sem sondagem mataria o modo
    proposta, que existe exatamente para vender com a incerteza etiquetada.
    Vai no retorno como `avisos`.

    Bloqueado (S1): o PARAMETRICO anterior da 02.01 é REMOVIDO (solo que piorou
    não pode deixar m³ velho na EAP) — a macroetapa 02 zera e o R7 também
    bloqueia: dupla proteção."""
    r = pre_dimensionar(con, projeto_id)
    vento = verificar_vento(con, projeto_id)

    avisos = [] if r.bloqueado else list(r.pendencias)
    bloqueantes = (list(r.pendencias) if r.bloqueado else []) + list(vento.pendencias)

    folha = con.execute(
        "SELECT id FROM eap_item WHERE codigo = '02.01'").fetchone()
    if folha is None:
        raise DadoIndisponivel("EAP sem a folha 02.01 (baldrame, m³)")

    con.execute("DELETE FROM pendencia WHERE projeto_id = ? AND motor = 'fundacao'",
                (projeto_id,))
    for msg in bloqueantes:
        con.execute(
            "INSERT OR IGNORE INTO pendencia (projeto_id, motor, mensagem)"
            " VALUES (?, 'fundacao', ?)", (projeto_id, msg))

    resultado = {
        "volume_m3": r.volume_m3, "confianca": r.confianca,
        "bloqueado": r.bloqueado, "avisos": avisos, "pendencias": bloqueantes,
        "vento": vento, "hold_downs_un": vento.hold_downs_un,
        "n_paredes": len(r.paredes),
        "governa_minimo": sum(1 for f in r.paredes
                              if f.governa == "mínimo construtivo"),
    }
    if r.bloqueado:
        con.execute(
            "DELETE FROM quantitativo WHERE projeto_id = ? AND eap_item_id = ?"
            " AND origem = 'PARAMETRICO'", (projeto_id, folha[0]))
        con.commit()
        return {**resultado, "gravado": False}

    cur = con.execute(
        "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem,"
        " confianca, origem_regra) VALUES (?,?,?,'PARAMETRICO',?,?)"
        " ON CONFLICT (projeto_id, eap_item_id) DO UPDATE SET"
        "   quantidade=excluded.quantidade, origem=excluded.origem,"
        "   confianca=excluded.confianca, origem_regra=excluded.origem_regra"
        " WHERE quantitativo.origem = 'PARAMETRICO'",
        (projeto_id, folha[0], r.volume_m3, r.confianca,
         f"{r.origem_regra} · {resultado['governa_minimo']}/{len(r.paredes)}"
         " paredes governadas pelo mínimo construtivo"))
    if cur.rowcount == 0:
        origem = con.execute(
            "SELECT origem FROM quantitativo WHERE projeto_id = ? AND eap_item_id = ?",
            (projeto_id, folha[0])).fetchone()[0]
        con.commit()
        return {**resultado, "gravado": False, "preservado": origem}
    con.commit()
    return {**resultado, "gravado": True}
