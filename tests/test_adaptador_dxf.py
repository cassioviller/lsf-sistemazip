"""Adaptador DXF → planta_normalizada (Fase 5): pares paralelos viram eixos;
linha solta vira aviso, nunca parede inventada."""
import ezdxf
import pytest

from lsf.adaptadores.dxf import importar_dxf


@pytest.fixture
def projeto_com_nivel(con):
    con.execute("INSERT INTO projeto (codigo, nome, referencia, desonerado)"
                " VALUES ('DXF-TST', 'x', '2026-06', 0)")
    pid = con.execute("SELECT id FROM projeto WHERE codigo='DXF-TST'").fetchone()[0]
    nid = con.execute(
        "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m, cota_m)"
        " VALUES (?, 0, 'térreo', 3.10, 0)", (pid,)).lastrowid
    con.commit()
    return pid, nid


def _dxf(tmp_path, linhas, layer="PAREDE"):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for a, b in linhas:
        msp.add_line(a, b, dxfattribs={"layer": layer})
    caminho = tmp_path / "planta.dxf"
    doc.saveas(caminho)
    return caminho


def test_l_do_spike_1_vira_duas_paredes(con, projeto_com_nivel, tmp_path):
    """As 4 linhas do spike (parede dupla 0,14 m em L) → 2 paredes DXF/estimado
    com espessura detectada e perfil NULL (decisão pendente, não default)."""
    _, nid = projeto_com_nivel
    caminho = _dxf(tmp_path, [((0, 0), (6, 0)), ((0, 0.14), (6, 0.14)),
                              ((0, 0), (0, 4)), ((0.14, 0.14), (0.14, 4))])
    r = importar_dxf(con, nid, caminho)
    assert r["paredes_criadas"] == 2

    paredes = con.execute(
        "SELECT espessura_m, origem, confianca, perfil_codigo FROM parede"
        " WHERE nivel_id = ?", (nid,)).fetchall()
    assert len(paredes) == 2
    for esp, origem, conf, perfil in paredes:
        assert esp == pytest.approx(0.14, abs=0.01)
        assert origem == "DXF"
        assert conf == "estimado"
        assert perfil is None
    assert any("SEM perfil" in a for a in r["avisos"])


def test_linha_solta_vira_aviso_nao_parede(con, projeto_com_nivel, tmp_path):
    _, nid = projeto_com_nivel
    caminho = _dxf(tmp_path, [((0, 0), (6, 0)), ((0, 0.14), (6, 0.14)),
                              ((10, 10), (14, 10))])          # solta
    r = importar_dxf(con, nid, caminho)
    assert r["paredes_criadas"] == 1
    assert any("sem par paralelo" in a for a in r["avisos"])
    assert con.execute("SELECT COUNT(*) FROM parede WHERE nivel_id = ?",
                       (nid,)).fetchone()[0] == 1


def test_paralelas_distantes_nao_sao_par(con, projeto_com_nivel, tmp_path):
    """Duas paredes paralelas de cômodos diferentes (3 m entre elas) não podem
    virar UMA parede de 3 m de espessura."""
    _, nid = projeto_com_nivel
    caminho = _dxf(tmp_path, [((0, 0), (6, 0)), ((0, 3.0), (6, 3.0))])
    r = importar_dxf(con, nid, caminho)
    assert r["paredes_criadas"] == 0


def test_sem_layer_parede_explica_quais_layers_tem(con, projeto_com_nivel, tmp_path):
    _, nid = projeto_com_nivel
    caminho = _dxf(tmp_path, [((0, 0), (6, 0))], layer="ARQ-WALLS")
    r = importar_dxf(con, nid, caminho)
    assert r["paredes_criadas"] == 0
    assert any("ARQ-WALLS" in a for a in r["avisos"])
