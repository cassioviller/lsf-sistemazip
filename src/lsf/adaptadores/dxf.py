"""Adaptador DXF → planta_normalizada (Fase 5; generaliza o spike 1).

Rota do arquitetônico digital (docs/02, rotas duplas): linhas na layer PAREDE,
em PARES PARALELOS à distância de uma espessura plausível (0,09–0,25 m) e com
sobreposição real ao longo do eixo, viram eixos de parede; eixos viram
`no_planta`/`parede` com origem='DXF' e confiança='estimado' (traço de terceiro
sem conferência não é `real`). O perfil fica NULL — é atribuído na tela, e o
gerador RECUSA derivar sem ele (D4.1): parede sem perfil é decisão pendente,
não default silencioso.

Linha sem par não vira parede: vira AVISO. Inventar parede de linha solta é o
erro que a rota manual existe para evitar. ezdxf é MIT (docs/04)."""
from __future__ import annotations

import math

_LAYER = "PAREDE"
_ESP_MIN, _ESP_MAX = 0.09, 0.25
_TOL_NO = 0.005


def _eixo_de_par(s1, s2):
    """Eixo médio de duas linhas paralelas à distância de uma espessura de
    parede, com sobreposição longitudinal real (≥50% da menor). Porta do spike 1
    + o critério de sobreposição que o spike não precisava (2 linhas apenas)."""
    (a1, b1), (a2, b2) = s1, s2
    v1 = (b1[0] - a1[0], b1[1] - a1[1])
    v2 = (b2[0] - a2[0], b2[1] - a2[1])
    if abs(v1[0] * v2[1] - v1[1] * v2[0]) > 1e-6:
        return None                                   # não paralelas
    L1 = math.hypot(*v1)
    if L1 < 1e-9:
        return None
    n = (-v1[1] / L1, v1[0] / L1)
    dist = abs((a2[0] - a1[0]) * n[0] + (a2[1] - a1[1]) * n[1])
    if not (_ESP_MIN <= dist <= _ESP_MAX):
        return None
    u = (v1[0] / L1, v1[1] / L1)
    t = sorted([((p[0] - a1[0]) * u[0] + (p[1] - a1[1]) * u[1]) for p in (a2, b2)])
    sobre = min(L1, t[1]) - max(0.0, t[0])
    L2 = math.hypot(*v2)
    if sobre < 0.5 * min(L1, L2):
        return None                                   # paralelas mas não par
    # eixo no trecho comum, na linha média
    ta, tb = max(0.0, t[0]), min(L1, t[1])
    meio = (n[0] * dist / 2 * (1 if (a2[0] - a1[0]) * n[0]
                               + (a2[1] - a1[1]) * n[1] > 0 else -1),
            n[1] * dist / 2 * (1 if (a2[0] - a1[0]) * n[0]
                               + (a2[1] - a1[1]) * n[1] > 0 else -1))
    p0 = (a1[0] + u[0] * ta + meio[0], a1[1] + u[1] * ta + meio[1])
    p1 = (a1[0] + u[0] * tb + meio[0], a1[1] + u[1] * tb + meio[1])
    return p0, p1, round(dist, 3)


def _no(con, nivel_id: int, x: float, y: float) -> int:
    linha = con.execute(
        "SELECT id FROM no_planta WHERE nivel_id = ?"
        " AND ABS(x - ?) < ? AND ABS(y - ?) < ?",
        (nivel_id, x, _TOL_NO, y, _TOL_NO)).fetchone()
    if linha:
        return linha[0]
    return con.execute(
        "INSERT INTO no_planta (nivel_id, x, y, confianca)"
        " VALUES (?,?,?,'estimado')", (nivel_id, x, y)).lastrowid


def importar_dxf(con, nivel_id: int, caminho) -> dict:
    """Importa as paredes do DXF para o nível. Devolve
    {'paredes_criadas': n, 'avisos': [...]} e NUNCA inventa parede de linha
    sem par. O chamador decide commitar."""
    import ezdxf

    doc = ezdxf.readfile(str(caminho))
    linhas = [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
              for e in doc.modelspace().query("LINE")
              if e.dxf.layer.upper() == _LAYER]
    avisos: list[str] = []
    if not linhas:
        layers = sorted({e.dxf.layer for e in doc.modelspace().query("LINE")})
        avisos.append(
            f"nenhuma LINE na layer '{_LAYER}' — layers com linhas no arquivo:"
            f" {', '.join(layers) if layers else 'nenhuma'}")
        return {"paredes_criadas": 0, "avisos": avisos}

    usadas: set[int] = set()
    criadas = 0
    for i in range(len(linhas)):
        if i in usadas:
            continue
        for j in range(i + 1, len(linhas)):
            if j in usadas:
                continue
            eixo = _eixo_de_par(linhas[i], linhas[j])
            if eixo is None:
                continue
            (x0, y0), (x1, y1), esp = eixo[0], eixo[1], eixo[2]
            no_a = _no(con, nivel_id, round(x0, 4), round(y0, 4))
            no_b = _no(con, nivel_id, round(x1, 4), round(y1, 4))
            con.execute(
                "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m,"
                " portante, externa, perfil_codigo, origem, confianca,"
                " origem_regra) VALUES (?,?,?,?,1,0,NULL,'DXF','estimado',"
                " 'adaptador DXF: par de linhas paralelas na layer PAREDE')",
                (nivel_id, no_a, no_b, esp))
            usadas.update((i, j))
            criadas += 1
            break
    soltas = len(linhas) - len(usadas)
    if soltas:
        avisos.append(
            f"{soltas} linha(s) da layer {_LAYER} sem par paralelo — NÃO viraram"
            " parede (traçar manualmente na tela ou corrigir o DXF)")
    if criadas:
        avisos.append(
            f"{criadas} parede(s) importadas SEM perfil e como interna/portante:"
            " atribuir perfil e classificar externas na tela antes de derivar")
    return {"paredes_criadas": criadas, "avisos": avisos}
