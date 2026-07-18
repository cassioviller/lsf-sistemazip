"""MOTOR 2 — Cronograma (Fase 4): CPM sobre a MESMA EAP do orçamento (D1).

Atividade = macroetapa com quantitativo. A duração é DERIVADA, não digitada:
homem-horas = Σ (quantidade da folha × horas de MO por unidade da composição,
recursivo como o custo) ÷ (equipe do grupo × jornada). A rede de precedências
(TI/II/TT com lag, migração 015) é DADO com origem anotada — o motor só executa.

Convenção de vínculos (atividade CONTÍGUA, não esticável):
  TI: ES_succ ≥ EF_pred + lag       (o FS clássico)
  II: ES_succ ≥ ES_pred + lag
  TT: EF_succ ≥ EF_pred + lag  →  ES_succ ≥ EF_pred + lag − dur_succ

Dias CORRIDOS (jornada_h_dia converte hh em dias; calendário de obra entra na
calibração R6 — documentado, não escondido). GERENCIAMENTO é hammock: não entra
no CPM; acompanha o makespan com o custo diluído.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from lsf.geradores.estrutura import DadoIndisponivel
from lsf.motores.orcamento import (CustoIndisponivel, OrcamentoError,
                                   custo_direto_projeto, pior_confianca)


class CicloNaRede(OrcamentoError):
    """Rede de precedências cíclica: CPM não tem resposta — dado errado."""


@dataclass(frozen=True)
class Atividade:
    grupo: str                 # grupo_eap da macroetapa
    codigo: str                # código EAP ('02', '03'...)
    descricao: str
    duracao_dias: int
    custo: float | None        # subtotal da macroetapa; None = pendência
    hh: float                  # homem-horas derivadas
    confianca: str


@dataclass(frozen=True)
class AtividadeProgramada:
    atividade: Atividade
    es: float
    ef: float
    ls: float
    lf: float
    folga: float
    critica: bool
    hammock: bool = False


@dataclass(frozen=True)
class Cronograma:
    projeto_codigo: str
    atividades: list[AtividadeProgramada]
    makespan_dias: float
    alertas: list[str]
    confianca: str
    # vínculos efetivos (só entre atividades presentes) — a exportação MSPDI
    # precisa deles; hammock não entra em vínculo
    rede: list[tuple[str, str, str, float]] = None


def horas_mo_composicao(con, composicao_id: int, _pilha: tuple = ()) -> float:
    """Horas de mão de obra por unidade da composição, recursivo como o custo.
    Sem analítica = exceção, nunca 0 h (0 h viraria atividade instantânea calada)."""
    if composicao_id in _pilha:
        caminho = " -> ".join(str(c) for c in (*_pilha, composicao_id))
        raise CicloNaRede(f"composição contém a si mesma: {caminho}")
    itens = con.execute(
        "SELECT item_tipo, item_id, coeficiente FROM composicao_item"
        " WHERE composicao_id = ?", (composicao_id,)).fetchall()
    if not itens:
        codigo = con.execute("SELECT codigo_fonte FROM composicao WHERE id = ?",
                             (composicao_id,)).fetchone()
        raise CustoIndisponivel(
            f"composição {codigo[0] if codigo else composicao_id} sem analítica"
            " — horas de MO indisponíveis (D4.1)")
    horas = 0.0
    for item_tipo, item_id, coef in itens:
        if item_tipo == "COMPOSICAO":
            horas += coef * horas_mo_composicao(con, item_id,
                                                (*_pilha, composicao_id))
        else:
            tipo = con.execute("SELECT tipo FROM insumo WHERE id = ?",
                               (item_id,)).fetchone()
            if tipo and tipo[0] == "MO":
                horas += coef
    return horas


def montar_atividades(con, projeto_id: int) -> tuple[list[Atividade], list[str]]:
    """Macroetapas com quantitativo viram atividades; as zeradas ficam FORA com
    alerta (o gate R7 já bloqueia a publicação — o cronograma do que existe
    continua computável). Devolve (atividades sem hammock, alertas)."""
    orc = custo_direto_projeto(con, projeto_id)
    jornada_row = con.execute(
        "SELECT valor FROM regra_lsf WHERE chave='jornada_h_dia'").fetchone()
    if jornada_row is None:
        raise DadoIndisponivel("regra_lsf sem 'jornada_h_dia'")
    jornada = jornada_row[0]

    equipes = {g: (t, h) for g, t, h in con.execute(
        "SELECT grupo_eap, trabalhadores, hammock FROM equipe_macroetapa")}

    # hh e confiança por grupo, a partir das MESMAS folhas do orçamento (D1)
    hh_por_grupo: dict[str, float] = {}
    conf_por_grupo: dict[str, str] = {}
    pend_por_grupo: dict[str, str] = {}
    for codigo, comp_id, grupo, qtd, conf in con.execute(
            "SELECT e.codigo, e.composicao_id, e.grupo_eap, q.quantidade,"
            "       q.confianca"
            "  FROM quantitativo q JOIN eap_item e ON e.id = q.eap_item_id"
            " WHERE q.projeto_id = ? AND e.composicao_id IS NOT NULL",
            (projeto_id,)):
        try:
            hh = qtd * horas_mo_composicao(con, comp_id)
        except CustoIndisponivel as e:
            pend_por_grupo[grupo] = str(e)
            continue
        hh_por_grupo[grupo] = hh_por_grupo.get(grupo, 0.0) + hh
        conf_por_grupo[grupo] = pior_confianca(
            conf_por_grupo.get(grupo, "real"), conf, "estimado")

    atividades: list[Atividade] = []
    alertas = [f"macroetapa {c} sem quantitativo — fora do cronograma"
               f" (o gate R7 bloqueia a publicação)"
               for c in orc.macroetapas_zeradas]
    for sub in orc.subtotais:
        if sub.zerada:
            continue
        if sub.grupo_eap in pend_por_grupo:
            alertas.append(
                f"macroetapa {sub.eap_codigo}: duração indisponível —"
                f" {pend_por_grupo[sub.grupo_eap]} — fora do cronograma")
            continue
        if sub.grupo_eap not in equipes:
            raise DadoIndisponivel(
                f"equipe_macroetapa sem o grupo '{sub.grupo_eap}'")
        trabalhadores, hammock = equipes[sub.grupo_eap]
        if hammock:
            continue                       # entra depois do CPM, sobre o makespan
        hh = hh_por_grupo.get(sub.grupo_eap, 0.0)
        atividades.append(Atividade(
            grupo=sub.grupo_eap, codigo=sub.eap_codigo, descricao=sub.descricao,
            duracao_dias=max(1, math.ceil(hh / (trabalhadores * jornada))),
            custo=sub.custo, hh=round(hh, 1),
            confianca=conf_por_grupo.get(sub.grupo_eap, "estimado")))
    return atividades, alertas


def cpm(atividades: list[Atividade],
        precedencias: list[tuple[str, str, str, float]],
        ) -> tuple[list[AtividadeProgramada], float]:
    """Passagem direta/inversa generalizada para TI/II/TT com lag (spike 2 é o
    caso particular só-TI). Vínculo com ponta fora do conjunto de atividades é
    ignorado (macroetapa zerada não trava a rede das presentes)."""
    presentes = {a.grupo: a for a in atividades}
    rede = [(p, s, t, lag) for p, s, t, lag in precedencias
            if p in presentes and s in presentes]

    # ordem topológica com detecção de ciclo
    entrantes: dict[str, list[tuple[str, str, float]]] = {g: [] for g in presentes}
    saintes: dict[str, list[tuple[str, str, float]]] = {g: [] for g in presentes}
    for p, s, t, lag in rede:
        entrantes[s].append((p, t, lag))
        saintes[p].append((s, t, lag))
    ordem: list[str] = []
    estado: dict[str, int] = {}

    def visita(g: str):
        if estado.get(g) == 2:
            return
        if estado.get(g) == 1:
            raise CicloNaRede(f"rede de precedências cíclica passando por {g}")
        estado[g] = 1
        for s, _, _ in saintes[g]:
            visita(s)
        estado[g] = 2
        ordem.append(g)

    for g in presentes:
        visita(g)
    ordem.reverse()

    es: dict[str, float] = {}
    ef: dict[str, float] = {}
    for g in ordem:
        dur = presentes[g].duracao_dias
        inicio = 0.0
        for p, tipo, lag in entrantes[g]:
            if tipo == "TI":
                inicio = max(inicio, ef[p] + lag)
            elif tipo == "II":
                inicio = max(inicio, es[p] + lag)
            else:  # TT
                inicio = max(inicio, ef[p] + lag - dur)
        es[g], ef[g] = inicio, inicio + dur
    makespan = max(ef.values(), default=0.0)

    lf: dict[str, float] = {}
    ls: dict[str, float] = {}
    for g in reversed(ordem):
        dur = presentes[g].duracao_dias
        fim = makespan
        for s, tipo, lag in saintes[g]:
            if tipo == "TI":
                fim = min(fim, ls[s] - lag)
            elif tipo == "II":
                fim = min(fim, ls[s] - lag + dur)
            else:  # TT
                fim = min(fim, lf[s] - lag)
        lf[g], ls[g] = fim, fim - dur

    prog = [AtividadeProgramada(
        atividade=a, es=es[g], ef=ef[g], ls=ls[g], lf=lf[g],
        folga=round(ls[g] - es[g], 6), critica=abs(ls[g] - es[g]) < 1e-9)
        for g, a in presentes.items()]
    prog.sort(key=lambda p: (p.es, p.atividade.codigo))
    return prog, makespan


def cronograma_projeto(con, projeto_id: int) -> Cronograma:
    atividades, alertas = montar_atividades(con, projeto_id)
    if not atividades:
        raise DadoIndisponivel(
            f"projeto {projeto_id} sem macroetapa com quantitativo — não há o"
            " que programar")
    rede = con.execute(
        "SELECT grupo_pred, grupo_succ, tipo, lag_dias"
        "  FROM precedencia_macroetapa").fetchall()
    prog, makespan = cpm(atividades, [tuple(r) for r in rede])

    # hammock (GERENCIAMENTO): acompanha o projeto inteiro; só entra se tiver
    # custo lançado — ausência é escopo (alerta), nunca custo zero inventado
    orc = custo_direto_projeto(con, projeto_id)
    for sub in orc.subtotais:
        eq = con.execute(
            "SELECT trabalhadores FROM equipe_macroetapa WHERE grupo_eap = ?"
            " AND hammock = 1", (sub.grupo_eap,)).fetchone()
        if eq is None:
            continue
        if sub.zerada:
            alertas.append(
                f"macroetapa {sub.eap_codigo} (hammock) sem quantitativo —"
                " gerenciamento fora da curva")
            continue
        prog.append(AtividadeProgramada(
            atividade=Atividade(
                grupo=sub.grupo_eap, codigo=sub.eap_codigo,
                descricao=sub.descricao, duracao_dias=math.ceil(makespan),
                custo=sub.custo, hh=0.0, confianca=sub.confianca or "estimado"),
            es=0.0, ef=makespan, ls=0.0, lf=makespan, folga=0.0,
            critica=False, hammock=True))

    projeto = con.execute("SELECT codigo FROM projeto WHERE id = ?",
                          (projeto_id,)).fetchone()
    confianca = pior_confianca(
        *(p.atividade.confianca for p in prog), "estimado")
    presentes = {p.atividade.grupo for p in prog if not p.hammock}
    return Cronograma(projeto_codigo=projeto[0], atividades=prog,
                      makespan_dias=makespan, alertas=alertas,
                      confianca=confianca,
                      rede=[tuple(r) for r in rede
                            if r[0] in presentes and r[1] in presentes])


def custo_composicao_por_tipo(con, composicao_id: int, referencia: str,
                              uf=None, desonerado: int = 0,
                              _pilha: tuple = ()) -> dict[str, float]:
    """Custo unitário repartido por tipo de insumo (MAT/MO/...), recursivo e
    consistente com `custo_composicao`: a soma dos tipos É o custo unitário.
    É o que permite a curva S pesar material no início (aço adiantado) sem
    inventar proporção."""
    from lsf.motores.orcamento import _preco_insumo

    if composicao_id in _pilha:
        caminho = " -> ".join(str(c) for c in (*_pilha, composicao_id))
        raise CicloNaRede(f"composição contém a si mesma: {caminho}")
    itens = con.execute(
        "SELECT item_tipo, item_id, coeficiente FROM composicao_item"
        " WHERE composicao_id = ?", (composicao_id,)).fetchall()
    if not itens:
        codigo = con.execute("SELECT codigo_fonte FROM composicao WHERE id = ?",
                             (composicao_id,)).fetchone()
        raise CustoIndisponivel(
            f"composição {codigo[0] if codigo else composicao_id} sem analítica")
    base = (referencia, uf, desonerado)
    por_tipo: dict[str, float] = {}
    for item_tipo, item_id, coef in itens:
        if item_tipo == "COMPOSICAO":
            filho = custo_composicao_por_tipo(con, item_id, referencia, uf,
                                              desonerado, (*_pilha, composicao_id))
            for t, v in filho.items():
                por_tipo[t] = por_tipo.get(t, 0.0) + coef * v
        else:
            tipo = con.execute("SELECT tipo, codigo_fonte FROM insumo"
                               " WHERE id = ?", (item_id,)).fetchone()
            preco, _ = _preco_insumo(con, item_id, base,
                                     f"composicao id={composicao_id}")
            por_tipo[tipo[0]] = por_tipo.get(tipo[0], 0.0) + coef * preco
    return por_tipo


@dataclass(frozen=True)
class CurvaS:
    desembolso: list[float]    # R$ por dia (dias corridos do cronograma)
    acumulado: list[float]
    total: float
    confianca: str


def curva_s(con, projeto_id: int, cronograma: Cronograma) -> CurvaS:
    """Curva S físico-financeira PONDERADA: a parcela MATERIAL de cada atividade
    desembolsa no dia do INÍCIO dela (aço adiantado — o kit LSF é comprado antes
    da montagem), o resto uniforme na duração; hammock uniforme no makespan.

    Fecha EXATAMENTE no total do custo direto por construção (D1): cada linha do
    orçamento é repartida pelas FRAÇÕES por tipo da sua composição, e frações
    somam 1. Orçamento com pendência (total None) não tem curva parcial (D4.1)."""
    orc = custo_direto_projeto(con, projeto_id)
    if orc.total is None:
        raise CustoIndisponivel(
            "orçamento não fecha (pendências: "
            + "; ".join(orc.pendencias or ["total indisponível"]) + ")"
            " — curva S parcial não existe (D4.1)")

    prog_por_grupo = {p.atividade.grupo: p for p in cronograma.atividades}
    dias = int(math.ceil(cronograma.makespan_dias))
    desembolso = [0.0] * dias

    for linha in orc.linhas:
        folha = con.execute(
            "SELECT composicao_id, grupo_eap FROM eap_item WHERE codigo = ?",
            (linha.eap_codigo,)).fetchone()
        comp_id, grupo = folha
        prog = prog_por_grupo.get(grupo)
        if prog is None:
            raise CustoIndisponivel(
                f"folha {linha.eap_codigo} custeada mas a macroetapa {grupo}"
                " está fora do cronograma — a curva não fecharia")
        por_tipo = custo_composicao_por_tipo(
            con, comp_id, orc.referencia, orc.uf, orc.desonerado)
        soma_tipos = sum(por_tipo.values())
        frac_mat = (por_tipo.get("MAT", 0.0) / soma_tipos) if soma_tipos else 0.0
        mat = linha.custo_total * frac_mat
        resto = linha.custo_total - mat

        if prog.hammock:
            for t in range(dias):
                desembolso[t] += linha.custo_total / dias
            continue
        d0, d1 = int(prog.es), int(prog.ef)
        desembolso[min(d0, dias - 1)] += mat
        for t in range(d0, min(d1, dias)):
            desembolso[t] += resto / (d1 - d0)

    acumulado = []
    soma = 0.0
    for v in desembolso:
        soma += v
        acumulado.append(round(soma, 2))
    return CurvaS(desembolso=[round(v, 2) for v in desembolso],
                  acumulado=acumulado, total=acumulado[-1],
                  confianca=pior_confianca(cronograma.confianca,
                                           orc.confianca or "estimado"))
