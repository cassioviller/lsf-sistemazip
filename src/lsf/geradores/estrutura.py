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
    return


def _contraventamento_e_ancoragem(contrav, externa, vaos_contrav, ops, juntas,
                                  comp, pd, perfil_m, alma_m, R, pecas, mk):
    return []
