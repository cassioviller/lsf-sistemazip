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


def _sobreposicao_m(wa: dict, w: dict) -> float:
    """Quantos metros da parede `wa` correm POR CIMA da parede `w` (0 se não forem
    colineares). É o que substitui o casar-pelo-ponto-médio: parede é carga linear,
    e quem está sob um trecho dela só pode receber o kN daquele trecho. Pelo médio,
    uma interna perpendicular que apenas ENCOSTA em T no meio da de cima levava a
    carga inteira outra vez, e o prédio ganhava carga que não tem."""
    cx, cz = w["ax"], w["az"]
    ux, uz = w["bx"] - cx, w["bz"] - cz
    L = math.hypot(ux, uz)
    if L <= 1e-9:
        return 0.0
    ux, uz = ux / L, uz / L

    def _perp(px: float, pz: float) -> float:
        return abs((px - cx) * uz - (pz - cz) * ux)

    # as duas pontas da de cima têm que estar sobre a RETA da de baixo; se só uma
    # está, elas se cruzam (T ou X) e o encontro é um ponto, não um trecho de apoio
    if _perp(wa["ax"], wa["az"]) > _TOL or _perp(wa["bx"], wa["bz"]) > _TOL:
        return 0.0
    ta = (wa["ax"] - cx) * ux + (wa["az"] - cz) * uz
    tb = (wa["bx"] - cx) * ux + (wa["bz"] - cz) * uz
    return max(0.0, min(max(ta, tb), L) - max(min(ta, tb), 0.0))


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
    orfa_laje = orfa_cob = orfa_td = 0.0

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
        for wa in paredes_acima:
            if wa["id"] not in de_cima:
                continue
            comp_acima = math.hypot(wa["bx"] - wa["ax"], wa["bz"] - wa["az"])
            if comp_acima <= 0:
                continue
            trechos = {w["id"]: _sobreposicao_m(wa, w) for w in portantes}
            apoiado = sum(trechos.values())
            # duas de baixo colineares cobrindo o MESMO trecho contariam-no duas
            # vezes; normaliza para nunca descer mais do que a de cima tem
            fator = min(1.0, comp_acima / apoiado) if apoiado > comp_acima else 1.0
            for pid_alvo, t in trechos.items():
                vindo_kn[pid_alvo] += de_cima[wa["id"]] * t * fator
            # trecho SEM parede portante embaixo: ela apoia na laje, e a laje leva a
            # carga às paredes por um caminho que este modelo não tem. Fica órfã em
            # vez de evaporar — mesmo princípio da reação de viga sem apoio.
            orfa_td += de_cima[wa["id"]] * max(0.0, comp_acima - apoiado * fator)

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
                              orfa_takedown_kn=round(orfa_td, 1))
    return saida


def pendencias_do_takedown(con, projeto_id: int,
                           cargas: list[CargaParede] | None = None) -> list[str]:
    """O que o modelo NÃO resolve e por isso precisa viajar marcado até o gate.

    Dois sintomas, ambos medidos e não adivinhados:
      * carga ÓRFÃ — reação de viga que não caiu em parede nenhuma. Está apoiada em
        algo que o modelo não tem (a 1VG da obra, o reforço de vão de escada). Sumiu
        da conta, não do prédio;
      * parede interna sem carga de laje — a laje vence o polígono inteiro e
        descarrega tudo nas externas.
    """
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

    if resumo.orfa_takedown_kn > 0:
        pend.append(
            f"{MARCA_PENDENCIA} {resumo.orfa_takedown_kn:.0f} kN de parede não"
            " encontraram parede PORTANTE embaixo: as plantas dos níveis são"
            " diferentes, e essa parede apoia na LAJE, que devolve a carga às"
            " paredes do nível de baixo por um caminho que este modelo não tem"
            " (a laje só é modelada como carga, nunca como apoio de parede)."
            " A carga sumiu da conta, não do prédio: as paredes do térreo saem"
            " LEVES, e dimensionar a fundação com elas seria subdimensionar."
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
