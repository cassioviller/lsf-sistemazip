"""Gerador de estrutura de paredes LSF — porta FIEL do gerarPecas do v7.

Cada bloco reproduz o algoritmo do calculador v7 (assets/, READ-ONLY), lendo
perfis e regras do banco em vez de constantes JS. Epsilons e ordem de operações
são contrato: o aceite compara peça a peça com o v7 headless.
origem_regra anota a proveniência de cada decisão, como o v7 fazia.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, replace

from lsf.geradores.geometria import bbox, cortar_span, encadear_contorno, poly_area, scan
from lsf.motores.orcamento import pior_confianca


class DadoIndisponivel(Exception):
    """Perfil/regra/dado ausente é ERRO — nunca peça pulada, nunca kg parcial (D4.1)."""


# Prefixo dos alertas que significam "a estrutura gerada NÃO passa na verificação".
# O kg segue sendo emitido (o orçamento precisa de um número), mas a pendência tem
# que viajar junto até a EAP — alerta que morre no retorno é disclaimer morto, e o
# CLAUDE.md manda gate bloquear, não avisar. Marcado em vez de deduzido por texto:
# `pendencias_estruturais` filtra por este prefixo, não por 'laminada' no meio da frase.
MARCA_PENDENCIA = "[PENDÊNCIA ESTRUTURAL]"


def _round_js(x: float, nd: int = 0) -> float:
    """Math.round/toFixed do JS arredondam 0.5 para cima; round() do Python é
    banker's. A porta fiel exige o comportamento JS."""
    m = 10 ** nd
    return math.floor(x * m + 0.5) / m


@dataclass(frozen=True)
class Peca:
    """Peça de perfil. `y` é a vertical (pé-direito/cota), `x`/`z` o plano da planta
    — convenção do v7. Parede vive num plano (z0=z1=0) e seu `comp` é o hypot 2D;
    laje/cobertura usam os três eixos, daí `comp` ser hypot 3D."""

    tag: str
    tipo: str          # guia|montante|montante_ext|montante_curto|king|jack|
                       # verga_mont|verga_guia|peitoril|cripple|diagonal|bloqueador|
                       # borda_laje|viga_laje|bloqueador_laje|enrijecedor_laje|
                       # reforco_abertura
    perfil: str
    x0: float
    y0: float
    x1: float
    y1: float
    comp: float
    origem_regra: str = ""
    sistema: str = "parede"
    grupo: str = ""
    z0: float = 0.0
    z1: float = 0.0
    confianca: str = "estimado"


@dataclass(frozen=True)
class Acessorio:
    item: str
    qtd: float
    un: str
    sistema: str = "parede"
    grupo: str = ""
    origem_regra: str = ""
    confianca: str = "parametrico"


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
        "SELECT alma_mm, massa_kg_m, aba_mm, enrijecedor_mm, espessura_mm"
        "  FROM perfil_lsf WHERE codigo = ?", (codigo,)
    ).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"perfil '{codigo}' não cadastrado em perfil_lsf")
    return dict(zip(("alma_mm", "massa_kg_m", "aba_mm", "enrijecedor_mm",
                     "espessura_mm"), linha))


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
        "       a.x, a.y, b.x, b.y, n.pe_direito_m, n.indice"
        "  FROM parede p"
        "  JOIN no_planta a ON a.id = p.no_a"
        "  JOIN no_planta b ON b.id = p.no_b"
        "  JOIN nivel n ON n.id = p.nivel_id"
        " WHERE p.id = ?", (parede_id,)
    ).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"parede {parede_id} não existe")
    externa, perfil_m, conf, ax, ay, bx, by, pd, nivel_indice = tuple(linha)
    # REGRA DP-04: só o térreo ancora no radier; painel de pavimento superior
    # aparafusa no painel de baixo [OBRA p.8-9]. O v7 filtra por nome do acessório
    # em montarProjeto (/Parabolt|Ancorador/i); aqui a parede simplesmente não gera
    # o que não existe — sem isso, a 109 orçaria 3,06x a ancoragem real.
    no_radier = nivel_indice == 0
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
        perfil_m, alma_m, R, pecas, mk, no_radier)

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
                                  comp, pd, perfil_m, alma_m, R, pecas, mk,
                                  no_radier=True):
    """Contraventamento (derivado de `externa` quando não vem explícito, como o
    wallToP do v7) + acessórios de ancoragem [OBRA-484125].

    `no_radier=False` (pavimento superior) não gera ancoragem: REGRA DP-04."""
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
    if no_radier:   # DP-04: painel-sobre-painel não chumba no concreto [OBRA p.8-9]
        n_anc = max(2, math.floor(comp / _regra(R, "ancor_esp_padrao_m")) + 1)
        acess.append(Acessorio("Ancorador chapa #3,00 190x50x50", n_anc, "un"))
        acess.append(Acessorio('Chumbador Parabolt 5/16"x4-1/4"', n_anc, "un"))
        acess.append(Acessorio("Parafuso sextavado 4,8x19 (ancoradores)",
                               n_anc * 8, "un"))
    return acess


# ---------- laje (porta fiel de gerarPecasLaje, v7:801-889) ----------

def contorno_pavimento(con, projeto_id: int, nivel_indice: int) -> list[tuple[float, float]]:
    """Footprint do pavimento = contorno das paredes EXTERNAS encadeado.

    Porta de chainPolygon(W_T)/buildBuilding do v7, que filtra `t==='ext'`. O
    footprint NÃO é input de projeto: deriva da planta normalizada (D3). A ordem
    das paredes importa (o encadeamento é guloso a partir da primeira) — por isso
    ORDER BY p.id, que reproduz a ordem do array W_T do v7.
    """
    segs = con.execute(
        "SELECT a.x, a.y, b.x, b.y"
        "  FROM parede p"
        "  JOIN no_planta a ON a.id = p.no_a"
        "  JOIN no_planta b ON b.id = p.no_b"
        "  JOIN nivel n ON n.id = p.nivel_id"
        " WHERE n.projeto_id = ? AND n.indice = ? AND p.externa = 1"
        " ORDER BY p.id", (projeto_id, nivel_indice)).fetchall()
    return encadear_contorno([((ax, az), (bx, bz)) for ax, az, bx, bz in segs])


def _perfis_laje(con, perfil_viga_input: str, vao_ef: float) -> tuple[str, str, str]:
    """Escalonamento do par viga/bloqueador por vão efetivo (laje_escalonamento).
    O limiar da primeira faixa é o mesmo da regra `laje_vao_ue200` (v7: 4,0 m)."""
    faixas = con.execute(
        "SELECT faixa_ate_m, perfil_viga, perfil_bloqueador, origem"
        "  FROM laje_escalonamento ORDER BY faixa_ate_m").fetchall()
    if not faixas:
        raise DadoIndisponivel("laje_escalonamento vazio")
    if perfil_viga_input != "auto":       # perfil imposto pelo projeto (v7: L.perfilViga)
        for _, pv, pb, origem in faixas:
            if pv == perfil_viga_input:
                return pv, pb, origem
        raise DadoIndisponivel(
            f"perfil de viga '{perfil_viga_input}' sem par de bloqueador em"
            " laje_escalonamento")
    for ate, pv, pb, origem in faixas:
        if vao_ef <= ate:
            return pv, pb, origem
    raise DadoIndisponivel(
        f"vão efetivo de {vao_ef:.2f} m acima da última faixa de laje_escalonamento")


