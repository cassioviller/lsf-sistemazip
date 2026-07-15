# -*- coding: utf-8 -*-
"""CLI do aceite F1 (tools/carregar_orcamento_v7.py): a montagem do banco em memória
tem de seguir a MESMA ordem de db/build_db.py e do fixture `con` — schema → migrações
ordenadas → seed. O seed depende das migrações (perfil 'laminado' exige o CHECK
relaxado da 006; ON CONFLICT da 003; tabelas da 001/006): seed antes de migração
crasha com IntegrityError e o CLI documentado fica inutilizável."""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))

import carregar_orcamento_v7 as cli  # noqa: E402


def test_montar_banco_constroi_sem_excecao():
    """schema → migrações → seed: montar sem IntegrityError e com o conhecimento
    pós-migração presente (perfil 'laminado' só entra com o CHECK relaxado da 006)."""
    con = cli.montar_banco()
    try:
        laminado = con.execute(
            "SELECT COUNT(*) FROM perfil_lsf WHERE tipo = 'laminado'"
        ).fetchone()[0]
        assert laminado > 0, "seed pós-migração 006 ausente: ordem de montagem errada"
    finally:
        con.close()


def test_conferencia_roda_contra_fixture():
    """O pipeline completo do CLI (carregar → custo direto → BDI → tabela de desvio)
    reproduz o orçamento v7 da 109.1506 com desvio ~0 (aceite F1)."""
    from lsf.motores.orcamento import aplicar_bdi, custo_direto_projeto

    con = cli.montar_banco()
    try:
        fixture = cli.carregar_fixture()
        pid = cli.carregar(con, fixture)
        orc = custo_direto_projeto(con, pid)
        venda = aplicar_bdi(orc, cli.parametros_bdi_da_obra(fixture))
        linhas, (nosso, deles, desvio_total) = cli.tabela_desvio(venda, fixture)
        assert len(linhas) == len(fixture["linhas"])
        assert abs(desvio_total) <= 2.0, f"desvio total {desvio_total}% > 2%"
    finally:
        con.close()
