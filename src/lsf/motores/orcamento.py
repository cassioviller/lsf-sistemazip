"""MOTOR 1 — Orçamento (Fase 1).
Contratos (ver CLAUDE.md, Fase atual):
  custo_composicao(con, composicao_id, referencia, uf, desonerado) -> (custo, confianca) [pronto]
  custo_direto_projeto(con, projeto_id) -> OrcamentoDireto (linhas + subtotais + total)  [pronto]
  aplicar_bdi(orcamento, params) -> OrcamentoVenda   # fórmula TCU (provada no spike 3)  [pronto]
Aceite da fase: reproduzir 1 orçamento Veks real com desvio <= 2%.

Este motor não lê `vw_custo_composicao`: a view resolve 1 nível e usa INNER JOIN, então
sub-composições e insumos sem preço somem da soma sem sinal. Aqui, dado ausente é erro —
confiança etiqueta incerteza, não ausência.

O projeto trava REFERÊNCIA (D5), não `data_base_id`: cada insumo é precificado na data-base
da SUA fonte naquela referência. É o que permite a composição própria D7 usar mão de obra
SINAPI e material VEKS — elas vivem em data-bases distintas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# D4 — ordem de confiança; a pior vence na propagação. Não é a ordem alfabética
# ('estimado' < 'parametrico' < 'real'), por isso MIN() sobre a string dá resposta errada.
CONFIANCA_RANK = {"real": 0, "estimado": 1, "parametrico": 2}


def pior_confianca(*confiancas: str) -> str:
    """Pior confiança entre as informadas (D4)."""
    fora = [c for c in confiancas if c not in CONFIANCA_RANK]
    if fora:
        raise ValueError(f"confiança fora do domínio: {fora!r}")
    return max(confiancas, key=lambda c: CONFIANCA_RANK[c])


class OrcamentoError(Exception):
    pass


class CustoIndisponivel(OrcamentoError):
    """Sem analítica, ou insumo sem preço na data-base pedida."""


class CicloDeComposicao(OrcamentoError):
    """Composição que contém a si mesma, direta ou indiretamente."""


class PrecoAmbiguo(OrcamentoError):
    """Mais de uma data-base candidata para o mesmo insumo na referência pedida."""


def custo_composicao(con, composicao_id, referencia, uf=None, desonerado=0):
    """Custo unitário direto da composição, resolvendo aninhamento recursivamente.

    `referencia` é 'YYYY-MM'. Cada insumo é precificado na data-base da sua própria fonte
    nessa referência, preferindo a base da `uf` pedida sobre a base nacional (uf NULL).

    Devolve (custo_unitario, confianca), onde confianca é a pior entre a da própria
    composição e a de cada componente, recursivamente (D4). Nunca devolve custo parcial:
    levanta CustoIndisponivel se faltar analítica ou preço, PrecoAmbiguo se houver mais de
    uma base candidata, e CicloDeComposicao se a recursão se fechar sobre si mesma.
    """
    base = (referencia, uf, desonerado)
    return _custo(con, composicao_id, base, pilha=(), memo={})


def _custo(con, composicao_id, base, pilha, memo):
    if composicao_id in memo:
        return memo[composicao_id]
    if composicao_id in pilha:
        caminho = " -> ".join(str(c) for c in (*pilha, composicao_id))
        raise CicloDeComposicao(f"composição contém a si mesma: {caminho}")

    cabecalho = con.execute(
        "SELECT codigo_fonte, confianca FROM composicao WHERE id = ?", (composicao_id,)
    ).fetchone()
    if cabecalho is None:
        raise CustoIndisponivel(f"composição id={composicao_id} não existe")
    codigo, confianca = cabecalho

    itens = con.execute(
        "SELECT item_tipo, item_id, coeficiente FROM composicao_item WHERE composicao_id = ?",
        (composicao_id,),
    ).fetchall()
    if not itens:
        raise CustoIndisponivel(f"composição {codigo} não tem analítica cadastrada")

    custo = 0.0
    for item_tipo, item_id, coeficiente in itens:
        if item_tipo == "INSUMO":
            preco, conf_item = _preco_insumo(con, item_id, base, codigo)
        elif item_tipo == "COMPOSICAO":
            preco, conf_item = _custo(con, item_id, base, (*pilha, composicao_id), memo)
        else:
            raise OrcamentoError(f"item_tipo inválido em {codigo}: {item_tipo!r}")
        custo += coeficiente * preco
        confianca = pior_confianca(confianca, conf_item)

    memo[composicao_id] = (custo, confianca)
    return memo[composicao_id]


def _preco_insumo(con, insumo_id, base, codigo_composicao):
    referencia, uf, desonerado = base
    # A data-base é a da FONTE do insumo. Base da UF pedida ganha da base nacional (uf NULL).
    linhas = con.execute(
        "SELECT ip.preco, ip.confianca, db.uf"
        "  FROM insumo i"
        "  JOIN data_base db ON db.fonte_id = i.fonte_id"
        "  JOIN insumo_preco ip ON ip.insumo_id = i.id AND ip.data_base_id = db.id"
        " WHERE i.id = ? AND db.referencia = ? AND db.desonerado = ?"
        "   AND (db.uf = ? OR db.uf IS NULL)",
        (insumo_id, referencia, desonerado, uf),
    ).fetchall()

    if not linhas:
        # item_id é FK lógica: o insumo pode nem existir. Distingue os dois casos.
        existe = con.execute("SELECT codigo_fonte FROM insumo WHERE id = ?", (insumo_id,)).fetchone()
        alvo = f"insumo {existe[0]}" if existe else f"insumo id={insumo_id} (inexistente)"
        raise CustoIndisponivel(
            f"{alvo}, usado por {codigo_composicao}, sem preço na referência {referencia}"
            f" (uf={uf}, desonerado={desonerado})"
        )

    exatas = [l for l in linhas if l[2] == uf]
    candidatas = exatas or linhas
    if len(candidatas) > 1:
        codigo_insumo = con.execute(
            "SELECT codigo_fonte FROM insumo WHERE id = ?", (insumo_id,)
        ).fetchone()[0]
        raise PrecoAmbiguo(
            f"insumo {codigo_insumo}, usado por {codigo_composicao}, tem {len(candidatas)}"
            f" data-bases candidatas em {referencia}"
        )
    preco, confianca, _ = candidatas[0]
    return preco, confianca


# ============ custo direto do projeto (item 3 do contrato) ============

@dataclass(frozen=True)
class LinhaOrcamento:
    eap_codigo: str
    descricao: str
    unidade: str
    quantidade: float
    origem: str
    custo_unitario: float | None   # None = pendência (nunca custo parcial)
    custo_total: float | None
    confianca: str | None          # pior entre quantitativo e composição (D4)
    pendencia: str | None = None


@dataclass(frozen=True)
class SubtotalMacroetapa:
    eap_codigo: str
    descricao: str
    grupo_eap: str
    custo: float | None            # None se zerada ou se alguma linha está pendente
    confianca: str | None
    zerada: bool                   # nenhum quantitativo — insumo do gate R7


@dataclass(frozen=True)
class OrcamentoDireto:
    projeto_codigo: str
    referencia: str
    uf: str | None
    desonerado: int
    linhas: list[LinhaOrcamento]
    subtotais: list[SubtotalMacroetapa]
    total: float | None            # None enquanto houver pendência: orçamento não fecha
    confianca: str | None
    pendencias: list[str] = field(default_factory=list)
    macroetapas_zeradas: list[str] = field(default_factory=list)


def custo_direto_projeto(con, projeto_id):
    """Custo direto do projeto: linhas por folha da EAP, subtotais por macroetapa, total.

    Cada linha vale quantidade × custo_composicao na referência travada pelo projeto (D5),
    com confiança = pior entre a do quantitativo e a da composição (D4). Linha que não
    precifica vira pendência com motivo — e o total fica None: um orçamento turn-key que
    soma R$ 0,00 num item é pior do que um que se recusa a fechar (R7).
    """
    proj = con.execute(
        "SELECT codigo, referencia, uf, desonerado FROM projeto WHERE id = ?", (projeto_id,)
    ).fetchone()
    if proj is None:
        raise OrcamentoError(f"projeto id={projeto_id} não existe")
    projeto_codigo, referencia, uf, desonerado = proj

    linhas: list[LinhaOrcamento] = []
    pendencias: list[str] = []
    linhas_por_macro: dict[int, list[LinhaOrcamento]] = {}

    quantitativos = con.execute(
        "SELECT q.quantidade, q.origem, q.confianca,"
        "       e.id, e.codigo, e.descricao, e.unidade, e.composicao_id"
        "  FROM quantitativo q JOIN eap_item e ON e.id = q.eap_item_id"
        " WHERE q.projeto_id = ? ORDER BY e.codigo",
        (projeto_id,),
    ).fetchall()

    for qtd, origem, conf_qtd, eap_id, codigo, descricao, unidade, composicao_id in quantitativos:
        try:
            unitario, conf_comp = custo_composicao(con, composicao_id, referencia, uf, desonerado)
            linha = LinhaOrcamento(
                codigo, descricao, unidade, qtd, origem,
                unitario, qtd * unitario, pior_confianca(conf_qtd, conf_comp),
            )
        except OrcamentoError as erro:
            linha = LinhaOrcamento(
                codigo, descricao, unidade, qtd, origem, None, None, None, pendencia=str(erro)
            )
            pendencias.append(f"{codigo}: {erro}")
        linhas.append(linha)
        linhas_por_macro.setdefault(_macroetapa_de(con, eap_id), []).append(linha)

    subtotais: list[SubtotalMacroetapa] = []
    zeradas: list[str] = []
    macros = con.execute(
        "SELECT id, codigo, descricao, grupo_eap FROM eap_item WHERE pai_id IS NULL ORDER BY codigo"
    ).fetchall()
    for macro_id, codigo, descricao, grupo in macros:
        do_grupo = linhas_por_macro.get(macro_id, [])
        if not do_grupo:
            zeradas.append(codigo)
            subtotais.append(SubtotalMacroetapa(codigo, descricao, grupo, None, None, zerada=True))
            continue
        completas = [l for l in do_grupo if l.custo_total is not None]
        custo = sum(l.custo_total for l in completas) if len(completas) == len(do_grupo) else None
        confianca = pior_confianca(*(l.confianca for l in completas)) if completas else None
        subtotais.append(SubtotalMacroetapa(codigo, descricao, grupo, custo, confianca, zerada=False))

    if not linhas:
        pendencias.append("projeto sem nenhum quantitativo")
    total = sum(l.custo_total for l in linhas) if linhas and not pendencias else None
    conf_linhas = [l.confianca for l in linhas if l.confianca is not None]
    confianca_geral = pior_confianca(*conf_linhas) if conf_linhas else None

    return OrcamentoDireto(
        projeto_codigo, referencia, uf, desonerado,
        linhas, subtotais, total, confianca_geral, pendencias, zeradas,
    )


def _macroetapa_de(con, eap_id, _limite=32):
    """Sobe a hierarquia da EAP até a raiz (macroetapa)."""
    atual = eap_id
    for _ in range(_limite):
        pai = con.execute("SELECT pai_id FROM eap_item WHERE id = ?", (atual,)).fetchone()
        if pai is None:
            raise OrcamentoError(f"eap_item id={atual} não existe")
        if pai[0] is None:
            return atual
        atual = pai[0]
    raise OrcamentoError(f"hierarquia da EAP não termina (ciclo?) a partir de id={eap_id}")


# ============ BDI e preço de venda (item 4 do contrato) ============

CHAVES_BDI = ("bdi_ac", "bdi_s", "bdi_r", "bdi_g", "bdi_df", "bdi_l", "bdi_i")


@dataclass(frozen=True)
class ParametrosBDI:
    ac: float
    s: float
    r: float
    g: float
    df: float
    l: float
    i: float
    confianca: str = "estimado"


def bdi_tcu(p: ParametrosBDI) -> float:
    """Fórmula do Acórdão TCU 2622/2013: ((1+AC+S+R+G)·(1+DF)·(1+L))/(1−I) − 1."""
    if not 0.0 <= p.i < 1.0:
        raise OrcamentoError(f"I (impostos) fora de [0,1): {p.i}")
    if min(p.ac, p.s, p.r, p.g, p.df, p.l) < 0:
        raise OrcamentoError("componente de BDI negativo")
    return ((1 + p.ac + p.s + p.r + p.g) * (1 + p.df) * (1 + p.l)) / (1 - p.i) - 1


def carregar_parametros_bdi(con) -> ParametrosBDI:
    """Lê o BDI decomposto de `parametros_globais`; confiança = pior componente (D4)."""
    linhas = dict(
        (chave, (valor, confianca))
        for chave, valor, confianca in con.execute(
            f"SELECT chave, valor, confianca FROM parametros_globais"
            f" WHERE chave IN ({','.join('?' * len(CHAVES_BDI))})",
            CHAVES_BDI,
        )
    )
    faltando = [c for c in CHAVES_BDI if c not in linhas]
    if faltando:
        raise OrcamentoError(f"parametros_globais sem chaves de BDI: {faltando}")
    valores = {c.removeprefix("bdi_"): linhas[c][0] for c in CHAVES_BDI}
    confianca = pior_confianca(*(linhas[c][1] for c in CHAVES_BDI))
    return ParametrosBDI(**valores, confianca=confianca)


@dataclass(frozen=True)
class LinhaVenda:
    eap_codigo: str
    descricao: str
    unidade: str
    quantidade: float
    origem: str
    custo_unitario: float | None
    custo_direto: float | None
    preco_venda: float | None      # custo_direto × (1 + BDI); None se pendente
    confianca: str | None          # pior entre a linha e os parâmetros do BDI (D4)
    pendencia: str | None = None


@dataclass(frozen=True)
class OrcamentoVenda:
    orcamento: OrcamentoDireto     # custo direto permanece visível separadamente
    parametros: ParametrosBDI
    bdi: float
    linhas: list[LinhaVenda]
    preco_total: float | None      # None enquanto o custo direto não fecha
    confianca: str | None


def aplicar_bdi(orcamento: OrcamentoDireto, params: ParametrosBDI) -> OrcamentoVenda:
    """Preço de venda por linha e total. O BDI 'estimado' rebaixa a confiança do preço
    mesmo quando o custo direto é 'real' (D4): a incerteza do markup é incerteza do preço."""
    bdi = bdi_tcu(params)
    linhas = []
    for l in orcamento.linhas:
        pendente = l.custo_total is None
        linhas.append(LinhaVenda(
            l.eap_codigo, l.descricao, l.unidade, l.quantidade, l.origem,
            l.custo_unitario, l.custo_total,
            None if pendente else l.custo_total * (1 + bdi),
            None if pendente else pior_confianca(l.confianca, params.confianca),
            l.pendencia,
        ))
    preco_total = None if orcamento.total is None else orcamento.total * (1 + bdi)
    confs = [l.confianca for l in linhas if l.confianca is not None]
    return OrcamentoVenda(
        orcamento, params, bdi, linhas, preco_total,
        pior_confianca(*confs) if confs else None,
    )
