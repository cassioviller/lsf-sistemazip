"""Helpers de geometria — porta fiel de v7:684-794 (chainPolygon/scan/polyArea/
cortarSpan). Funções puras: recebem polígonos (lista de vértices (x,z)) e devolvem
áreas, intervalos e recortes. Sem SQL, sem estado. O footprint por pavimento é o
contorno das paredes externas encadeado por `encadear_contorno` (cadeia D3)."""
from __future__ import annotations

import math

_EPS_NO = 0.02   # tolerância de coincidência de nós (v7: 0.02)
_EPS_IV = 0.05   # intervalo mínimo internamente válido (v7: 0.05)
_EPS_SPAN = 0.1   # fragmento mínimo em cortar_span (v7:797)


def encadear_contorno(segmentos):
    """chainPolygon: encadeia segmentos externos num polígono fechado."""
    segs = [{"a": tuple(a), "b": tuple(b)} for a, b in segmentos]
    if not segs:
        return []
    pts = [segs[0]["a"], segs[0]["b"]]
    segs.pop(0)
    eq = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1]) < _EPS_NO
    guard = 0
    while segs and guard < 200:
        guard += 1
        tail = pts[-1]
        i = next((k for k, s in enumerate(segs)
                  if eq(s["a"], tail) or eq(s["b"], tail)), -1)
        if i < 0:
            break
        s = segs.pop(i)
        pts.append(s["b"] if eq(s["a"], tail) else s["a"])
    if eq(pts[0], pts[-1]):
        pts.pop()
    return pts


def poly_area(poligono):
    a = 0.0
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a / 2)


def poly_perim(poligono):
    p = 0.0
    n = len(poligono)
    for i in range(n):
        a = poligono[i]
        b = poligono[(i + 1) % n]
        p += math.hypot(b[0] - a[0], b[1] - a[1])
    return p


def scan(poligono, valor, eixo):
    """Interseções do polígono com a linha eixo=valor → intervalos internos."""
    xs = []
    n = len(poligono)
    for i in range(n):
        a = poligono[i]
        b = poligono[(i + 1) % n]
        a1, b1 = (a[1], b[1]) if eixo == "z" else (a[0], b[0])
        a0, b0 = (a[0], b[0]) if eixo == "z" else (a[1], b[1])
        if (a1 <= valor < b1) or (b1 <= valor < a1):
            t = (valor - a1) / (b1 - a1)
            xs.append(a0 + t * (b0 - a0))
    xs.sort()
    iv = []
    i = 0
    while i + 1 < len(xs):
        if xs[i + 1] - xs[i] > _EPS_IV:
            iv.append((xs[i], xs[i + 1]))
        i += 2
    return iv


def cortar_span(a, b, vaos):
    """Recorta o intervalo [a,b] pelos vãos (aberturas). Porta de v7:788-798."""
    segs = [[a, b]]
    for va, vb in vaos:
        for i in range(len(segs) - 1, -1, -1):
            s, e = segs[i]
            if va <= s and vb >= e:
                segs.pop(i)
            elif va > s and vb < e:
                segs[i:i + 1] = [[s, va], [vb, e]]
            elif s < va < e:
                segs[i] = [s, va]
            elif s < vb < e:
                segs[i] = [vb, e]
    return [(s, e) for s, e in segs if e - s > _EPS_SPAN]  # v7:797 descarta <0,1m


def bbox(poligono):
    xs = [p[0] for p in poligono]
    zs = [p[1] for p in poligono]
    return {"x0": min(xs), "x1": max(xs), "z0": min(zs), "z1": max(zs)}
