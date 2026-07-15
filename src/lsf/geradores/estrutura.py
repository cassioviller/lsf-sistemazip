"""Gerador de estrutura de paredes LSF — porta FIEL do gerarPecas do v7.

Cada bloco reproduz o algoritmo do calculador v7 (assets/, READ-ONLY), lendo
perfis e regras do banco em vez de constantes JS. Epsilons e ordem de operações
são contrato: o aceite compara peça a peça com o v7 headless.
origem_regra anota a proveniência de cada decisão, como o v7 fazia.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from lsf.motores.orcamento import pior_confianca


class DadoIndisponivel(Exception):
    """Perfil/regra/dado ausente é ERRO — nunca peça pulada, nunca kg parcial (D4.1)."""


def _round_js(x: float, nd: int = 0) -> float:
    """Math.round/toFixed do JS arredondam 0.5 para cima; round() do Python é
    banker's. A porta fiel exige o comportamento JS."""
    m = 10 ** nd
    return math.floor(x * m + 0.5) / m


@dataclass(frozen=True)
class Peca:
    tag: str
    tipo: str          # guia|montante|montante_ext|montante_curto|king|jack|
                       # verga_mont|verga_guia|peitoril|cripple|diagonal|bloqueador
    perfil: str
    x0: float
    y0: float
    x1: float
    y1: float
    comp: float
    origem_regra: str = ""


@dataclass(frozen=True)
class Acessorio:
    item: str
    qtd: float
    un: str


@dataclass(frozen=True)
class EstruturaParede:
    parede_id: int
    pecas: list[Peca]
    acessorios: list[Acessorio]
    alertas: list[str]
    juntas: list[float]
    n_paineis: int
    kg_por_perfil: dict[str, float]
    confianca: str


# ---------- leitura de conhecimento (dado ausente = DadoIndisponivel) ----------

def _regras(con: sqlite3.Connection) -> dict[str, float]:
    return {chave: valor for chave, valor in con.execute("SELECT chave, valor FROM regra_lsf")}


def _regra(regras: dict, chave: str) -> float:
    if chave not in regras:
        raise DadoIndisponivel(f"regra_lsf sem a chave '{chave}'")
    return regras[chave]


def _perfil(con, codigo: str) -> dict:
    linha = con.execute(
        "SELECT alma_mm, massa_kg_m FROM perfil_lsf WHERE codigo = ?", (codigo,)
    ).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"perfil '{codigo}' não cadastrado em perfil_lsf")
    return {"alma_mm": linha[0], "massa_kg_m": linha[1]}


def _guia_correspondente(con, perfil_montante: str) -> str:
    """Porta de perfilGuiaCorrespondente: guia_de[família] com a mesma espessura;
    se o código exato não existir, a primeira guia da família."""
    familia, _, t = perfil_montante.partition("#")
    g = con.execute(
        "SELECT familia_guia FROM guia_de WHERE familia_montante = ?", (familia,)
    ).fetchone()
    if g is None:
        raise DadoIndisponivel(f"guia_de sem a família '{familia}'")
    exato = f"{g[0]}#{t}"
    if con.execute("SELECT 1 FROM perfil_lsf WHERE codigo = ?", (exato,)).fetchone():
        return exato
    alternativa = con.execute(
        "SELECT codigo FROM perfil_lsf WHERE familia = ? ORDER BY codigo", (g[0],)
    ).fetchone()
    if alternativa is None:
        raise DadoIndisponivel(f"nenhuma guia da família '{g[0]}' em perfil_lsf")
    return alternativa[0]


def _perfil_verga(con, vao_larg: float, perfil_parede: str) -> tuple[str, str]:
    """Porta de perfilVerga: primeira faixa que acomoda o vão; NULL = perfil da parede."""
    faixas = con.execute(
        "SELECT faixa_ate_m, perfil_montante, perfil_guia FROM verga_escalonamento"
        " ORDER BY faixa_ate_m"
    ).fetchall()
    if not faixas:
        raise DadoIndisponivel("verga_escalonamento vazio")
    for ate, mont, guia in faixas:
        if vao_larg <= ate:
            return (mont or perfil_parede, guia or _guia_correspondente(con, perfil_parede))
    ate, mont, guia = faixas[-1]
    if mont is None or guia is None:
        raise DadoIndisponivel(f"vão de {vao_larg} m acima da última faixa de verga")
    return (mont, guia)


