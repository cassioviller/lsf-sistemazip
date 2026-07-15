import math
from lsf.geradores.geometria import (
    encadear_contorno, poly_area, poly_perim, scan, cortar_span, bbox,
)

RET = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]  # 4x3

def test_poly_area_retangulo():
    assert poly_area(RET) == 12.0

def test_poly_perim_retangulo():
    assert poly_perim(RET) == 14.0

def test_bbox_retangulo():
    assert bbox(RET) == {"x0": 0.0, "x1": 4.0, "z0": 0.0, "z1": 3.0}

def test_encadear_contorno_fecha_o_poligono():
    # segmentos fora de ordem, devem encadear no retângulo (tolerância 0,02)
    segs = [((4.0, 0.0), (4.0, 3.0)), ((0.0, 0.0), (4.0, 0.0)),
            ((0.0, 3.0), (0.0, 0.0)), ((4.0, 3.0), (0.0, 3.0))]
    poly = encadear_contorno(segs)
    assert len(poly) == 4
    assert poly_area(poly) == 12.0

def test_scan_linha_horizontal_atravessa_retangulo():
    # z=1,5 corta o retângulo em [0,4]
    assert scan(RET, 1.5, "z") == [(0.0, 4.0)]

def test_scan_vertical_atravessa_retangulo():
    assert scan(RET, 2.0, "x") == [(0.0, 3.0)]

def test_scan_forma_em_L_devolve_dois_intervalos():
    # L: recorte no canto superior direito → linha alta corta 1 vão; linha baixa corta cheio
    L = [(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (2.0, 1.0), (2.0, 3.0), (0.0, 3.0)]
    assert scan(L, 0.5, "z") == [(0.0, 4.0)]
    assert scan(L, 2.0, "z") == [(0.0, 2.0)]

def test_cortar_span_remove_vao_interno():
    assert cortar_span(0.0, 4.0, [(1.0, 2.0)]) == [(0.0, 1.0), (2.0, 4.0)]

def test_cortar_span_vao_cobre_tudo():
    assert cortar_span(0.0, 4.0, [(0.0, 4.0)]) == []

def test_cortar_span_sem_vaos_mantem():
    assert cortar_span(1.0, 3.0, []) == [(1.0, 3.0)]
