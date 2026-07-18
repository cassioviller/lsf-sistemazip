"""Task 9 — `gerar_forro`: porta fiel de v7:1045-1057 (gerarPecasForro).

Borda no perímetro + perfis ao longo de z, nos três pavimentos, logo abaixo do
pé-direito (y = cota + pé-direito - 0,05).
"""
from collections import Counter


def test_forro_pecas_por_tipo_e_perfil_batem_com_o_oraculo(projeto_109_estrutura, oraculo):
    from lsf.geradores.estrutura import gerar_forro

    con, pid = projeto_109_estrutura
    pecas, _, _ = gerar_forro(con, pid)
    ref = oraculo["sistemas"]["forro"]["pecas"]
    assert (Counter((p.tipo, p.perfil) for p in pecas)
            == Counter((p["tipo"], p["perfil"]) for p in ref))


def test_forro_kg_dentro_de_10pct_do_v7(projeto_109_estrutura, oraculo):
    from lsf.geradores.estrutura import _perfil, gerar_forro

    con, pid = projeto_109_estrutura
    pecas, _, _ = gerar_forro(con, pid)
    kg = sum(p.comp * _perfil(con, p.perfil)["massa_kg_m"] for p in pecas)
    ref = oraculo["sistemas"]["forro"]["kg_liquido"]
    assert abs(kg - ref) <= 0.10 * ref


def test_forro_cobre_os_tres_pavimentos(projeto_109_estrutura, oraculo):
    """Um forro por pavimento: as cotas em y têm que ser 3 distintas."""
    from lsf.geradores.estrutura import gerar_forro

    con, pid = projeto_109_estrutura
    pecas, _, _ = gerar_forro(con, pid)
    esperado = {round(cota + oraculo["pe_direito_m"] - 0.05, 4)
                for cota in oraculo["niveis"]}
    assert {round(p.y0, 4) for p in pecas} == esperado


def test_forro_confianca_nunca_melhor_que_estimado(projeto_109_estrutura):
    from lsf.geradores.estrutura import gerar_forro

    con, pid = projeto_109_estrutura
    pecas, _, _ = gerar_forro(con, pid)
    assert pecas
    assert all(p.confianca in ("estimado", "parametrico") for p in pecas)