# ---------- o gerador ----------

def gerar_parede(con, parede_id: int, contrav: str | None = None,
                 vaos_contrav: int = 1) -> EstruturaParede:
    linha = con.execute(
        "SELECT p.externa, p.perfil_codigo, p.confianca,"
        "       a.x, a.y, b.x, b.y, n.pe_direito_m"
        "  FROM parede p"
        "  JOIN no_planta a ON a.id = p.no_a"
        "  JOIN no_planta b ON b.id = p.no_b"
        "  JOIN nivel n ON n.id = p.nivel_id"
        " WHERE p.id = ?", (parede_id,)
    ).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"parede {parede_id} não existe")
    externa, perfil_m, conf, ax, ay, bx, by, pd = tuple(linha)
    comp = math.hypot(bx - ax, by - ay)
    if comp <= 0 or pd <= 0:
        raise DadoIndisponivel(f"parede {parede_id} degenerada (comp={comp}, pd={pd})")
    if perfil_m is None:
        raise DadoIndisponivel(
            f"parede {parede_id} sem perfil_codigo — dado ausente é erro (D4.1)")

    R = _regras(con)
    perfil_g = _guia_correspondente(con, perfil_m)
    alma_m = _perfil(con, perfil_m)["alma_mm"] / 1000
    passo = _regra(R, "modulacao_lsf_m")
    barra = _regra(R, "barra_m")

    pecas: list[Peca] = []
    alertas: list[str] = []
    seq: dict[str, int] = {}

    def mk(pfx, tipo, perfil, x0, y0, x1, y1, origem=""):
        seq[pfx] = seq.get(pfx, 0) + 1
        c = math.hypot(x1 - x0, y1 - y0)
        p = Peca(f"{pfx}{seq[pfx]}", tipo, perfil, _round_js(x0, 4), _round_js(y0, 4),
                 _round_js(x1, 4), _round_js(y1, 4), _round_js(c, 4), origem)
        pecas.append(p)
        return p

    ops, conf = _aberturas(con, parede_id, comp, pd, R, alertas, conf)
    juntas, n_paineis = _panelizar(comp, ops, R)

    # ---- guias: por painel, segmentadas em barras (v7: TTOP/TBOT próprios) ----
    limites = [0.0, *juntas, comp]
    for i in range(len(limites) - 1):
        a, b = limites[i], limites[i + 1]
        for y, pfx in ((0.0, "TBOT"), (pd, "TTOP")):
            x = a
            while x < b - 1e-6:
                fim = min(x + barra, b)
                mk(pfx, "guia", perfil_g, x, y, fim, y,
                   origem="guia por painel [OBRA layout 1PV]")
                x = fim

    # ---- posições de montantes de campo ----
    xs: list[float] = []
    i = 0
    while i * passo < comp - 1e-3:
        xs.append(_round_js(i * passo, 4))
        i += 1
    xs.append(_round_js(comp, 4))

    _enquadrar_vaos(con, ops, xs, pd, perfil_m, alma_m, R, mk)          # Task 4
    _montantes_de_campo(ops, xs, juntas, comp, pd, perfil_m, alma_m, pecas, mk)
    _bloqueadores(ops, comp, pd, perfil_m, R, pecas, mk)                # Task 5
    acess = _contraventamento_e_ancoragem(                              # Task 5
        contrav, externa, vaos_contrav, ops, juntas, comp, pd,
        perfil_m, alma_m, R, pecas, mk)

    kg: dict[str, float] = {}
    massas: dict[str, float] = {}
    for p in pecas:
        if p.perfil not in massas:
            massas[p.perfil] = _perfil(con, p.perfil)["massa_kg_m"]
        kg[p.perfil] = kg.get(p.perfil, 0.0) + p.comp * massas[p.perfil]

    return EstruturaParede(parede_id, pecas, acess, alertas, juntas, n_paineis,
                           kg, conf)