# citação das regras de montagem da laje, como o v7 anotava (REGRAS_SIS.laje.origem)
_O_LAJE = ("REGRA LAJE-003/006/007/009/010 [mont. p.21-39: DL-01 5 paraf. alma;"
           " C=176(L200)/226(L250)]")


def gerar_laje(con, laje_id: int) -> tuple[list[Peca], list[Acessorio], list[str]]:
    """Laje de piso sobre um pavimento: bordas no contorno real, vigas na direção x
    recortadas pelo polígono e pelos vãos de escada, bloqueadores por baia em
    modulação alternada, enrijecedores, reforço de abertura e chapa de piso.

    Porta fiel de v7:801-889 — a ordem das operações e os epsilons são contrato.
    """
    linha = con.execute(
        "SELECT projeto_id, id_laje, grupo, pav_base, nivel, esp_m, perfil_viga,"
        "       perfil_enrijecedor, bloqueador_max_m, chapa_piso_tipo,"
        "       chapa_piso_larg, chapa_piso_alt, confianca"
        "  FROM laje WHERE id = ?", (laje_id,)).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"laje {laje_id} não existe")
    (projeto_id, id_laje, grupo, pav_base, y, esp, perfil_viga_in, perfil_enrij,
     bmax, chapa_tipo, chapa_larg, chapa_alt, conf_laje) = tuple(linha)

    # coeficientes de regra são `estimado` (sem calibração de obra): a peça nunca
    # sai melhor que isso, por melhor que seja a geometria de entrada (D4)
    conf = pior_confianca(conf_laje, "estimado")
    pecas: list[Peca] = []
    acess: list[Acessorio] = []
    alertas: list[str] = []

    fp = contorno_pavimento(con, projeto_id, pav_base)
    if not fp:
        alertas.append(
            f"{id_laje}: footprint vazio — verificar as paredes externas do"
            f" pavimento {pav_base}.")
        return pecas, acess, alertas

    R = _regras(con)
    aberturas = [dict(zip(("tipo", "x", "z", "w", "d"), r)) for r in con.execute(
        "SELECT tipo, x, z, w, d FROM laje_abertura WHERE laje_id = ? ORDER BY id",
        (laje_id,)).fetchall()]
    extensoes = [dict(zip(("x", "z", "w", "d"), r)) for r in con.execute(
        "SELECT x, z, w, d FROM laje_extensao WHERE laje_id = ? ORDER BY id",
        (laje_id,)).fetchall()]

    # Coerência da GEOMETRIA, antes de gerar peça: aberturas que somam mais que o
    # próprio pavimento não descrevem uma laje. A guarda mora aqui, e não na chapa
    # de piso, porque não depende de haver chapa — uma laje sem `chapa_piso_tipo`
    # geraria vigas e bordas sobre um polígono já consumido pelos vãos (D4.1).
    area_util = (poly_area(fp)
                 - sum(ab["w"] * ab["d"] for ab in aberturas)
                 + sum(ex["w"] * ex["d"] for ex in extensoes))
    if area_util <= 0:
        raise DadoIndisponivel(
            f"{id_laje}: área de piso {area_util:.2f} m² <= 0 — as aberturas somam"
            " mais que o footprint; revisar laje_abertura")

    seq: dict[str, int] = {}

    def mk(tipo, perfil, x0, y0, z0, x1, y1, z1, origem, confianca):
        pfx = "".join(c for c in tipo if c.isalpha())[:3].upper()   # v7 mkP
        chave = grupo + pfx
        seq[chave] = seq.get(chave, 0) + 1
        comp = math.hypot(x1 - x0, y1 - y0, z1 - z0)
        p = Peca(f"{grupo}-{pfx}{seq[chave]}", tipo, perfil, x0, y0, x1, y1,
                 _round_js(comp, 4), origem, "laje", grupo, z0, z1, confianca)
        pecas.append(p)
        return p

    def mk_ac(item, qtd, un, origem, confianca):
        acess.append(Acessorio(item, _round_js(qtd, 1), un, "laje", grupo, origem,
                               confianca))

    bb = bbox(fp)
    # escalonamento: o maior vão livre (varredura em z, passo 0,5) decide o perfil
    max_span = 0.0
    z = bb["z0"] + 0.2
    while z < bb["z1"]:
        for a, b in scan(fp, z, "z"):
            max_span = max(max_span, b - a)
        z += 0.5
    # O /2 NÃO é chute nem "simplificação": é o apoio intermediário no meio do vão.
    # Na 109 esse apoio é a viga laminada 1VG da obra (v7: "laminada no meio do vão
    # [estudo NBR: reduz vãoEf/2; OBRA 1VG p.9]"), que parte a largura do prédio
    # (~15,8 m) nos ~7,9 m que as vigas de laje LSF realmente vencem. Por isso o
    # veredito 'laminada' bate com o que foi construído: 1VG + pilares 1AL.
    # Generalizar isso para o apoio REAL (paredes portantes internas da
    # planta_normalizada, em vez de metade do bbox) é o estágio 3 da Fase 2
    # (takedown de cargas por parede real) — não mexer aqui sem aquele plano.
    vao_ef = max_span / 2
    perf_v, perf_b, origem_par = _perfis_laje(con, perfil_viga_in, vao_ef)

    # a verificação usa o perfil REALMENTE escolhido pelo escalonamento (o v7 lia
    # sempre a seção do Ue250, mesmo nas lajes de Ue200)
    chk = dimensionar_viga(con, vao_ef, esp, perf_v)
    if chk["modo"] == "dupla":
        alertas.append(
            f"{id_laje}: vão de cálculo {_round_js(vao_ef, 1)}m reprova viga simples"
            f" em {perf_v} (M={chk['M']} vs {chk['MRd']} kNm;"
            f" δ={chk['delta']} vs {chk['dLim']}mm)"
            " → VIGAS DUPLAS geradas. Memória: SC 4,0 kN/m² loja [NBR 6120], ZAR230, L/350.")
    if chk["modo"] == "laminada":
        alertas.append(
            f"{MARCA_PENDENCIA} {id_laje}: vão {_round_js(vao_ef, 1)}m reprova até"
            f" viga dupla em {perf_v} (M={chk['M']} > 2×{chk['MRd']} kNm e/ou"
            f" δ={chk['delta']} > {chk['dLim']}mm) → exige viga laminada 1VG +"
            " pilares [OBRA p.3-9]. O kg gerado é PROVISÃO de orçamento, não"
            " dimensionamento: reduzir vão com apoio intermediário no executivo.")

    # origem da 2ª viga do par (só existe fora do modo 'simples'). Em 'laminada' nem
    # a dupla passa: a peça é provisão de orçamento e NÃO pode citar NBR 14762 como
    # se estivesse verificada — quem gateia é a pendência que sobe até a EAP.
    if chk["modo"] == "dupla":
        _origem_2a_viga = (
            f"viga DUPLA (box): ELU M={chk['M']}>{chk['MRd']} kNm e/ou"
            f" δ={chk['delta']}>{chk['dLim']}mm no vão {_round_js(vao_ef, 1)}m"
            f" em {perf_v} [NBR 14762]")
    else:
        _origem_2a_viga = (
            f"PROVISÃO de orçamento, NÃO verificada: no vão {_round_js(vao_ef, 1)}m"
            f" nem a dupla em {perf_v} passa (M={chk['M']}>2×{chk['MRd']} kNm e/ou"
            f" δ={chk['delta']}>{chk['dLim']}mm) — exige viga laminada 1VG +"
            " pilares. Ver a pendência estrutural da laje.")

    # bordas = perímetro real do polígono
    for i in range(len(fp)):
        a, b = fp[i], fp[(i + 1) % len(fp)]
        mk("borda_laje", perf_b, a[0], y, a[1], b[0], y, b[1],
           "rim no contorno real", conf)

    # vigas ao longo de x, recortadas pelo polígono e pelos vãos de escada
    n_enr = n_bloc = n_vigas = 0
    z = bb["z0"] + esp
    while z < bb["z1"] - 0.05:
        for xa, xb in scan(fp, z, "z"):
            vaos = [(ab["x"], ab["x"] + ab["w"]) for ab in aberturas
                    if ab["z"] <= z <= ab["z"] + ab["d"]]
            for s, e in cortar_span(xa, xb, vaos):
                n_vigas += 1
                mk("viga_laje", perf_v, s, y, z, e, y, z,
                   f"{_O_LAJE} · {origem_par} · vão ef {_round_js(vao_ef, 1)}m→{perf_v}",
                   conf)
                if chk["modo"] != "simples":
                    mk("viga_laje", perf_v, s, y, z + 0.05, e, y, z + 0.05,
                       _origem_2a_viga, "parametrico")
        z += esp

    # bloqueadores em linhas x, passo <= bloqueador_max_m, cortados pelo polígono e vãos
    n_lin = max(1, math.ceil((bb["x1"] - bb["x0"]) / bmax) - 1)
    c_enrij = _regra(R, "laje_enrij_c_f250" if perf_v.startswith("Ue250")
                     else "laje_enrij_c_f200")
    origem_enrij = ("REGRA LAJE-010: C=226mm (laje 250) [p.39]"
                    if perf_v.startswith("Ue250")
                    else "REGRA LAJE-009: C=176mm (laje 200) [p.27-38]")
    for lin in range(1, n_lin + 1):
        x = bb["x0"] + (bb["x1"] - bb["x0"]) * lin / (n_lin + 1)
        for za, zb in scan(fp, x, "x"):
            vaos = [(ab["z"], ab["z"] + ab["d"]) for ab in aberturas
                    if ab["x"] <= x <= ab["x"] + ab["w"]]
            for s, e in cortar_span(za, zb, vaos):
                # A4 [p.27 + LAJE-005]: bloqueador é peça POR VÃO entre vigas, em
                # modulação ALTERNADA (baia sim, baia não, deslocada ±12cm)
                n_bay = max(1, int(_round_js((e - s) / esp)))
                for b in range(n_bay):
                    zb0 = s + b * esp
                    zb1 = min(e, s + (b + 1) * esp)
                    x_alt = x + (0.12 if b % 2 else -0.12)
                    mk("bloqueador_laje", perf_b, x_alt, y, zb0, x_alt, y, zb1,
                       "A4: bloq. por vão alternado [p.27, LAJE-005] · 2 paraf/ligação"
                       " [DP-01A]", conf)
                    n_bloc += 1
                for c in range(n_bay):   # um enrijecedor por baia, no eixo da linha
                    n_enr += 1
                    mk("enrijecedor_laje", perfil_enrij, x, y, s + c * esp,
                       x, y - c_enrij, s + c * esp, origem_enrij, "parametrico")

    mk_ac("Parafuso 4,8×19 — bloqueador na mesa (4/bloq)",
          n_bloc * _regra(R, "laje_fix_mesa_paraf"), "un",
          "DP-01A: 2 paraf. flangeados por ligação × 2 extremidades", "parametrico")
    mk_ac("Parafuso 4,8×19 — enrijecedor na alma (5/contato)",
          n_enr * _regra(R, "laje_fix_alma_paraf"), "un",
          "REGRA LAJE-007: 5 parafusos [DL-01 p.21-39]", "parametrico")

    # extensões retangulares (ex.: faixa de varanda) — bordas no perímetro exposto + vigas
    for ex in extensoes:
        mk("borda_laje", perf_b, ex["x"], y, ex["z"], ex["x"], y, ex["z"] + ex["d"],
           "borda de varanda", conf)
        mk("borda_laje", perf_b, ex["x"], y, ex["z"], ex["x"] + ex["w"], y, ex["z"],
           "borda de varanda", conf)
        mk("borda_laje", perf_b, ex["x"], y, ex["z"] + ex["d"], ex["x"] + ex["w"], y,
           ex["z"] + ex["d"], "borda de varanda", conf)
        z = ex["z"] + esp
        while z < ex["z"] + ex["d"] - 0.05:
            mk("viga_laje", perf_v, ex["x"], y, z, ex["x"] + ex["w"], y, z,
               "viga da faixa de varanda", conf)
            z += esp

    # reforço nas aberturas (vão de escada)
    for ab in aberturas:
        x, zz, w, d = ab["x"], ab["z"], ab["w"], ab["d"]
        for x0, z0, x1, z1 in ((x, zz, x + w, zz), (x, zz + d, x + w, zz + d),
                               (x, zz, x, zz + d), (x + w, zz, x + w, zz + d)):
            mk("reforco_abertura", perf_b, x0, y, z0, x1, y, z1,
               "reforço de vão de escada", conf)

    # chapa de piso pela área útil já validada acima (polígono - vãos + extensões)
    if chapa_tipo:
        n_ch = math.ceil(area_util * 1.10 / ((chapa_larg or 1.2) * (chapa_alt or 2.4)))
        mk_ac(f"{chapa_tipo} (piso {id_laje})", n_ch, "chapa",
              "área do polígono + 10%", conf)

    return pecas, acess, alertas


