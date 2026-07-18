"""MOTOR 3 — Takedown de cargas por parede real (Fase 2, item 3).

Generaliza o spike 4, que provou o núcleo com três coisas chumbadas no script:
a lista de camadas da parede, a área tributária (`trib=2.0`) e o empilhamento de
pavimentos. Aqui:

  * as camadas saem da `camada_parede` (migração 013) — conhecimento no banco;
  * a tributária sai da GEOMETRIA: cada viga de laje entrega metade da sua carga
    em cada apoio, e o apoio é a parede que contém a ponta da viga;
  * o empilhamento segue a planta: a parede de cima descarrega na parede de baixo
    que estiver sob ela.

origem_regra: NBR 6120 (ações — permanente das camadas, sobrecarga `carga_sc`)
+ NBR 6122 (o pré-dim. da fundação, que consome isto, vem na Fase 3).

LIMITE CONHECIDO, que vira pendência em vez de sair calado: a laje do gerador
vence o polígono inteiro (o `scan` corta no contorno externo, não nas paredes
internas), então a carga da laje cai toda nas paredes EXTERNAS. É o mesmo buraco
do `vao_ef = max_span/2` do gerador — o apoio do meio (a viga laminada 1VG que a
obra construiu) não está modelado. Consequência: externa sai conservadora (a
favor da segurança na fundação) e interna sai leve (contra). Ver
`pendencias_do_takedown`.

Regra I3 (spike 4, Fase 3): largura = max(teórica, MINIMO_CONSTRUTIVO).
Pendente: verificação de ancoragem/arrancamento por vento — gate externo, revisão
com engenheiro estrutural antes do aceite da Fase 3 (CLAUDE.md).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from lsf.geradores.estrutura import (DadoIndisponivel, MARCA_2A_VIGA,
                                     MARCA_PENDENCIA, _regra, _regras,
                                     gerar_cobertura, gerar_laje)
from lsf.motores.orcamento import pior_confianca

G = 9.81 / 1000          # kg → kN
_TOL = 0.05              # tolerância de "ponta da viga cai nesta parede" (m)
_PASSO_PAREDE_M = 0.25   # passo da parede que apoia na laje (aproximação numérica)


@dataclass(frozen=True)
class CargaParede:
    """Carga linear característica numa parede (kN/m), decomposta pela origem —
    decomposta porque um total seco não deixa ninguém conferir de onde veio."""
    parede_id: int
    nivel_indice: int
    comp_m: float
    externa: bool
    g_propria_kn_m: float      # peso próprio da parede (camadas × pé-direito)
    g_laje_kn_m: float         # permanente da laje que apoia nela
    q_laje_kn_m: float         # sobrecarga de uso da laje
    g_cobertura_kn_m: float    # cobertura, se for o último pavimento
    de_cima_kn_m: float        # takedown: o que a parede de cima entrega
    total_kn_m: float
    confianca: str
    origem_regra: str


def peso_parede_kn_m2(con, externa: bool) -> tuple[float, str]:
    """Peso próprio da parede (kN/m²) somando as camadas do tipo, e a PIOR
    confiança entre elas (D4). Camada ausente é erro: parede de peso zero viraria
    fundação subdimensionada, calada (D4.1)."""
    tipo = "externa" if externa else "interna"
    linhas = con.execute(
        "SELECT p.kg_m2, cp.faces, p.confianca"
        "  FROM camada_parede cp JOIN peso_camada p ON p.material = cp.material"
        " WHERE cp.tipo = ?", (tipo,)).fetchall()
    if not linhas:
        raise DadoIndisponivel(
            f"camada_parede sem camadas para parede '{tipo}' — sem elas a parede"
            " pesaria zero e a fundação sairia subdimensionada (D4.1)")
    kg_m2 = sum(kg * faces for kg, faces, _ in linhas)
    conf = pior_confianca(*(c for _, _, c in linhas), "estimado")
    return kg_m2 * G, conf


def _ponto_na_parede(px: float, pz: float, ax: float, az: float,
                     bx: float, bz: float) -> bool:
    """O ponto cai sobre o segmento AB (dentro de `_TOL`)? Distância ponto-segmento."""
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    if L2 <= 1e-12:
        return math.hypot(px - ax, pz - az) <= _TOL
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / L2))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz)) <= _TOL


def _sobreposicao_intervalo(wa: dict, w: dict) -> tuple[float, float] | None:
    """Em QUE trecho da parede `wa` — medido em metros a partir da ponta A dela — a
    parede `w` corre por baixo. `None` se não forem colineares.

    É o que substitui o casar-pelo-ponto-médio: parede é carga linear, e quem está
    sob um trecho dela só pode receber o kN daquele trecho. Pelo médio, uma interna
    perpendicular que apenas ENCOSTA em T no meio da de cima levava a carga inteira
    outra vez, e o prédio ganhava carga que não tem."""
    ux, uz = wa["bx"] - wa["ax"], wa["bz"] - wa["az"]
    La = math.hypot(ux, uz)
    if La <= 1e-9:
        return None
    ux, uz = ux / La, uz / La

    def _perp(px: float, pz: float) -> float:
        return abs((px - wa["ax"]) * uz - (pz - wa["az"]) * ux)

    # as duas pontas da de baixo têm que estar sobre a RETA da de cima; se só uma
    # está, elas se cruzam (T ou X) e o encontro é um ponto, não um trecho de apoio
    if _perp(w["ax"], w["az"]) > _TOL or _perp(w["bx"], w["bz"]) > _TOL:
        return None
    ta = (w["ax"] - wa["ax"]) * ux + (w["az"] - wa["az"]) * uz
    tb = (w["bx"] - wa["ax"]) * ux + (w["bz"] - wa["az"]) * uz
    lo, hi = max(min(ta, tb), 0.0), min(max(ta, tb), La)
    return (lo, hi) if hi > lo + 1e-9 else None


def _sobreposicao_m(wa: dict, w: dict) -> float:
    """Quantos metros da parede `wa` correm por cima da parede `w`."""
    iv = _sobreposicao_intervalo(wa, w)
    return iv[1] - iv[0] if iv else 0.0


def _subtrair(iv: tuple[float, float],
              ocupados: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """O que sobra de `iv` depois de tirar os trechos já `ocupados` — impede que duas
    paredes de baixo cobrindo o MESMO trecho o contem duas vezes."""
    restos = [iv]
    for lo, hi in ocupados:
        novos = []
        for a, b in restos:
            if hi <= a or lo >= b:
                novos.append((a, b))
                continue
            if a < lo:
                novos.append((a, lo))
            if hi < b:
                novos.append((hi, b))
        restos = novos
    return restos


def _complemento(ocupados: list[tuple[float, float]], L: float) -> list[tuple[float, float]]:
    """Os trechos de [0, L] que ninguém cobre — a parede de cima ali não tem parede
    embaixo, e o que a segura é a laje."""
    livres: list[tuple[float, float]] = []
    pos = 0.0
    for lo, hi in sorted(ocupados):
        if lo > pos + 1e-9:
            livres.append((pos, min(lo, L)))
        pos = max(pos, hi)
        if pos >= L:
            break
    if pos < L - 1e-9:
        livres.append((pos, L))
    return livres


def _apoiar_na_laje(pontos: list[tuple[float, float, float]], pecas_laje,
                    paredes: list[dict], esp: float) -> tuple[dict, float]:
    """Leva até as paredes as cargas PONTUAIS (kN) que caem sobre a laje.

    É o caminho real da parede que não tem parede embaixo: ela apoia na laje, a laje
    leva às vigas, e as vigas às paredes. Duas alavancas em série:

      1. o ponto cai ENTRE duas vigas vizinhas → reparte pela alavanca (a laje é
         unidirecional: a chapa de piso vence de viga a viga);
      2. cada viga é biapoiada e entrega `P·(L-a)/L` e `P·a/L` nos seus dois apoios,
         com `a` medido do primeiro apoio.

    origem_regra: estática de viga biapoiada com carga pontual [NBR 6120 (ações) /
    NBR 14762 (o perfil que as recebe)].

    ATENÇÃO — o que isto NÃO faz: não verifica se a viga AGUENTA a parede que caiu
    em cima dela. Uma viga de laje sob uma parede normalmente pede reforço (dobrar
    ou perfil maior), e o gerador não emite esse reforço. Ver `pendencias_do_takedown`.
    """
    por_parede = {w["id"]: 0.0 for w in paredes}
    vigas = [p for p in pecas_laje
             if p.tipo == "viga_laje"
             and not p.origem_regra.startswith(MARCA_2A_VIGA)]
    total = sum(kn for _, _, kn in pontos)
    if not vigas:
        return por_parede, total

    # laje unidirecional: as vigas são todas paralelas, e o eixo da 1ª define o
    # sistema — `u` ao longo da viga, `n` na perpendicular, que é onde elas se espaçam
    v0 = vigas[0]
    ux, uz = v0.x1 - v0.x0, v0.z1 - v0.z0
    Lu = math.hypot(ux, uz)
    if Lu <= 1e-9:
        return por_parede, total
    ux, uz = ux / Lu, uz / Lu
    nx, nz = -uz, ux

    def _s(px: float, pz: float) -> float:      # coordenada ENTRE vigas
        return px * nx + pz * nz

    def _t(px: float, pz: float) -> float:      # coordenada AO LONGO da viga
        return px * ux + pz * uz

    eixo = [(_s(v.x0, v.z0), _t(v.x0, v.z0), _t(v.x1, v.z1)) for v in vigas]
    carga_viga: dict[int, list[tuple[float, float]]] = {}
    orfas = 0.0

    for px, pz, kn in pontos:
        sp, tp = _s(px, pz), _t(px, pz)
        # só vigas que realmente passam sob o ponto (o vão da escada não tem viga)
        cand = [(s, i) for i, (s, t0, t1) in enumerate(eixo)
                if min(t0, t1) - _TOL <= tp <= max(t0, t1) + _TOL]
        if not cand:
            orfas += kn
            continue
        abaixo = max((c for c in cand if c[0] <= sp + 1e-9), default=None)
        acima = min((c for c in cand if c[0] >= sp - 1e-9), default=None)
        if abaixo is None or acima is None:
            # o ponto está fora do meio-a-meio: só há viga de um lado
            unica = abaixo or acima
            if abs(unica[0] - sp) > esp + _TOL:
                orfas += kn          # nenhuma viga ao alcance da modulação
            else:
                carga_viga.setdefault(unica[1], []).append((tp, kn))
            continue
        if abaixo[1] == acima[1] or abs(acima[0] - abaixo[0]) < 1e-9:
            carga_viga.setdefault(abaixo[1], []).append((tp, kn))
            continue
        f = (sp - abaixo[0]) / (acima[0] - abaixo[0])
        carga_viga.setdefault(abaixo[1], []).append((tp, kn * (1 - f)))
        carga_viga.setdefault(acima[1], []).append((tp, kn * f))

    for i, cargas in carga_viga.items():
        v = vigas[i]
        t0, t1 = eixo[i][1], eixo[i][2]
        L = abs(t1 - t0)
        alvos = [next((w for w in paredes
                       if _ponto_na_parede(x, z, w["ax"], w["az"], w["bx"], w["bz"])),
                      None)
                 for x, z in ((v.x0, v.z0), (v.x1, v.z1))]
        for tp, kn in cargas:
            if L <= 1e-9:
                orfas += kn
                continue
            r1 = kn * abs(tp - t0) / L          # reação no apoio da ponta t1
            for alvo, r in zip(alvos, (kn - r1, r1)):
                if alvo is None:
                    orfas += r                  # viga que morre na 1VG que não temos
                else:
                    por_parede[alvo["id"]] += r
    return por_parede, orfas


def _paredes_do_nivel(con, projeto_id: int, indice: int) -> list[dict]:
    return [dict(zip(("id", "ax", "az", "bx", "bz", "externa", "portante",
                      "confianca", "pe_direito"), r))
            for r in con.execute(
                "SELECT p.id, a.x, a.y, b.x, b.y, p.externa, p.portante, p.confianca,"
                "       n.pe_direito_m"
                "  FROM parede p"
                "  JOIN no_planta a ON a.id = p.no_a"
                "  JOIN no_planta b ON b.id = p.no_b"
                "  JOIN nivel n ON n.id = p.nivel_id"
                " WHERE n.projeto_id = ? AND n.indice = ? ORDER BY p.id",
                (projeto_id, indice))]


def _reacoes_das_vigas(pecas, tipo: str, w_kn_m: float, paredes: list[dict],
                       recuo_apoio_m: float = 0.0) -> dict:
    """Distribui as reações das vigas de `tipo` nas paredes que as apoiam.

    Cada viga é biapoiada: entrega `w·L/2` em cada apoio (NBR 6120, carga uniforme).

    `recuo_apoio_m` puxa o ponto de apoio para dentro, a partir da ponta. É o que a
    tesoura pede: o banzo vai de `za-beiral` a `zb+beiral`, então as PONTAS estão no
    ar, no beiral — ela apoia onde cruza a parede, `beiral` para dentro. Atribuir
    pela ponta fazia a carga do telhado evaporar (0,07 kN/m nas paredes do topo).

    Reação que não cai em parede nenhuma (borda de vão de escada, apoio do meio que
    o modelo não tem) é CONTADA e devolvida: carga que some da conta não some do
    prédio."""
    por_parede: dict[int, float] = {p["id"]: 0.0 for p in paredes}
    orfas = 0.0
    for p in pecas:
        if p.tipo != tipo:
            continue
        # a 2ª viga do par dá CAPACIDADE ao mesmo vão, não carrega outra faixa de
        # laje: contá-la dobraria a carga (a mesma armadilha da cantoneira DX-06)
        if p.origem_regra.startswith(MARCA_2A_VIGA):
            continue
        reacao = w_kn_m * p.comp / 2
        # direção unitária da peça, para recuar o apoio a partir de cada ponta
        dx, dz = p.x1 - p.x0, p.z1 - p.z0
        L = math.hypot(dx, dz)
        ux, uz = (dx / L, dz / L) if L > 1e-9 else (0.0, 0.0)
        r = recuo_apoio_m
        apoios = ((p.x0 + ux * r, p.z0 + uz * r), (p.x1 - ux * r, p.z1 - uz * r))
        for px, pz in apoios:
            alvo = next((w for w in paredes
                         if _ponto_na_parede(px, pz, w["ax"], w["az"],
                                             w["bx"], w["bz"])), None)
            if alvo is None:
                orfas += reacao
            else:
                por_parede[alvo["id"]] += reacao
    return {"por_parede": por_parede, "orfas_kn": orfas}


@dataclass(frozen=True)
class ResumoTakedown:
    """O takedown + o que ele NÃO conseguiu apoiar. A carga órfã é o diagnóstico
    honesto do motor: reação de viga que não caiu em parede nenhuma está apoiada em
    algo que o modelo não tem (a 1VG da obra, o reforço de vão de escada). Ela
    sumiu da CONTA, não do prédio."""
    cargas: list[CargaParede]
    orfa_laje_kn: float
    orfa_cobertura_kn: float
    orfa_takedown_kn: float = 0.0
    parede_na_laje_kn: float = 0.0   # parede que desceu APOIADA na laje, não em parede


def takedown_por_parede(con, projeto_id: int, com_resumo: bool = False):
    """Carga linear em cada parede portante, do topo para o radier.

    A ordem importa: só dá para somar o que vem de cima depois de fechar o nível
    de cima. Por isso o laço vai do maior `indice` para o menor.

    `com_resumo=True` devolve `ResumoTakedown`, com a carga órfã junto (segue o
    precedente do `gerar_laje(com_info=)`). A função continua pura (D6): o resumo
    é retorno, não estado guardado no motor.
    """
    R = _regras(con)
    q_uso = _regra(R, "carga_sc")                      # kN/m² [NBR 6120]

    # Peças CRUAS dos geradores, NÃO as de `gerar_estrutura`: aquelas já passaram
    # pela BOX-003, que reparte uma viga de 15,8 m em 3 segmentos de 5,27 m para o
    # corte. Segmento de fábrica não é vão estrutural — tratar cada um como viga
    # biapoiada joga as pontas dos segmentos do meio no vazio. Foi assim que 68% da
    # carga da laje (1.722 kN) virou órfã, até a própria métrica de órfã acusar.
    niveis = [r[0] for r in con.execute(
        "SELECT indice FROM nivel WHERE projeto_id = ? ORDER BY indice DESC",
        (projeto_id,))]
    if not niveis:
        raise DadoIndisponivel(f"projeto {projeto_id} sem níveis")

    contrapiso = con.execute(
        "SELECT kg_m2, confianca FROM peso_camada WHERE material = ?",
        ("Contrapiso seco (2x OSB/cimentícia)",)).fetchone()
    if contrapiso is None:
        raise DadoIndisponivel("peso_camada sem 'Contrapiso seco' — a laje pesaria"
                               " só o aço (D4.1)")

    saida: list[CargaParede] = []
    de_cima: dict[int, float] = {}      # parede_id do nível de cima → kN/m
    orfa_laje = orfa_cob = orfa_td = na_laje = 0.0

    for indice in niveis:
        paredes = _paredes_do_nivel(con, projeto_id, indice)
        if not paredes:
            continue
        paredes_acima = _paredes_do_nivel(con, projeto_id, indice + 1)

        # --- laje que APOIA neste nível (pav_base == indice) ---
        laje = con.execute(
            "SELECT id, esp_m, grupo FROM laje WHERE projeto_id = ? AND pav_base = ?",
            (projeto_id, indice)).fetchone()
        reac_laje = {"por_parede": {}, "orfas_kn": 0.0}
        g_laje_kn_m2 = q_laje_kn_m2 = 0.0
        pecas_laje = None
        esp = 0.0
        if laje is not None:
            laje_id, esp, _grupo = tuple(laje)
            g_laje_kn_m2 = contrapiso[0] * G
            q_laje_kn_m2 = q_uso
            # a viga carrega a faixa da sua modulação (`esp`)
            w_viga = (g_laje_kn_m2 + q_laje_kn_m2) * esp
            pecas_laje, _, _ = gerar_laje(con, laje_id)
            reac_laje = _reacoes_das_vigas(pecas_laje, "viga_laje", w_viga, paredes)

        # --- cobertura, se este for o último pavimento ---
        reac_cob = {"por_parede": {}, "orfas_kn": 0.0}
        if indice == max(niveis):
            telha = con.execute(
                "SELECT kg_m2 FROM peso_camada WHERE material LIKE 'Telha%'"
                " ORDER BY kg_m2 DESC").fetchone()
            esp_tes = _regra(R, "cobertura_esp_tesoura")
            w_tes = ((telha[0] if telha else 0.0) * G) * esp_tes
            # a tesoura apoia `beiral` para dentro da ponta: o banzo vai de
            # za-beiral a zb+beiral, e o trecho do beiral está em balanço
            cob = con.execute(
                "SELECT id, beiral_m FROM cobertura WHERE projeto_id = ? ORDER BY id",
                (projeto_id,)).fetchone()
            if cob is not None:
                pecas_cob, _, _ = gerar_cobertura(con, cob[0])
                reac_cob = _reacoes_das_vigas(
                    pecas_cob, "banzo_inferior", w_tes, paredes,
                    recuo_apoio_m=cob[1] or 0.0)
        orfa_laje += reac_laje["orfas_kn"]
        orfa_cob += reac_cob["orfas_kn"]

        # --- takedown: reparte cada parede de cima nas de baixo, POR TRECHO ---
        # A de cima é kN/m DELA: o trecho de `t` metros que corre sobre uma de baixo
        # entrega `kN/m × t` kN nela, e nada nas outras. Só parede PORTANTE é apoio.
        portantes = [w for w in paredes if w["portante"]]
        vindo_kn: dict[int, float] = {w["id"]: 0.0 for w in portantes}
        pontos_na_laje: list[tuple[float, float, float]] = []
        for wa in paredes_acima:
            if wa["id"] not in de_cima:
                continue
            comp_acima = math.hypot(wa["bx"] - wa["ax"], wa["bz"] - wa["az"])
            if comp_acima <= 0:
                continue
            q = de_cima[wa["id"]]                       # kN/m DELA
            ux_a = (wa["bx"] - wa["ax"]) / comp_acima
            uz_a = (wa["bz"] - wa["az"]) / comp_acima

            # 1) trecho a trecho, quem tem parede portante embaixo desce direto nela
            ocupados: list[tuple[float, float]] = []
            for w in portantes:
                iv = _sobreposicao_intervalo(wa, w)
                if iv is None:
                    continue
                for a, b in _subtrair(iv, ocupados):
                    vindo_kn[w["id"]] += q * (b - a)
                    ocupados.append((a, b))

            # 2) o resto apoia na LAJE: vira carga distribuída em passos, que a laje
            #    leva às paredes pelas vigas. Discretizar é aproximação numérica
            #    assumida (passo de 25 cm), não modelo: a alternativa seria integrar
            #    a linha de influência de cada viga, com o mesmo resultado.
            for a, b in _complemento(ocupados, comp_acima):
                n = max(1, math.ceil((b - a) / _PASSO_PAREDE_M))
                ds = (b - a) / n
                for k in range(n):
                    t = a + (k + 0.5) * ds
                    pontos_na_laje.append(
                        (wa["ax"] + ux_a * t, wa["az"] + uz_a * t, q * ds))

        if pontos_na_laje:
            na_laje += sum(kn for _, _, kn in pontos_na_laje)
            if pecas_laje is None:
                # parede pendurada sobre um nível sem laje: não há o que a segure
                orfa_td += sum(kn for _, _, kn in pontos_na_laje)
            else:
                rp, orf = _apoiar_na_laje(pontos_na_laje, pecas_laje, portantes, esp)
                for pid_alvo, kn in rp.items():
                    vindo_kn[pid_alvo] += kn
                orfa_td += orf

        novo_de_cima: dict[int, float] = {}
        for w in paredes:
            if not w["portante"]:
                continue
            comp = math.hypot(w["bx"] - w["ax"], w["bz"] - w["az"])
            if comp <= 0:
                continue
            g_m2, conf_camadas = peso_parede_kn_m2(con, bool(w["externa"]))
            g_propria = g_m2 * w["pe_direito"]

            g_laje = q_laje = 0.0
            if laje is not None:
                total = reac_laje["por_parede"].get(w["id"], 0.0) / comp
                # separa permanente/sobrecarga na mesma proporção do w_viga
                soma = g_laje_kn_m2 + q_laje_kn_m2
                g_laje = total * (g_laje_kn_m2 / soma) if soma else 0.0
                q_laje = total - g_laje
            g_cob = reac_cob["por_parede"].get(w["id"], 0.0) / comp

            # o que veio de cima já está em kN; vira kN/m no comprimento DESTA
            vindo = vindo_kn.get(w["id"], 0.0) / comp

            total = g_propria + g_laje + q_laje + g_cob + vindo
            novo_de_cima[w["id"]] = total
            saida.append(CargaParede(
                parede_id=w["id"], nivel_indice=indice, comp_m=round(comp, 3),
                externa=bool(w["externa"]),
                g_propria_kn_m=round(g_propria, 3), g_laje_kn_m=round(g_laje, 3),
                q_laje_kn_m=round(q_laje, 3), g_cobertura_kn_m=round(g_cob, 3),
                de_cima_kn_m=round(vindo, 3), total_kn_m=round(total, 3),
                confianca=pior_confianca(conf_camadas, w["confianca"], "estimado"),
                origem_regra=(
                    "NBR 6120: permanente das camadas [camada_parede] + sobrecarga"
                    f" carga_sc={q_uso} kN/m²; tributária pela reação das vigas"
                    " (w·L/2 por apoio); takedown pela parede de cima")))
        de_cima = novo_de_cima

    if com_resumo:
        return ResumoTakedown(cargas=saida, orfa_laje_kn=round(orfa_laje, 1),
                              orfa_cobertura_kn=round(orfa_cob, 1),
                              orfa_takedown_kn=round(orfa_td, 1),
                              parede_na_laje_kn=round(na_laje, 1))
    return saida


def pendencias_do_takedown(con, projeto_id: int,
                           resumo: ResumoTakedown | None = None) -> list[str]:
    """O que o modelo NÃO resolve e por isso precisa viajar marcado até o gate.

    Dois sintomas, ambos medidos e não adivinhados:
      * carga ÓRFÃ — reação de viga que não caiu em parede nenhuma. Está apoiada em
        algo que o modelo não tem (a 1VG da obra, o reforço de vão de escada). Sumiu
        da conta, não do prédio;
      * parede interna sem carga de laje — a laje vence o polígono inteiro e
        descarrega tudo nas externas.

    `resumo` pré-computado evita rodar o takedown duas vezes quando o chamador já
    o tem (derivar_cargas); sem ele, computa aqui.
    """
    if resumo is None:
        resumo = takedown_por_parede(con, projeto_id, com_resumo=True)
    cargas = resumo.cargas
    pend: list[str] = []

    externas = [c for c in cargas if c.externa and c.nivel_indice == 0]
    internas = [c for c in cargas if not c.externa and c.nivel_indice == 0]
    if externas and internas:
        med_ext = sum(c.total_kn_m for c in externas) / len(externas)
        med_int = sum(c.total_kn_m for c in internas) / len(internas)
        if med_int < med_ext / 3:
            pend.append(
                f"{MARCA_PENDENCIA} Apoio intermediário não modelado: a laje vence o"
                " polígono inteiro e descarrega nas paredes EXTERNAS"
                f" (térreo: externa ~{med_ext:.1f} kN/m vs interna ~{med_int:.1f}"
                " kN/m). A obra resolve com a viga laminada 1VG + pilares 1AL, que o"
                " gerador não emite (é o mesmo buraco do vao_ef=max_span/2). A carga"
                " das externas sai conservadora; a das internas, CONTRA a segurança."
                " Exige verificação de engenheiro estrutural.")

    if resumo.parede_na_laje_kn > 0:
        pend.append(
            f"{MARCA_PENDENCIA} {resumo.parede_na_laje_kn:.0f} kN de parede não têm"
            " parede portante embaixo (as plantas dos níveis são diferentes) e"
            " descem APOIADOS NA LAJE. O caminho está modelado — laje → vigas →"
            " paredes, por alavanca —, mas o que ele produz NÃO está verificado:"
            " (a) a viga de laje que recebe uma parede em cima normalmente exige"
            " reforço (dobrar o perfil ou subir a seção), e o gerador NÃO emite esse"
            " reforço, então ele não está no kg nem no preço; (b) a modelagem supõe"
            " que a laje aguenta a reação concentrada. Nenhuma das duas é conclusão"
            " deste motor. Exige verificação de engenheiro estrutural.")

    if resumo.orfa_takedown_kn > 0:
        pend.append(
            f"{MARCA_PENDENCIA} {resumo.orfa_takedown_kn:.0f} kN de parede não"
            " acharam apoio nenhum — nem parede portante embaixo, nem viga de laje"
            " (caem sobre vão de escada ou sobre trecho que o scan da laje não"
            " cobre). Essa carga sumiu da conta, não do prédio: as paredes do nível"
            " de baixo saem LEVES e a fundação sairia subdimensionada."
            " Exige verificação de engenheiro estrutural.")

    orfa = resumo.orfa_laje_kn + resumo.orfa_cobertura_kn
    if orfa > 0:
        pend.append(
            f"{MARCA_PENDENCIA} {orfa:.0f} kN de reação de viga não encontraram apoio"
            f" em parede (laje {resumo.orfa_laje_kn:.0f} kN, cobertura"
            f" {resumo.orfa_cobertura_kn:.0f} kN): apoiam em elementos fora do modelo"
            " (viga laminada, reforço de vão de escada). Essa carga não chega à"
            " fundação pelo takedown — dimensionar a fundação só com o que sobrou"
            " seria subdimensionar. Exige verificação de engenheiro estrutural.")
    return pend


def derivar_cargas(con, projeto_id: int) -> dict:
    """Roda o takedown e grava as pendências dele na tabela `pendencia`
    (motor='cargas'), onde o gate de publicação as lê. Pendência que morre no
    retorno de função é disclaimer morto — o gate bloqueia, não avisa (CLAUDE.md).

    Espelho do `derivar_quantitativos` do gerador: re-derivar TROCA as linhas
    DESTE motor (pendência resolvida some, senão o gate trava para sempre) e não
    toca as de outros motores. As cargas em si não viram `quantitativo`: kN/m não
    é folha da EAP — é o input do pré-dimensionamento de fundação (Fase 3), que
    consome o retorno."""
    resumo = takedown_por_parede(con, projeto_id, com_resumo=True)
    pendencias = pendencias_do_takedown(con, projeto_id, resumo)

    con.execute("DELETE FROM pendencia WHERE projeto_id = ? AND motor = 'cargas'",
                (projeto_id,))
    for msg in pendencias:
        con.execute(
            "INSERT OR IGNORE INTO pendencia (projeto_id, motor, mensagem)"
            " VALUES (?, 'cargas', ?)", (projeto_id, msg))
    con.commit()

    return {"cargas": resumo.cargas, "resumo": resumo, "pendencias": pendencias}