def _aberturas(con, parede_id, comp, pd, R, alertas, conf):
    """Vãos com posição explícita (posicao_m NOT NULL): valida, clampa e converte
    para o formato interno do v7 (x0/larg/sill/head/janela). Vão inválido vira
    alerta e sai do desenho — nunca silêncio."""
    margem = _regra(R, "margem_abertura_m")
    entre = _regra(R, "folga_entre_aberturas_m")
    alt_min = _regra(R, "alt_min_porta_giro_m")
    ops = []
    ultimo_fim = -1.0
    for tipo, pos, larg, alt, peitoril, conf_vao in con.execute(
        "SELECT tipo, posicao_m, largura_m, altura_m, peitoril_m, confianca"
        "  FROM vao WHERE parede_id = ? ORDER BY posicao_m", (parede_id,)
    ).fetchall():
        conf = pior_confianca(conf, conf_vao)
        janela = tipo == "JANELA"
        if janela and peitoril is None:
            # v7 linha 248: `a.peitoril ?? R.peitorilPadrao` (nullish) — NULL é
            # "não informado" e usa a regra; 0 explícito é dado (porta-janela).
            # Regra ausente no banco = DadoIndisponivel (D4.1), nunca default
            # silencioso em código.
            peitoril = _regra(R, "peitoril_padrao_m")
        sill = min(peitoril, max(0.0, pd - alt - 0.05)) if janela else 0.0
        head = min(sill + alt, pd - 0.05)
        if larg > comp - 2 * margem:
            alertas.append(
                f"Vão de {larg} m não cabe numa parede de {comp:.2f} m (com folgas de borda).")
            continue
        if head - sill < 0.1:
            alertas.append("Abertura com altura inválida — ignorada.")
            continue
        if not janela and alt < alt_min - 1e-6:
            alertas.append(
                f"Porta com {alt:.2f} m: abaixo do vão mínimo (giro ≥{alt_min} m) [Guia Smart].")
        x0 = max(margem, min(pos, comp - margem - larg))
        if x0 < ultimo_fim + entre - 1e-6:
            alertas.append(f"Abertura de {larg} m sobreposta a outra — removida do desenho.")
            continue
        ops.append({"x0": x0, "larg": larg, "sill": sill, "head": head, "janela": janela})
        ultimo_fim = x0 + larg
    return ops, conf


def _panelizar(comp, ops, R):
    """Juntas fora dos vãos [OBRA layout 1PV] — junta NUNCA a <30cm da lateral."""
    n_paineis = max(1, math.ceil(comp / _regra(R, "largura_painel_max_m")))
    juntas = []
    for j in range(1, n_paineis):
        xj = comp * j / n_paineis
        o = next((o for o in ops if o["x0"] - 0.1 < xj < o["x0"] + o["larg"] + 0.1), None)
        if o:
            xj = (max(0.3, o["x0"] - 0.15)
                  if xj - o["x0"] < o["x0"] + o["larg"] - xj
                  else min(comp - 0.3, o["x0"] + o["larg"] + 0.15))
        juntas.append(_round_js(xj, 3))
    return sorted(set(juntas)), n_paineis


def _dentro_de_vao(ops, x):
    return any(o["x0"] + 0.02 < x < o["x0"] + o["larg"] - 0.02 for o in ops)


def _montantes_de_campo(ops, xs, juntas, comp, pd, perfil_m, alma_m, pecas, mk):
    kings_x = [p.x0 for p in pecas if p.tipo == "king"]
    for x in xs:
        if _dentro_de_vao(ops, x):
            continue
        if any(abs(kx - x) < alma_m * 1.2 for kx in kings_x):
            continue
        ext = x < 1e-3 or abs(x - comp) < 1e-3
        mk("E" if ext else "S", "montante_ext" if ext else "montante",
           perfil_m, x, 0, x, pd)
    for xj in juntas:
        # junta: cada painel traz seu montante de borda [OBRA layout]
        mk("E", "montante_ext", perfil_m, xj - alma_m / 2, 0, xj - alma_m / 2, pd)
        mk("E", "montante_ext", perfil_m, xj + alma_m / 2, 0, xj + alma_m / 2, pd)