# ---------- escada (porta fiel de gerarPecasEscada, v7:893-946) ----------

_O_ESCADA = ("484125 1ES1: longarina Ue140+U142, degrau Ue90#0.95,"
             " reforço 140 @150mm")


def gerar_escada(con, escada_id: int, com_info: bool = False):
    """Escada em U: 2 lances lado a lado + patamar no topo do poço.

    Porta fiel de v7:893-946. Os lances correm na MAIOR dimensão do poço; a
    largura de cada lance é metade da menor. `com_info=True` acrescenta o dict de
    geometria (n_degraus/espelho/piso) que o v7 expunha em `E._info`.
    """
    linha = con.execute(
        "SELECT id_escada, grupo, vao_x, vao_z, vao_w, vao_d, altura, nivel_inicial,"
        "       longarina_perfil_a, longarina_perfil_b, degrau_perfil, confianca"
        "  FROM escada WHERE id = ?", (escada_id,)).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"escada {escada_id} não existe")
    (id_escada, grupo, vx, vz, vw, vd, altura, y0, long_a, long_b, perf_degrau,
     conf_escada) = tuple(linha)

    R = _regras(con)
    espelho_max = _regra(R, "escada_espelho_max")
    piso_min = _regra(R, "escada_piso_min")
    piso_abs_min = _regra(R, "escada_piso_abs_min")
    fix_lateral = _regra(R, "escada_fix_lateral_mm")

    conf = pior_confianca(conf_escada, "estimado")
    pecas: list[Peca] = []
    acess: list[Acessorio] = []
    alertas: list[str] = []
    seq: dict[str, int] = {}

    n_deg = max(4, math.ceil(altura / espelho_max))
    espelho = altura / n_deg
    along_z = vd >= vw                  # lances correm na maior dimensão do poço
    run_dim = vd if along_z else vw
    larg_dim = vw if along_z else vd
    larg_lance = larg_dim / 2           # U: 2 lances lado a lado
    patamar_prof = larg_dim             # patamar quadrado no topo do poço
    n_d1 = math.ceil(n_deg / 2)
    n_d2 = n_deg - n_d1
    piso = min(piso_min, max(piso_abs_min, run_dim / n_d1))   # piso limitado pelo poço
    run1 = n_d1 * piso
    run2 = n_d2 * piso

    if piso < piso_min - 1e-3:
        alertas.append(
            f"{id_escada}: piso {piso * 1000:.0f}mm < {piso_min * 1000:.0f}mm p/ caber"
            f" no vão de {run_dim:.2f}m. Ampliar o vão de escada na laje ou aceitar"
            " arranque fora do poço no térreo.")
    if run1 > run_dim + 0.31:
        alertas.append(
            f"{id_escada}: lance de {run1:.2f}m excede o poço de {run_dim:.2f}m —"
            " arranque sai do vão (comum no piso de partida). Confirmar arranque"
            " no executivo.")

    h_meio = espelho * n_d1

    def P(u, w, y):
        """u = direção do lance, w = transversal (v7: helper P)."""
        return (vx + w, y, vz + u) if along_z else (vx + u, y, vz + w)

    def seg(tipo, perfil, a, b, origem=_O_ESCADA, confianca=None):
        ax, ay, az = P(*a)
        bx, by, bz = P(*b)
        pfx = "".join(c for c in tipo if c.isalpha())[:3].upper()
        chave = grupo + pfx
        seq[chave] = seq.get(chave, 0) + 1
        comp = math.hypot(bx - ax, by - ay, bz - az)
        pecas.append(Peca(f"{grupo}-{pfx}{seq[chave]}", tipo, perfil, ax, ay, bx, by,
                          _round_js(comp, 4), origem, "escada", grupo, az, bz,
                          confianca or conf))

    def mk_ac(item, qtd, un, origem, confianca):
        acess.append(Acessorio(item, _round_js(qtd, 1), un, "escada", grupo, origem,
                               confianca))

    # LANCE 1 (sobe, faixa w:[0, larg_lance])
    for w_off in (0.03, larg_lance - 0.03):
        for pf in (long_a, long_b):
            seg("longarina", pf, (0, w_off, y0), (run1, w_off, y0 + h_meio),
                "longarina composta Ue140+U142 [1ES1]")
    for i in range(1, n_d1 + 1):
        seg("travessa_degrau", perf_degrau,
            (i * piso, 0, y0 + i * espelho), (i * piso, larg_lance, y0 + i * espelho))

    # PATAMAR (no fim do lance 1, largura total do poço)
    u_p = min(run1, run_dim - 0.4)
    u_p2 = min(u_p + 0.9, run_dim)
    seg("patamar", long_a, (u_p, 0, y0 + h_meio), (u_p, larg_dim, y0 + h_meio),
        "frame do patamar")
    seg("patamar", long_a, (u_p2, 0, y0 + h_meio), (u_p2, larg_dim, y0 + h_meio),
        "frame do patamar")
    seg("patamar", long_b, (u_p, 0, y0 + h_meio), (u_p2, 0, y0 + h_meio),
        "guia patamar")
    seg("patamar", long_b, (u_p, larg_dim, y0 + h_meio), (u_p2, larg_dim, y0 + h_meio),
        "guia patamar")

    # LANCE 2 (volta, faixa w:[larg_lance, larg_dim]) — desce em u
    for w_off in (larg_lance + 0.03, larg_dim - 0.03):
        for pf in (long_a, long_b):
            seg("longarina", pf, (u_p, w_off, y0 + h_meio),
                (max(u_p - run2, 0), w_off, y0 + altura), "longarina composta [1ES1]")
    for i in range(1, n_d2 + 1):
        seg("travessa_degrau", perf_degrau,
            (u_p - i * piso, larg_lance, y0 + h_meio + i * espelho),
            (u_p - i * piso, larg_dim, y0 + h_meio + i * espelho))

    # reforço lateral @150mm + chapa L (2 lados externos)
    # v7 fixa 'Ue140#1.25' aqui; é o mesmo perfil da longarina_a — lido do banco
    # para que o par continue coerente se o projeto trocar a longarina.
    d_inc1 = math.hypot(run1, h_meio)
    d_inc2 = math.hypot(run2, altura - h_meio)
    seg("reforco_lateral", long_a, (0, 0, y0), (run1, 0, y0 + h_meio),
        "reforço lateral 140mm [DE-02]")
    seg("reforco_lateral", long_a, (u_p, larg_dim, y0 + h_meio),
        (max(u_p - run2, 0), larg_dim, y0 + altura), "reforço lateral 140mm [DE-02]")

    mk_ac("Chapa L #0,95 89×89×3000 (reforço lateral)", 2, "un", _O_ESCADA, conf)
    mk_ac("Parafuso 4,8×19 — reforço lateral @150mm",
          math.ceil((d_inc1 + d_inc2) / (fix_lateral / 1000)) * 2, "un",
          "@150mm [DE-02]", "parametrico")
    mk_ac("Parafuso 4,8×19 — degraus (4/degrau)", n_deg * 4, "un", _O_ESCADA,
          "parametrico")
    mk_ac("Chapa Gousset 150×150 #1,25 (escada)", 2, "un", "1ES1: 2/painel", conf)
    area_piso = n_deg * piso * larg_lance + patamar_prof * larg_dim * 0.9
    mk_ac("Chapa de piso degraus/patamar", math.ceil(area_piso * 1.10 / 2.88),
          "chapa", "área + 10%", "estimado")

    if com_info:
        info = {"n_degraus": n_deg, "espelho": _round_js(espelho, 3),
                "piso": _round_js(piso, 3), "lances": 2}
        return pecas, acess, alertas, info
    return pecas, acess, alertas


