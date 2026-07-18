"""ACEITE PARCIAL F2.1 (paredes): porta fiel vs v7 headless, parede a parede.

Carrega as 53 paredes da 109.1506 (fixture extraída do v7) na planta_normalizada
e compara o gerador com a referência. O aceite da FASE (23.673 kg do edifício,
desvio <= 10%) só fecha quando lajes/escadas/cobertura/forro forem portados.

As fixtures `oraculo` e `projeto_109` vivem em `tests/conftest.py` (reuso pelos
testes de laje/escada/cobertura/forro).
"""
import pytest


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
