"""ACEITE PARCIAL F2.1 (paredes): porta fiel vs v7 headless, parede a parede.

Carrega as 53 paredes da 109.1506 (fixture extraída do v7) na planta_normalizada
e compara o gerador com a referência. O aceite da FASE (23.673 kg do edifício,
desvio <= 10%) só fecha quando lajes/escadas/cobertura/forro forem portados.
"""
import json
import pathlib

import pytest

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "estrutura_v7_109_1506.json"


@pytest.fixture(scope="module")
def oraculo():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def projeto_109(con, oraculo):
    """Projeto com a planta da 109.1506 carregada na planta_normalizada."""
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf, desonerado)"
        " VALUES ('109.1506-EST', 'Máximo Tintas', '2026-06', 'SP', 0)")
    pid = con.execute(
        "SELECT id FROM projeto WHERE codigo='109.1506-EST'").fetchone()[0]
    niveis = {}
    for i, cota in enumerate(oraculo["niveis"]):
        cur = con.execute(
            "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m, cota_m)"
            " VALUES (?,?,?,?,?)",
            (pid, i, f"pav-{i}", oraculo["pe_direito_m"], cota))
        niveis[i] = cur.lastrowid
    mapa = {}          # id da fixture -> parede_id no banco
    for w in oraculo["paredes"]:
        nivel_id = niveis[w["pav"]]
        no_a = con.execute(
            "INSERT INTO no_planta (nivel_id, x, y, confianca) VALUES (?,?,?,?)",
            (nivel_id, w["a"][0], w["a"][1], "real")).lastrowid
        no_b = con.execute(
            "INSERT INTO no_planta (nivel_id, x, y, confianca) VALUES (?,?,?,?)",
            (nivel_id, w["b"][0], w["b"][1], "real")).lastrowid
        parede_id = con.execute(
            "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, portante,"
            " externa, perfil_codigo, origem, confianca)"
            " VALUES (?,?,?,0.14,1,?,?,'MANUAL',?)",
            (nivel_id, no_a, no_b, w["externa"], w["perfil"],
             "estimado" if w["est"] else "real")).lastrowid
        for a in w["aberturas"]:
            con.execute(
                "INSERT INTO vao (parede_id, tipo, posicao_m, largura_m, altura_m,"
                " peitoril_m, confianca) VALUES (?,?,?,?,?,?,'real')",
                (parede_id, a["tipo"], a["posicao_m"], a["largura_m"],
                 a["altura_m"], a["peitoril_m"]))
        mapa[w["id"]] = parede_id
    con.commit()
    return {"projeto_id": pid, "mapa": mapa}


def test_cada_parede_bate_com_o_v7_em_pecas_e_kg(con, oraculo, projeto_109):
    from lsf.geradores.estrutura import gerar_parede

    divergentes = []
    for w in oraculo["paredes"]:
        r = gerar_parede(con, projeto_109["mapa"][w["id"]])
        tipos = {}
        for p in r.pecas:
            tipos[p.tipo] = tipos.get(p.tipo, 0) + 1
        kg = sum(r.kg_por_perfil.values())
        ref = w["ref"]
        if tipos != ref["pecas_por_tipo"]:
            divergentes.append(f"{w['id']}: tipos {tipos} != {ref['pecas_por_tipo']}")
        elif abs(kg - ref["kg"]) > 0.01 * ref["kg"]:
            divergentes.append(f"{w['id']}: kg {kg:.2f} != {ref['kg']:.2f}")
    assert not divergentes, "\n".join(divergentes)


def test_total_das_paredes_dentro_do_gate_de_10pct(con, oraculo, projeto_109):
    from lsf.geradores.estrutura import gerar_estrutura

    est = gerar_estrutura(con, projeto_109["projeto_id"])
    ref = oraculo["total_paredes"]
    assert est.kg_liquido == pytest.approx(ref["kg_liquido"], rel=0.10)
    assert est.kg_comprado == pytest.approx(ref["kg_comprado"], rel=0.10)


def test_paredes_estimadas_rebaixam_a_confianca(con, oraculo, projeto_109):
    from lsf.geradores.estrutura import gerar_estrutura

    est = gerar_estrutura(con, projeto_109["projeto_id"])
    assert est.confianca == "estimado"      # há paredes est=1 e regras estimado