# ---------- cobertura (porta fiel de gerarPecasCobertura, v7:949-1041) ----------

_O_COBERTURA = ("484125 1TS41/42: gusset por nó, box @200mm · 1CB p.56-77:"
                " painéis 140#0.80 (perímetro+travessas+diagonais [COB-003/005])")


def gerar_cobertura(con, cobertura_id: int) -> tuple[list[Peca], list[Acessorio], list[str]]:
    """Telhado de duas águas ao longo de x, sobre o footprint do último pavimento.

    Porta fiel de v7:949-1041. O telhado cobre só a área COBERTA: a faixa de
    varanda descoberta recua o beiral a oeste e o pátio abre vão na água. As
    tesouras saem no grupo `grupo_tesouras` (1TS) e os painéis no `grupo` (1CB).
    """
    linha = con.execute(
        "SELECT projeto_id, id_cobertura, grupo, grupo_tesouras, nivel_base, beiral_m,"
        "       inclinacao, banzo_perfil, guia_banzo_perfil, alma_perfil, telha_tipo,"
        "       telha_perda_pct, painel_cb_perfil, painel_cb_perfil_per, confianca"
        "  FROM cobertura WHERE id = ?", (cobertura_id,)).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"cobertura {cobertura_id} não existe")
    (projeto_id, id_cob, grupo, grupo_ts, yB, beiral, incl, p_banzo, p_guia, p_alma,
     telha_tipo, telha_perda, p_cb, p_cb_per, conf_cob) = tuple(linha)

    R = _regras(con)
    esp_tesoura = _regra(R, "cobertura_esp_tesoura")
    passo_mont = _regra(R, "cobertura_passo_mont")
    gusset_paraf = _regra(R, "cobertura_gusset_paraf")
    box_paraf_mm = _regra(R, "cobertura_box_paraf_mm")
    cb_passo = _regra(R, "cobertura_cb_passo")

    conf = pior_confianca(conf_cob, "estimado")
    pecas: list[Peca] = []
    acess: list[Acessorio] = []
    alertas: list[str] = []
    seq: dict[str, int] = {}

    def mk(grupo_p, tipo, perfil, x0, y0, z0, x1, y1, z1, origem, confianca=None):
        pfx = "".join(c for c in tipo if c.isalpha())[:3].upper()
        chave = grupo_p + pfx
        seq[chave] = seq.get(chave, 0) + 1
        comp = math.hypot(x1 - x0, y1 - y0, z1 - z0)
        pecas.append(Peca(f"{grupo_p}-{pfx}{seq[chave]}", tipo, perfil, x0, y0, x1, y1,
                          _round_js(comp, 4), origem, "cobertura", grupo_p, z0, z1,
                          confianca or conf))

    def mk_ac(grupo_a, item, qtd, un, origem, confianca):
        acess.append(Acessorio(item, _round_js(qtd, 1), un, "cobertura", grupo_a,
                               origem, confianca))

    # o telhado assenta no último pavimento (v7: BUILDING.footprint[2])
    ultimo = con.execute(
        "SELECT MAX(indice) FROM nivel WHERE projeto_id = ?", (projeto_id,)).fetchone()[0]
    if ultimo is None:
        raise DadoIndisponivel(f"projeto {projeto_id} sem níveis")
    fp = contorno_pavimento(con, projeto_id, ultimo)
    if not fp:
        alertas.append(f"{id_cob}: footprint vazio — verificar as paredes externas.")
        return pecas, acess, alertas
    bb0 = bbox(fp)

    descobertas = [dict(zip(("nome", "x", "z", "w", "d", "tipo"), r)) for r in con.execute(
        "SELECT nome, x, z, w, d, tipo FROM area_descoberta WHERE projeto_id = ?"
        " ORDER BY id", (projeto_id,)).fetchall()]
    faixa = next((d for d in descobertas if d["tipo"] == "faixa"), None)
    patio = next((d for d in descobertas if d["tipo"] == "patio"), None)
    # telhado cobre só a área COBERTA: a faixa de varanda recua o telhado a oeste
    bb = dict(bb0)
    if faixa:
        bb["x0"] = max(bb0["x0"], faixa["x"] + faixa["w"])
        alertas.append(
            f"Telhado recuado {faixa['x'] + faixa['w']:.2f}m a oeste: varanda do 3º pav"
            " fica descoberta (laje 2LJ é o teto da varanda do 2º). Prever"
            " impermeabilização e guarda-corpo na laje exposta.")
    if patio:
        alertas.append(
            f"Área descoberta {patio['w'] * patio['d']:.1f}m² dentro do telhado (pátio"
            " do 3º pav): abertura na cobertura. Reforço de borda das tesouras no"
            " executivo + rufos no perímetro do vão.")

    n_t = max(2, int(_round_js((bb["x1"] - bb["x0"]) / esp_tesoura)) + 1)
    n_gusset = 0
    area_telha = 0.0
    zc = (bb["z0"] + bb["z1"]) / 2      # cumeeira no meio do bbox (duas águas em x)
    prev_w = None

    for i in range(n_t):
        xT = bb["x0"] + (bb["x1"] - bb["x0"]) * i / (n_t - 1)
        # largura real do prédio nesta posição
        iv = scan(fp, min(max(xT, bb["x0"] + 0.02), bb["x1"] - 0.02), "x")
        if iv:
            za, zb = iv[0][0] - beiral, iv[-1][1] + beiral
        else:
            za, zb = bb["z0"] - beiral, bb["z1"] + beiral
        meia_e, meia_d = zc - za, zb - zc
        h_cume = max(meia_e, meia_d) * incl

        mk(grupo_ts, "banzo_inferior", p_banzo, xT, yB, za, xT, yB, zb, _O_COBERTURA)
        mk(grupo_ts, "guia_banzo", p_guia, xT, yB, za, xT, yB, zb, "box banzo [DX-09]")
        mk(grupo_ts, "banzo_superior", p_banzo, xT, yB, za, xT, yB + h_cume, zc,
           _O_COBERTURA)
        mk(grupo_ts, "banzo_superior", p_banzo, xT, yB + h_cume, zc, xT, yB, zb,
           _O_COBERTURA)

        # montantes @passo + diagonais Pratt, altura seguindo o telhado
        zs_m = []
        z = za + passo_mont
        while z < zb - passo_mont / 2:
            hz = ((z - za) / (zc - za) * h_cume if z <= zc
                  else (zb - z) / (zb - zc) * h_cume)
            if hz >= 0.12:      # v7: montante mais baixo que 12cm não se justifica
                mk(grupo_ts, "montante_tesoura", p_alma, xT, yB, z, xT, yB + hz, z,
                   "montante @0,60 [1TS]")
                zs_m.append((z, hz))
            z += passo_mont
        for m in range(len(zs_m) - 1):
            (z1, h1), (z2, h2) = zs_m[m], zs_m[m + 1]
            sobe = m % 2 == 0
            mk(grupo_ts, "diagonal_tesoura", p_alma,
               xT, yB + (0 if sobe else h1), z1, xT, yB + (h2 if sobe else 0), z2,
               "diagonal Pratt [1TS]")

        # nós com gusset: 2 apoios + cume + 2 por montante (base/topo)
        n_gusset += 3 + 2 * len(zs_m)
        # área de telha por trapézio entre tesouras (largura real × fator inclinação)
        w_here = zb - za
        if prev_w is not None:
            dx = (bb["x1"] - bb["x0"]) / (n_t - 1)
            area_telha += dx * (w_here + prev_w) / 2 * math.hypot(1, incl)
        prev_w = w_here

    # A8 [p.57, COB-005]: diagonais de canto a 45° — 4 por água
    for lado in (-1, 1):
        z_edge = bb["z0"] - beiral if lado < 0 else bb["z1"] + beiral
        for x_edge in (bb["x0"], bb["x1"] - 1.2):
            y_diag = yB + ((bb["z1"] - bb["z0"]) / 2 * incl) * 0.85
            mk(grupo, "diagonal_canto", p_alma,
               x_edge, y_diag, zc + lado * 0.6, x_edge + 1.2, y_diag, zc + lado * 1.8,
               "A8: diagonal de canto (extremo da cumeeira) [p.57, COB-005]")
            mk(grupo, "diagonal_canto", p_alma,
               x_edge, yB, z_edge, x_edge + 1.2, yB, z_edge - lado * 1.2,
               "A8: diagonal de canto do painel 1CB [p.57, COB-005]")

    # painéis 1CB no plano inclinado (carimbo 1CB-140#0.80 + COB-003/005)
    for lado in (-1, 1):
        z_base = bb["z0"] - beiral if lado < 0 else bb["z1"] + beiral
        h_c = ((bb["z1"] - bb["z0"]) / 2) * incl
        # perímetro da água: beiral + cumeeira
        mk(grupo, "per_1CB", p_cb_per, bb["x0"] - beiral, yB, z_base,
           bb["x1"] + beiral, yB, z_base, "perímetro painel 1CB")
        mk(grupo, "per_1CB", p_cb_per, bb["x0"] - beiral, yB + h_c, zc,
           bb["x1"] + beiral, yB + h_c, zc, "perímetro painel 1CB (cumeeira)")
        # travessas ao longo da inclinação @passo
        x = bb["x0"] - beiral
        while x <= bb["x1"] + beiral + 0.01:
            mk(grupo, "travessa_1CB", p_cb, x, yB, z_base, x, yB + h_c, zc,
               f"travessa painel 1CB @{cb_passo}m [COB-004]")
            x += cb_passo
        # diagonais de canto (2 por extremidade da água) [COB-005]
        # a diagonal sempre aponta para DENTRO da água: +1 na ponta esquerda, -1 na
        # direita. Derivar isso de `xe < bb["x0"]` invertia a esquerda com beiral=0.
        for xe, direcao in ((bb["x0"] - beiral, 1), (bb["x1"] + beiral, -1)):
            mk(grupo, "diag_canto_1CB", p_cb, xe, yB, z_base,
               xe + direcao * 1.2, yB + h_c * 0.35, z_base + (zc - z_base) * 0.35,
               "diagonal de canto [COB-005]", conf)

    mk_ac(grupo_ts, "Chapa Gousset 150×150 #1,25 (nós de tesoura)", n_gusset, "un",
          "gusset por nó [1TS41: 62/painel]", conf)
    mk_ac(grupo_ts, "Parafuso flangeado — gusset (4/perfil, 2 lados)",
          n_gusset * gusset_paraf * 2, "un", "DX-01B", "parametrico")
    mk_ac(grupo_ts, "Parafuso flangeado — box banzo @200mm",
          math.ceil(n_t * (bb["z1"] - bb["z0"] + 2 * beiral) / (box_paraf_mm / 1000)),
          "un", "DX-09", "parametrico")

    if patio:
        # Pátio descoberto não leva telha — mas só desconta a parte que estava
        # COBERTA: `bb` já recuou o telhado pela faixa de varanda, então um pátio
        # dentro desse recuo nunca entrou em `area_telha` e descontá-lo inteiro
        # tiraria m² duas vezes. Recorta o retângulo do pátio contra a água.
        ov_x = max(0.0, min(patio["x"] + patio["w"], bb["x1"] + beiral)
                        - max(patio["x"], bb["x0"] - beiral))
        ov_z = max(0.0, min(patio["z"] + patio["d"], bb["z1"] + beiral)
                        - max(patio["z"], bb["z0"] - beiral))
        area_telha -= ov_x * ov_z * math.hypot(1, incl)
    if area_telha <= 0:
        # pátio maior que a água (ou telhado recuado demais pela faixa): m² negativo
        # de telha é dado incoerente, não zero (D4.1)
        raise DadoIndisponivel(
            f"{id_cob}: área de telha {area_telha:.2f} m² <= 0 — as áreas"
            " descobertas somam mais que o telhado; revisar area_descoberta")
    perda = 1 + telha_perda / 100
    mk_ac(grupo, f"{telha_tipo} (m²)", area_telha * perda, "m²",
          "trapezoidal × √(1+i²) × perda", conf)
    mk_ac(grupo, "Cumeeira (m)", bb["x1"] - bb["x0"], "m", "comprimento", conf)
    mk_ac(grupo, "Calha (m)", 2 * (bb["x1"] - bb["x0"]), "m", "2 águas", conf)

    return pecas, acess, alertas


