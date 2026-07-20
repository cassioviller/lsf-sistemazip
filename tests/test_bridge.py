"""Ponte AutoSINAPI (Rota A): idempotência e upsert de preço.
O bug original: cada reexecução duplicava composicao_item e o 'PONTE OK' passava
mais folgado quanto mais corrompido o banco (assert de limite inferior)."""
import pathlib
import sqlite3
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))

from bridge_autosinapi import criar_staging_fixture, executar_ponte  # noqa: E402
from lsf.motores.orcamento import custo_composicao  # noqa: E402


@pytest.fixture
def staging():
    st = sqlite3.connect(":memory:")
    criar_staging_fixture(st)
    yield st
    st.close()


def _custo_96359(con):
    comp = con.execute("SELECT id FROM composicao WHERE codigo_fonte = '96359'").fetchone()[0]
    return custo_composicao(con, comp, "2026-06", "SP", 0)


def test_ponte_popula_e_precifica_96359(con, staging):
    executar_ponte(staging, con)
    custo, confianca = _custo_96359(con)
    assert custo == pytest.approx(99.55, abs=0.01)
    assert confianca == "real"  # composição oficial + preços de tabela


def test_ponte_e_idempotente(con, staging):
    for _ in range(3):
        executar_ponte(staging, con)
    custo, _ = _custo_96359(con)
    assert custo == pytest.approx(99.55, abs=0.01)  # antes: 99,55 → 199,10 → 298,66
    n = con.execute(
        "SELECT COUNT(*) FROM composicao_item ci JOIN composicao c ON c.id = ci.composicao_id"
        " WHERE c.codigo_fonte = '96359'"
    ).fetchone()[0]
    assert n == 6


def test_ponte_atualiza_preco_corrigido_no_mesmo_mes(con, staging):
    executar_ponte(staging, con)
    staging.execute(
        "UPDATE precos_insumos_mensal SET preco_mediano = 31.00 WHERE insumo_codigo = 10774"
    )
    executar_ponte(staging, con)
    custo, _ = _custo_96359(con)
    assert custo == pytest.approx(99.55 + 2.10 * (31.00 - 29.80), abs=0.01)


def test_ponte_ignora_composicao_fora_do_catalogo(con, staging):
    staging.execute("INSERT INTO composicao_insumos VALUES (99999, 88278, 1.0)")
    tocadas = executar_ponte(staging, con)
    assert 99999 in tocadas  # presente no staging...
    assert con.execute(
        "SELECT COUNT(*) FROM composicao WHERE codigo_fonte = '99999'"
    ).fetchone()[0] == 0  # ...mas não inventada no catálogo


def test_ponte_filtra_por_regime(con, staging):
    staging.execute(
        "INSERT INTO precos_insumos_mensal VALUES (10774, 'SP', '2026-06-01', 'DESONERADO', 25.00)"
    )
    executar_ponte(staging, con)  # regime default NAO_DESONERADO
    custo, _ = _custo_96359(con)
    assert custo == pytest.approx(99.55, abs=0.01)  # o preço desonerado não vazou


# --- subcomposições (item_tipo='COMPOSICAO') --------------------------------
# O DataModel.md do upstream tem staging próprio p/ aninhamento e o docs/03
# prometia o mapeamento, mas a ponte só lia composicao_insumos. Composição de
# instalações/canteiro — justamente as macroetapas travadas no R7 — aninha muito.

def _custo_96114(con):
    comp = con.execute(
        "SELECT id FROM composicao WHERE codigo_fonte = '96114'").fetchone()[0]
    return custo_composicao(con, comp, "2026-06", "SP", 0)


def test_ponte_importa_subcomposicao_e_o_custo_atravessa_o_aninhamento(con, staging):
    """96114 = 1,0 × 96359. O custo do pai tem que descer até os insumos da filha."""
    executar_ponte(staging, con)
    tipos = [t for (t,) in con.execute(
        "SELECT ci.item_tipo FROM composicao_item ci JOIN composicao c"
        " ON c.id = ci.composicao_id WHERE c.codigo_fonte = '96114'")]
    assert tipos == ["COMPOSICAO"]
    custo, confianca = _custo_96114(con)
    assert custo == pytest.approx(99.55, abs=0.01)
    assert confianca == "real"


def test_reload_mensal_nao_deixa_subcomposicao_orfa(con, staging):
    """O DELETE do reload filtrava item_tipo='INSUMO': rodar 2× duplicava o
    aninhamento e inflava o custo do pai — o mesmo bug que a ponte já tinha
    corrigido para insumos."""
    for _ in range(3):
        executar_ponte(staging, con)
    n = con.execute(
        "SELECT COUNT(*) FROM composicao_item ci JOIN composicao c"
        " ON c.id = ci.composicao_id WHERE c.codigo_fonte = '96114'").fetchone()[0]
    assert n == 1
    custo, _ = _custo_96114(con)
    assert custo == pytest.approx(99.55, abs=0.01)


def test_subcomposicao_fora_do_catalogo_e_pulada_nao_inventada(con, staging):
    """Par do test_ponte_ignora_composicao_fora_do_catalogo, agora p/ COMPOSICAO."""
    staging.execute("INSERT INTO composicao_subcomposicoes VALUES (96114, 88888, 1.0)")
    executar_ponte(staging, con)
    assert con.execute(
        "SELECT COUNT(*) FROM composicao WHERE codigo_fonte = '88888'").fetchone()[0] == 0
    custo, _ = _custo_96114(con)
    assert custo == pytest.approx(99.55, abs=0.01)  # a filha inexistente não vira zero


def test_pai_aninhado_sem_preco_na_filha_e_custo_indisponivel(con, staging):
    """D4.1: ausência derruba. Pai não pode fechar com custo parcial da filha."""
    from lsf.motores.orcamento import CustoIndisponivel

    executar_ponte(staging, con)
    con.execute(
        "DELETE FROM insumo_preco WHERE insumo_id ="
        " (SELECT id FROM insumo WHERE codigo_fonte = '10774')")
    with pytest.raises(CustoIndisponivel):
        _custo_96114(con)
