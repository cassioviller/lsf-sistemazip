"""A fixture do oráculo é gerada por tools/extrair_estrutura_v7.mjs — estes testes
garantem que ninguém a truncou/editou à mão."""
import json
import pathlib

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "estrutura_v7_109_1506.json"


def test_fixture_tem_53_paredes_em_3_pavimentos():
    d = json.loads(FIXTURE.read_text())
    assert len(d["paredes"]) == 53          # 19 (W_T) + 17 + 17 (W_S nos pav. 1 e 2)
    assert {p["pav"] for p in d["paredes"]} == {0, 1, 2}
    assert d["pe_direito_m"] == 3.10


def test_toda_parede_tem_referencia_e_perfil():
    d = json.loads(FIXTURE.read_text())
    for p in d["paredes"]:
        assert p["ref"]["kg"] > 0, p["id"]
        assert p["perfil"].startswith("Ue"), p["id"]
        for a in p["aberturas"]:
            assert a["tipo"] in ("JANELA", "PORTA")
            assert a["posicao_m"] >= 0


def test_total_de_paredes_positivo_e_menor_que_o_edificio():
    d = json.loads(FIXTURE.read_text())
    assert 0 < d["total_paredes"]["kg_liquido"] < 23673
    assert d["total_paredes"]["kg_comprado"] > d["total_paredes"]["kg_liquido"]