# implementadas nas Tasks 4 e 5 — por ora, paredes sem vãos e sem HB/contraventamento:

def _enquadrar_vaos(con, ops, xs, pd, perfil_m, alma_m, R, mk):
    """Porta fiel do enquadramento LSF do v7: kings/jacks (duplos acima do limite),
    verga em caixa (2 montantes + 2 guias), peitoril de janela, cripples na
    modulação e diagonais sobre a verga em vão largo."""
    king_lim = _regra(R, "king_duplo_lim_m")
    jack_lim = _regra(R, "jack_duplo_lim_m")
    apoio = _regra(R, "apoio_verga_m")
    diag_min = _regra(R, "diag_sobre_verga_min_m")
    guia_parede = _guia_correspondente(con, perfil_m)

    for o in ops:
        pv_mont, pv_guia = _perfil_verga(con, o["larg"], perfil_m)
        h_v = _perfil(con, pv_mont)["alma_mm"] / 1000
        vy0 = o["head"]
        vy1 = min(o["head"] + h_v, pd - 0.01)
        king_n = 2 if o["larg"] > king_lim else 1
        jack_n = 2 if o["larg"] > jack_lim else 1
        for lado in (-1, 1):
            xk = o["x0"] if lado < 0 else o["x0"] + o["larg"]
            for k in range(king_n):
                mk("K", "king", perfil_m,
                   xk + lado * (k + 1) * alma_m, 0, xk + lado * (k + 1) * alma_m, pd,
                   origem="king; duplo acima de 2m [GATE2 1P4]")
            for j in range(jack_n):
                x = xk - lado * (j * alma_m + alma_m / 2)
                mk("J", "jack", perfil_m, x, 0, x, vy0,
                   origem="jack sob a verga; duplo acima de 2m [CBCA/AISI pendente]")
        vx0 = o["x0"] - apoio
        vx1 = o["x0"] + o["larg"] + apoio
        mk("HTW", "verga_mont", pv_mont, vx0, vy0, vx1, vy0,
           origem="verga escalonada por vão [OBRA DX-11]")
        mk("HTW", "verga_mont", pv_mont, vx0, vy1, vx1, vy1,
           origem="verga escalonada por vão [OBRA DX-11]")
        # caixa: DUAS guias no eixo da verga (assim está no v7 — não é bug de cópia)
        mk("HTW", "verga_guia", pv_guia, vx0, (vy0 + vy1) / 2, vx1, (vy0 + vy1) / 2,
           origem="caixa da verga [OBRA DX-11]")
        mk("HTW", "verga_guia", pv_guia, vx0, (vy0 + vy1) / 2, vx1, (vy0 + vy1) / 2,
           origem="caixa da verga [OBRA DX-11]")
        if o["janela"]:
            mk("SBW", "peitoril", guia_parede,
               o["x0"], o["sill"], o["x0"] + o["larg"], o["sill"],
               origem="peitoril de janela")
        crip_x = []
        for x in xs:
            if not (o["x0"] + 0.02 < x < o["x0"] + o["larg"] - 0.02):
                continue
            if vy1 < pd - 0.02:
                mk("C", "cripple", perfil_m, x, vy1, x, pd,
                   origem="cripple sobre a verga, mantém a modulação")
                crip_x.append(x)
            if o["janela"] and o["sill"] > 0.02:
                mk("C", "cripple", perfil_m, x, 0, x, o["sill"],
                   origem="cripple sob o peitoril, mantém a modulação")
        if o["larg"] >= diag_min and vy1 < pd - 0.05:
            nos = [o["x0"], *crip_x, o["x0"] + o["larg"]]
            for i in range(len(nos) - 1):
                inv = i % 2 == 1
                mk("BRB", "diagonal", perfil_m,
                   nos[i], pd if inv else vy1, nos[i + 1], vy1 if inv else pd,
                   origem="diagonais sobre a verga em vão largo [GATE2 1P4 BRR1-3]")