# ---------- forro (porta fiel de gerarPecasForro, v7:1045-1057) ----------

def gerar_forro(con, projeto_id: int) -> tuple[list[Peca], list[Acessorio], list[str]]:
    """Forro de todos os pavimentos: borda no perímetro + perfis ao longo de z.

    Porta fiel de v7:1045-1057. O forro pendura logo abaixo do pé-direito
    (y = cota do nível + pé-direito - 0,05).
    """
    linha = con.execute(
        "SELECT perfil, perfil_borda, esp_m, grupo, confianca"
        "  FROM forro WHERE projeto_id = ?", (projeto_id,)).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"projeto {projeto_id} sem forro cadastrado")
    perfil, perfil_borda, esp, grupo, conf_forro = tuple(linha)

    conf = pior_confianca(conf_forro, "estimado")
    origem = "derivado bloco 1FR p.16-20: Ue70#0.80 + U72#0.80"
    pecas: list[Peca] = []
    seq: dict[str, int] = {}

    def mk(tipo, perf, x0, y0, z0, x1, y1, z1):
        pfx = "".join(c for c in tipo if c.isalpha())[:3].upper()
        chave = grupo + pfx
        seq[chave] = seq.get(chave, 0) + 1
        comp = math.hypot(x1 - x0, y1 - y0, z1 - z0)
        pecas.append(Peca(f"{grupo}-{pfx}{seq[chave]}", tipo, perf, x0, y0, x1, y1,
                          _round_js(comp, 4), origem, "forro", grupo, z0, z1, conf))

    niveis = con.execute(
        "SELECT indice, cota_m, pe_direito_m FROM nivel WHERE projeto_id = ?"
        " ORDER BY indice", (projeto_id,)).fetchall()
    if not niveis:
        raise DadoIndisponivel(f"projeto {projeto_id} sem níveis")

    for indice, cota, pd in niveis:
        if cota is None:
            raise DadoIndisponivel(
                f"nível {indice} sem cota_m — o forro pendura na cota (D4.1)")
        fp = contorno_pavimento(con, projeto_id, indice)
        if not fp:
            continue
        bb = bbox(fp)
        y = cota + pd - 0.05
        for i in range(len(fp)):
            a, b = fp[i], fp[(i + 1) % len(fp)]
            mk("borda_forro", perfil_borda, a[0], y, a[1], b[0], y, b[1])
        z = bb["z0"] + esp
        while z < bb["z1"] - 0.05:
            for xa, xb in scan(fp, z, "z"):
                mk("perfil_forro", perfil, xa, y, z, xb, y, z)
            z += esp

    return pecas, [], []