def _bloqueadores(ops, comp, pd, perfil_m, R, pecas, mk):
    """Bloqueadores HB em linhas horizontais, cortados pelos vãos que a linha cruza."""
    n_lin = max(1, int(_round_js(pd / _regra(R, "passo_hb_m"))) - 1)
    for lin in range(1, n_lin + 1):
        y = _round_js(pd * lin / (n_lin + 1), 4)
        cortes = [[0.0, comp]]
        for o in ops:
            if not (o["sill"] < y < o["head"]):
                continue
            for i in range(len(cortes) - 1, -1, -1):
                a, b = cortes[i]
                va, vb = o["x0"], o["x0"] + o["larg"]
                if va > a and vb < b:
                    cortes[i:i + 1] = [[a, va], [vb, b]]
                elif va <= a and vb >= b:
                    del cortes[i]
                elif a < va < b:
                    cortes[i] = [a, va]
                elif a < vb < b:
                    cortes[i] = [vb, b]
        for a, b in cortes:
            if b - a < 0.15:
                continue
            mk("HB", "bloqueador", perfil_m, a, y, b, y,
               origem="bloqueador ~700mm [OBRA-1P4 pendente]")


def _contraventamento_e_ancoragem(contrav, externa, vaos_contrav, ops, juntas,
                                  comp, pd, perfil_m, alma_m, R, pecas, mk):
    """Contraventamento (derivado de `externa` quando não vem explícito, como o
    wallToP do v7) + acessórios de ancoragem [OBRA-484125]."""
    if contrav is None:
        contrav = "fita" if externa else "nenhum"
    acess: list[Acessorio] = []

    if contrav == "trelica":
        n_b = max(1, vaos_contrav)
        vx = sorted({_round_js(p.x0, 3) for p in pecas
                     if p.tipo in ("montante", "montante_ext", "king", "jack")})
        livres = []
        for i in range(len(vx) - 1):
            a, b = vx[i], vx[i + 1]
            if b - a < 0.15:
                continue
            if any(a >= o["x0"] - 0.03 and b <= o["x0"] + o["larg"] + 0.03 for o in ops):
                continue
            livres.append((a, b))
        for a, b in livres[-n_b:]:
            cols = ([(a, (a + b) / 2), ((a + b) / 2, b)]
                    if (b - a) > _regra(R, "colunas_trelica_se_m") else [(a, b)])
            if len(cols) == 2:
                mk("S", "montante_curto", perfil_m, (a + b) / 2, 0, (a + b) / 2, pd,
                   origem="montante intermediário da treliça")
            for ca, cb in cols:
                n_passos = max(2, int(_round_js(pd / _regra(R, "passo_trelica_m"))))
                flip = False
                for i in range(n_passos):
                    y0 = pd * i / n_passos
                    y1 = pd * (i + 1) / n_passos
                    x_a, x_b = (cb, ca) if flip else (ca, cb)
                    mk("BRB", "diagonal", perfil_m,
                       x_a + (-1 if flip else 1) * alma_m / 2, y0,
                       x_b + (1 if flip else -1) * alma_m / 2, y1,
                       origem="treliça zigzag [GATE2 1P4]")
                    flip = not flip
    elif contrav == "fita":
        diag = math.hypot(pd, min(comp, 3.6))
        acess.append(Acessorio("Fita de contraventamento em X",
                               _round_js(vaos_contrav * 2 * diag, 1), "m"))
    elif contrav == "osb":
        acess.append(Acessorio("OSB estrutural (diafragma)",
                               math.ceil(comp * pd / 2.88), "placa"))

    if juntas:
        pf = len(juntas) * math.ceil(pd / _regra(R, "passo_conex_painel_m"))
        acess.append(Acessorio(
            "Parafuso sext. 4,8x19 — conexão entre painéis (ziguezague 200mm)", pf, "un"))
    n_anc = max(2, math.floor(comp / _regra(R, "ancor_esp_padrao_m")) + 1)
    acess.append(Acessorio("Ancorador chapa #3,00 190x50x50", n_anc, "un"))
    acess.append(Acessorio('Chumbador Parabolt 5/16"x4-1/4"', n_anc, "un"))
    acess.append(Acessorio("Parafuso sextavado 4,8x19 (ancoradores)", n_anc * 8, "un"))
    return acess