def segmentar_box003(con, pecas: list[Peca]) -> tuple[list[Peca], dict[str, int]]:
    """REGRA BOX-003 (porta fiel do bloco de `montarProjeto`, v7): peça linear
    acima da barra comercial (`barra_m` = 6,0 m, ref. 'REGRA BOX-003 [mont. p.53:
    peça 8583mm → emenda/pré-corte]') é segmentada ANTES do plano de corte.

    O detalhe é o que manda no kg comprado: `n = ceil(comp/6)` e cada segmento vale
    `comp/n` — partes IGUAIS, não 6+6+resto. Uma viga de 7,9 m vira 2×3,95 m, e cada
    3,95 m deixa 2,05 m de sobra na barra de 6 m. Nestar a peça inteira como emenda
    (6+6+3,8) encheria as barras e mentiria ~13% para baixo no aço comprado: era a
    "perda inexplicada" de 32,4% da 109 — que é regra de fabricação, não desperdício.

    Devolve as peças já segmentadas e as emendas por sistema (n-1 por peça cortada),
    que viram acessório (a emenda é material).
    """
    comp_max = _regra(_regras(con), "barra_m")
    out: list[Peca] = []
    emendas: dict[str, int] = {}
    for p in pecas:
        if p.comp <= comp_max + 1e-6:
            out.append(p)
            continue
        n = math.ceil(p.comp / comp_max)
        emendas[p.sistema] = emendas.get(p.sistema, 0) + (n - 1)
        for k in range(n):
            t0, t1 = k / n, (k + 1) / n
            out.append(replace(
                p,
                tag=f"{p.tag}{chr(97 + k)}",
                comp=_round_js(p.comp / n, 4),
                x0=p.x0 + (p.x1 - p.x0) * t0, y0=p.y0 + (p.y1 - p.y0) * t0,
                z0=p.z0 + (p.z1 - p.z0) * t0,
                x1=p.x0 + (p.x1 - p.x0) * t1, y1=p.y0 + (p.y1 - p.y0) * t1,
                z1=p.z0 + (p.z1 - p.z0) * t1,
                origem_regra=f"{p.origem_regra} · segm. REGRA BOX-003"))
    return out, emendas


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
    pecas: list[Peca]
    acessorios: list[Acessorio]

    @property
    def pendencias_estruturais(self) -> list[str]:
        """Alertas que dizem que a estrutura gerada NÃO passa na verificação
        (hoje: vão que reprova até viga dupla). O kg existe, mas é provisão."""
        return [a for a in self.alertas if a.startswith(MARCA_PENDENCIA)]


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
    acess: list[Acessorio] = [a for ep in paredes for a in ep.acessorios]
    alertas = [a for ep in paredes for a in ep.alertas]

    # Os 4 sistemas horizontais. Sistema ausente é ESCOPO, não dado faltante: um
    # galpão térreo não tem laje nem escada. Por isso aqui vira ALERTA (o gate de
    # macroetapa zerada barra a proposta lá na frente) em vez de exceção — enquanto
    # gerar_forro/gerar_laje, chamados direto, seguem exigindo seu input (D4.1).
    for tabela, gerador in (("laje", gerar_laje), ("escada", gerar_escada),
                            ("cobertura", gerar_cobertura)):
        ids_sis = [r[0] for r in con.execute(
            f"SELECT id FROM {tabela} WHERE projeto_id = ? ORDER BY id",
            (projeto_id,))]
        if not ids_sis:
            alertas.append(f"projeto sem {tabela}: kg do edifício não a inclui")
        for sid in ids_sis:
            p, a, al = gerador(con, sid)
            todas += p
            acess += a
            alertas += al
    if con.execute("SELECT 1 FROM forro WHERE projeto_id = ?",
                   (projeto_id,)).fetchone() is None:
        alertas.append("projeto sem forro: kg do edifício não o inclui")
    else:
        p, a, al = gerar_forro(con, projeto_id)
        todas += p
        acess += a
        alertas += al

    # REGRA BOX-003 antes do corte: peça acima de 6 m não existe — vira n partes
    # iguais com emenda. É o que o v7 faz em montarProjeto antes do resumoPorSistema,
    # e sem isso o aço comprado sai ~13% baixo (nestar 15,8 m como 6+6+3,8 enche as
    # barras; a obra corta 3×5,27 m e sobra 0,73 m em cada).
    barra = _regra(_regras(con), "barra_m")
    todas, emendas = segmentar_box003(con, todas)
    for sistema, n in sorted(emendas.items()):
        acess.append(Acessorio(
            "Emenda/luva de perfil (peça > barra 6m)", float(n), "un", sistema,
            "GERAL", "REGRA BOX-003 [p.53: BX2 8583mm]", "parametrico"))
        alertas.append(
            f"{n} peça(s) de {sistema} acima de 6 m segmentadas com emenda (ou"
            " pré-corte de fábrica). Confirmar com fornecedor: barra especial vs"
            " emenda em obra.")

    # Nesting POR SISTEMA, como o `resumoPorSistema` do v7 — que é o que gerou o
    # orçamento da obra (31.345 kg). Nestar tudo junto (global) faria a sobra de uma
    # barra de parede servir uma peça de cobertura e derrubaria o comprado ~8%: é
    # hipótese de compra centralizada que a obra NÃO praticou.
    plano: list[PlanoCortePerfil] = []
    por_sistema: dict[str, list[Peca]] = {}
    for p in todas:
        por_sistema.setdefault(p.sistema, []).append(p)
    for sistema in sorted(por_sistema):
        plano += plano_de_corte(con, por_sistema[sistema], barra)
    kg_liquido = sum(pl.kg for pl in plano)
    kg_comprado = sum(
        pl.barras * barra * _perfil(con, pl.perfil)["massa_kg_m"] for pl in plano)
    # coeficientes das regras são `estimado` (sem calibração de obra): o resultado
    # nunca é melhor que estimado, por pior que seja a geometria (D4)
    # dedup antes de passar: o domínio tem 3 valores, não ~2.900 (uma por peça)
    confianca = pior_confianca(*{ep.confianca for ep in paredes},
                               *{p.confianca for p in todas}, "estimado")
    return EstruturaProjeto(projeto_id, paredes, plano,
                            _round_js(kg_liquido), _round_js(kg_comprado),
                            confianca, alertas, todas, acess)