@dataclass(frozen=True)
class PlanoCortePerfil:
    perfil: str
    n_pecas: int
    ml: float
    kg: float
    barras: int
    perda_pct: float


@dataclass(frozen=True)
class EstruturaProjeto:
    projeto_id: int
    paredes: list[EstruturaParede]
    plano_corte: list[PlanoCortePerfil]
    kg_liquido: float
    kg_comprado: float
    confianca: str
    alertas: list[str]


def plano_de_corte(con, pecas: list[Peca], barra_m: float) -> list[PlanoCortePerfil]:
    """Porta do nestingCorte do v7: first-fit decrescente por perfil; peça maior
    que a barra vira emendas de até barra_m."""
    por_perfil: dict[str, list[Peca]] = {}
    for p in pecas:
        por_perfil.setdefault(p.perfil, []).append(p)
    plano = []
    for perfil, lista in sorted(por_perfil.items()):
        massa = _perfil(con, perfil)["massa_kg_m"]
        ml = sum(p.comp for p in lista)
        sobras: list[float] = []

        def alocar(c):
            for i, s in enumerate(sobras):
                if s >= c - 1e-9:
                    sobras[i] = _round_js(s - c, 4)
                    return
            sobras.append(_round_js(barra_m - c, 4))

        for p in sorted(lista, key=lambda p: -p.comp):
            if p.comp > barra_m + 1e-6:
                rest = p.comp
                while rest > 1e-6:
                    c = min(rest, barra_m)
                    alocar(c)
                    rest -= c
            else:
                alocar(p.comp)
        sobra_total = sum(sobras)
        plano.append(PlanoCortePerfil(
            perfil, len(lista), _round_js(ml, 2), _round_js(ml * massa, 1),
            len(sobras),
            _round_js(100 * sobra_total / (len(sobras) * barra_m), 1) if sobras else 0.0))
    return plano


def gerar_estrutura(con, projeto_id: int) -> EstruturaProjeto:
    ids = [r[0] for r in con.execute(
        "SELECT p.id FROM parede p JOIN nivel n ON n.id = p.nivel_id"
        " WHERE n.projeto_id = ? ORDER BY p.id", (projeto_id,))]
    if not ids:
        raise DadoIndisponivel(
            f"projeto {projeto_id} sem paredes na planta_normalizada")
    paredes = [gerar_parede(con, i) for i in ids]
    todas = [p for ep in paredes for p in ep.pecas]
    barra = _regra(_regras(con), "barra_m")
    plano = plano_de_corte(con, todas, barra)
    kg_liquido = sum(pl.kg for pl in plano)
    kg_comprado = sum(
        pl.barras * barra * _perfil(con, pl.perfil)["massa_kg_m"] for pl in plano)
    # coeficientes das regras são `estimado` (sem calibração de obra): o resultado
    # nunca é melhor que estimado, por pior que seja a geometria (D4)
    confianca = pior_confianca(*(ep.confianca for ep in paredes), "estimado")
    alertas = [a for ep in paredes for a in ep.alertas]
    return EstruturaProjeto(projeto_id, paredes, plano,
                            _round_js(kg_liquido), _round_js(kg_comprado),
                            confianca, alertas)


def _cargas(con) -> dict:
    chaves = ("carga_sc", "carga_g", "aco_fy", "aco_E", "coef_gm", "flecha_lim",
              "sec_ue250_a", "sec_ue250_wx", "sec_ue250_ix")
    regras = _regras(con)
    faltando = [c for c in chaves if c not in regras]
    if faltando:
        raise DadoIndisponivel(f"regra_lsf sem cargas/seção: {faltando}")
    return {c: regras[c] for c in chaves}