def _cargas(con) -> dict:
    chaves = ("carga_sc", "carga_g", "aco_fy", "aco_E", "coef_gm", "flecha_lim")
    regras = _regras(con)
    faltando = [c for c in chaves if c not in regras]
    if faltando:
        raise DadoIndisponivel(f"regra_lsf sem cargas: {faltando}")
    return {c: regras[c] for c in chaves}


# kv da alma sem enrijecedor transversal (bordas apoiadas). É constante da FÓRMULA
# de flambagem por cisalhamento, não conhecimento de obra — por isso vive no código,
# com a referência, e não em regra_lsf.
_KV_ALMA = 5.34


def propriedades_secao(con, perfil: str) -> dict:
    """A, Ix e Wx do perfil Ue pela sua geometria, método linear (NBR 14762 Anexo
    — seção tratada como linha de espessura t: A = t·Σℓ, Ix = Σ(t·ℓ·d² + I_próprio)).

    origem_regra: NBR 14762 (perfis formados a frio — propriedades geométricas pelo
    método linear, dimensões nominais sem raio de dobra).

    O v7 chumbava só o Ue250 (`SEC_Ue250`, v7:634) e verificava toda laje com ele,
    inclusive as de Ue200. Aqui a seção sai do perfil REAL. O método é validado
    contra aqueles mesmos valores em `test_metodo_linear_reproduz_a_secao_ue250_do_v7`
    (bate em <=0,08%), que é o que autoriza calcular em vez de chumbar.
    """
    p = _perfil(con, perfil)
    a, b, c = p["alma_mm"], p["aba_mm"], p["enrijecedor_mm"]
    t = p["espessura_mm"]
    if not c:
        raise DadoIndisponivel(
            f"perfil '{perfil}' sem enrijecedor_mm — o método linear aqui é para"
            " seção Ue (U enrijecido); guia U não é viga de laje")

    A = t * (a + 2 * b + 2 * c)
    i_alma = t * a ** 3 / 12                       # alma vertical, centro em y=0
    i_abas = 2 * (t * b) * (a / 2) ** 2            # abas horizontais em y=±a/2
    d_lip = a / 2 - c / 2                          # enrijecedores verticais
    i_lips = 2 * ((t * c) * d_lip ** 2 + t * c ** 3 / 12)
    Ix = i_alma + i_abas + i_lips
    return {"A": A, "Ix": Ix, "Wx": Ix / (a / 2), "alma_mm": a, "espessura_mm": t}