def dimensionar_viga(con, vao_m: float, trib_m: float) -> dict:
    """Verifica viga de laje (perfil Ue250, porta fiel de v7:635-642): ELS
    (flecha <= L/flecha_lim) e ELU (M<=MRd, V<=VRd) em modo simples; se falhar,
    tenta dupla (2 perfis); senão exige viga laminada.

    origem_regra: NBR 6120 (ações — SC=carga_sc sobrecarga, G=carga_g permanente)
    + NBR 14762 (dimensionamento de perfis formados a frio — M/MRd/Wx, δ=L/flecha_lim,
    V/VRd por flambagem de alma h/t do perfil Ue250)."""
    C = _cargas(con)
    sc, g = C["carga_sc"], C["carga_g"]
    fy, E, gM, flecha = C["aco_fy"], C["aco_E"], C["coef_gm"], C["flecha_lim"]
    A, Wx, Ix = C["sec_ue250_a"], C["sec_ue250_wx"], C["sec_ue250_ix"]
    L = vao_m
    trib = trib_m

    pp = A * 7850e-9 * 9.81
    wS = (sc + g) * trib + pp
    wU = 1.4 * g * trib + 1.5 * sc * trib + 1.4 * pp
    M = wU * L * L / 8 * 1e6
    MRd = Wx * fy / gM
    delta = 5 * wS * L ** 4 * 1e12 / (384 * E * Ix)
    dLim = L * 1000 / flecha
    V = wU * L / 2
    VRd = 0.905 * E * 5.34 * (2.0 ** 3) / 250 / gM / 1000
    okS = M <= MRd and delta <= dLim and V <= VRd
    okD = M <= 2 * MRd and delta / 2 <= dLim and V <= 2 * VRd
    modo = "simples" if okS else ("dupla" if okD else "laminada")

    return {"modo": modo, "M": _round_js(M, 1), "MRd": _round_js(MRd, 1),
            "delta": _round_js(delta, 1), "dLim": _round_js(dLim, 0),
            "V": _round_js(V, 1), "VRd": _round_js(VRd, 1)}


def derivar_quantitativos(con, projeto_id: int) -> dict:
    """Escreve o kg comprado do gerador na folha 03.01 da EAP como quantitativo
    PARAMETRICO (D2: re-derivar substitui a linha; a UNIQUE garante).

    Guarda: derivação paramétrica NUNCA sobrescreve linha MANUAL/TAKEOFF (dado
    melhor que 'estimado' de regra). Nesse caso preserva a linha e devolve
    `gravado=False` + `preservado=<origem existente>` — o chamador decide alertar."""
    est = gerar_estrutura(con, projeto_id)
    folha = con.execute(
        "SELECT id FROM eap_item WHERE codigo = '03.01'").fetchone()
    if folha is None:
        raise DadoIndisponivel("EAP sem a folha 03.01 (estrutura LSF, kg)")
    cur = con.execute(
        "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem,"
        " confianca, origem_regra) VALUES (?,?,?,'PARAMETRICO',?,?)"
        " ON CONFLICT (projeto_id, eap_item_id) DO UPDATE SET"
        "   quantidade=excluded.quantidade, origem=excluded.origem,"
        "   confianca=excluded.confianca, origem_regra=excluded.origem_regra"
        " WHERE quantitativo.origem = 'PARAMETRICO'",
        (projeto_id, folha[0], est.kg_comprado, est.confianca,
         "gerador de estrutura F2.1 (porta fiel v7) — kg comprado em barras 6m"))
    resultado = {"kg_comprado": est.kg_comprado, "confianca": est.confianca}
    if cur.rowcount == 0:  # conflito com linha não-PARAMETRICO: nada escrito
        origem = con.execute(
            "SELECT origem FROM quantitativo WHERE projeto_id = ? AND eap_item_id = ?",
            (projeto_id, folha[0])).fetchone()[0]
        con.commit()
        return {**resultado, "gravado": False, "preservado": origem}
    con.commit()
    return {**resultado, "gravado": True}