def dimensionar_viga(con, vao_m: float, trib_m: float, perfil: str) -> dict:
    """Verifica viga de laje no PERFIL informado (porta de v7:635-642, corrigida):
    ELS (flecha <= L/flecha_lim) e ELU (M<=MRd, V<=VRd) em modo simples; se falhar,
    tenta dupla (2 perfis); senão exige viga laminada.

    origem_regra: NBR 6120 (ações — SC=carga_sc sobrecarga, G=carga_g permanente)
    + NBR 14762 (perfis formados a frio — M/MRd via Wx, δ=L/flecha_lim, e VRd por
    flambagem por cisalhamento da alma, Vcr = 0,905·E·kv·t³/h, com t e h do perfil).

    O v7 lia sempre a seção do Ue250 e fixava t=2,0/h=250 no VRd, mesmo quando a
    laje era Ue200 — superestimando MRd em ~2,2x (Wx do Ue200 é 45% do Ue250).
    """
    C = _cargas(con)
    sec = propriedades_secao(con, perfil)
    sc, g = C["carga_sc"], C["carga_g"]
    fy, E, gM, flecha = C["aco_fy"], C["aco_E"], C["coef_gm"], C["flecha_lim"]
    A, Wx, Ix = sec["A"], sec["Wx"], sec["Ix"]
    t_alma, h_alma = sec["espessura_mm"], sec["alma_mm"]
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
    VRd = 0.905 * E * _KV_ALMA * t_alma ** 3 / h_alma / gM / 1000
    okS = M <= MRd and delta <= dLim and V <= VRd
    okD = M <= 2 * MRd and delta / 2 <= dLim and V <= 2 * VRd
    modo = "simples" if okS else ("dupla" if okD else "laminada")

    return {"modo": modo, "perfil": perfil, "M": _round_js(M, 1),
            "MRd": _round_js(MRd, 1), "delta": _round_js(delta, 1),
            "dLim": _round_js(dLim, 0), "V": _round_js(V, 1),
            "VRd": _round_js(VRd, 1)}


def derivar_quantitativos(con, projeto_id: int) -> dict:
    """Escreve o kg comprado do gerador na folha 03.01 da EAP como quantitativo
    PARAMETRICO (D2: re-derivar substitui a linha; a UNIQUE garante).

    Guarda: derivação paramétrica NUNCA sobrescreve linha MANUAL/TAKEOFF (dado
    melhor que 'estimado' de regra). Nesse caso preserva a linha e devolve
    `gravado=False` + `preservado=<origem existente>` — o chamador decide alertar.

    Os `alertas` e as `pendencias_estruturais` do gerador SOBEM no retorno e a
    pendência entra na `origem_regra` gravada: um vão que reprova na verificação
    não pode virar um kg limpo na EAP sem rastro (gate bloqueia, não avisa)."""
    est = gerar_estrutura(con, projeto_id)
    folha = con.execute(
        "SELECT id FROM eap_item WHERE codigo = '03.01'").fetchone()
    if folha is None:
        raise DadoIndisponivel("EAP sem a folha 03.01 (estrutura LSF, kg)")
    origem_regra = ("gerador de estrutura F2 (paredes+laje+escada+cobertura+forro,"
                    " porta fiel v7) — kg comprado em barras 6m")
    pendencias = est.pendencias_estruturais
    if pendencias:
        origem_regra += (f" · {MARCA_PENDENCIA} {len(pendencias)} vão(s) reprovam na"
                         " verificação estrutural — kg é PROVISÃO, exige revisão de"
                         " engenheiro antes de virar preço fechado")
    cur = con.execute(
        "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem,"
        " confianca, origem_regra) VALUES (?,?,?,'PARAMETRICO',?,?)"
        " ON CONFLICT (projeto_id, eap_item_id) DO UPDATE SET"
        "   quantidade=excluded.quantidade, origem=excluded.origem,"
        "   confianca=excluded.confianca, origem_regra=excluded.origem_regra"
        " WHERE quantitativo.origem = 'PARAMETRICO'",
        (projeto_id, folha[0], est.kg_comprado, est.confianca, origem_regra))
    resultado = {"kg_comprado": est.kg_comprado, "confianca": est.confianca,
                 "alertas": est.alertas, "pendencias_estruturais": pendencias}
    if cur.rowcount == 0:  # conflito com linha não-PARAMETRICO: nada escrito
        origem = con.execute(
            "SELECT origem FROM quantitativo WHERE projeto_id = ? AND eap_item_id = ?",
            (projeto_id, folha[0])).fetchone()[0]
        con.commit()
        return {**resultado, "gravado": False, "preservado": origem}
    con.commit()
    return {**resultado, "gravado": True}
