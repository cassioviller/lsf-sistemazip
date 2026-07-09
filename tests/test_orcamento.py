"""Motor de orçamento — item 1 do contrato da Fase 1: custo_composicao recursivo."""
import pytest

from lsf.motores.orcamento import (
    CicloDeComposicao,
    CustoIndisponivel,
    PrecoAmbiguo,
    custo_composicao,
    pior_confianca,
)

# VK-C-001, ancorado no spike 6: 1,02*14,50 + 6,0*0,18 + 0,040*34,00 + 0,040*23,00
CUSTO_VK_C_001 = 18.15


def _nova_composicao(con, codigo, confianca="estimado", fonte_sigla="VEKS"):
    fonte = con.execute("SELECT id FROM fonte WHERE sigla = ?", (fonte_sigla,)).fetchone()[0]
    cur = con.execute(
        "INSERT INTO composicao (fonte_id, codigo_fonte, descricao, unidade, grupo_eap, confianca)"
        " VALUES (?, ?, ?, 'm2', 'ESTRUTURA', ?)",
        (fonte, codigo, f"teste {codigo}", confianca),
    )
    return cur.lastrowid


def _add_item(con, composicao_id, item_tipo, item_id, coeficiente):
    con.execute(
        "INSERT INTO composicao_item (composicao_id, item_tipo, item_id, coeficiente)"
        " VALUES (?, ?, ?, ?)",
        (composicao_id, item_tipo, item_id, coeficiente),
    )


def _novo_insumo(con, codigo, preco, data_base_id, confianca="real", fonte_sigla="VEKS"):
    fonte = con.execute("SELECT id FROM fonte WHERE sigla = ?", (fonte_sigla,)).fetchone()[0]
    cur = con.execute(
        "INSERT INTO insumo (fonte_id, codigo_fonte, descricao, tipo, unidade)"
        " VALUES (?, ?, ?, 'MAT', 'un')",
        (fonte, codigo, f"teste {codigo}"),
    )
    insumo_id = cur.lastrowid
    if preco is not None:
        con.execute(
            "INSERT INTO insumo_preco (insumo_id, data_base_id, preco, confianca)"
            " VALUES (?, ?, ?, ?)",
            (insumo_id, data_base_id, preco, confianca),
        )
    return insumo_id


def _nova_data_base(con, fonte_sigla, referencia, uf, desonerado=0):
    fonte = con.execute("SELECT id FROM fonte WHERE sigla = ?", (fonte_sigla,)).fetchone()[0]
    cur = con.execute(
        "INSERT INTO data_base (fonte_id, referencia, uf, desonerado) VALUES (?, ?, ?, ?)",
        (fonte, referencia, uf, desonerado),
    )
    return cur.lastrowid


# ---------- propagação de confiança (D4) ----------

def test_pior_confianca_nao_e_ordem_alfabetica():
    # 'estimado' < 'parametrico' < 'real' alfabeticamente; a pior é 'parametrico'.
    assert pior_confianca("real", "estimado") == "estimado"
    assert pior_confianca("real", "parametrico") == "parametrico"
    assert pior_confianca("estimado", "parametrico") == "parametrico"
    assert pior_confianca("real", "real") == "real"


def test_confianca_fora_do_dominio_falha():
    with pytest.raises(ValueError):
        pior_confianca("real", "chute")


# ---------- caso plano (regressão contra o spike 6) ----------

def test_composicao_plana_reproduz_spike6(con, id_de, base):
    custo, confianca = custo_composicao(con, id_de("VK-C-001"), **base)
    assert custo == pytest.approx(CUSTO_VK_C_001, abs=0.005)
    assert confianca == "estimado"


# ---------- aninhamento (o que a view não faz) ----------

def test_composicao_aninhada_um_nivel(con, id_de, base):
    painel = _nova_composicao(con, "VK-C-900")
    _add_item(con, painel, "COMPOSICAO", id_de("VK-C-001"), 41.4)  # 41,4 kg de aço por m²
    custo, _ = custo_composicao(con, painel, **base)
    assert custo == pytest.approx(41.4 * CUSTO_VK_C_001, abs=0.01)


def test_composicao_aninhada_dois_niveis(con, id_de, base):
    meio = _nova_composicao(con, "VK-C-900")
    _add_item(con, meio, "COMPOSICAO", id_de("VK-C-001"), 2.0)
    topo = _nova_composicao(con, "VK-C-901")
    _add_item(con, topo, "COMPOSICAO", meio, 3.0)
    custo, _ = custo_composicao(con, topo, **base)
    assert custo == pytest.approx(6.0 * CUSTO_VK_C_001, abs=0.01)


def test_composicao_mista_soma_insumo_e_subcomposicao(con, id_de, base):
    """A view devolveria só a parte de insumo, sem aviso. O motor soma as duas."""
    mista = _nova_composicao(con, "VK-C-900")
    _add_item(con, mista, "COMPOSICAO", id_de("VK-C-001"), 41.4)
    _add_item(con, mista, "INSUMO", id_de.insumo("VK-I-003"), 1.0)  # OSB, R$ 46,00
    custo, _ = custo_composicao(con, mista, **base)
    assert custo == pytest.approx(41.4 * CUSTO_VK_C_001 + 46.00, abs=0.01)


def test_memoizacao_nao_dedupe_usos_em_ramos_diferentes(con, id_de, base):
    """Memoização é cache de custo: a MESMA subcomposição usada em dois ramos da
    árvore é avaliada uma vez, mas contada nos dois lugares."""
    meio = _nova_composicao(con, "VK-C-900")
    _add_item(con, meio, "COMPOSICAO", id_de("VK-C-001"), 2.0)
    topo = _nova_composicao(con, "VK-C-901")
    _add_item(con, topo, "COMPOSICAO", id_de("VK-C-001"), 1.0)  # uso direto
    _add_item(con, topo, "COMPOSICAO", meio, 1.0)               # uso via VK-C-900
    custo, _ = custo_composicao(con, topo, **base)
    assert custo == pytest.approx(3.0 * CUSTO_VK_C_001, abs=0.01)


def test_item_duplicado_na_mesma_composicao_e_rejeitado_pelo_banco(con, id_de):
    """Migração 003: reinserir a mesma analítica dobrava o custo em silêncio (bug
    provado na ponte antiga); agora o UNIQUE bloqueia na escrita."""
    import sqlite3 as _sq
    topo = _nova_composicao(con, "VK-C-900")
    _add_item(con, topo, "COMPOSICAO", id_de("VK-C-001"), 1.0)
    with pytest.raises(_sq.IntegrityError):
        _add_item(con, topo, "COMPOSICAO", id_de("VK-C-001"), 2.0)


# ---------- confiança mista através do aninhamento ----------

def test_confianca_mista_real_mais_estimado_vira_estimado(con, id_de, base, db_veks):
    insumo = _novo_insumo(con, "VK-I-900", 10.00, db_veks, confianca="real")
    comp = _nova_composicao(con, "VK-C-900", confianca="real")
    _add_item(con, comp, "INSUMO", insumo, 1.0)
    assert custo_composicao(con, comp, **base)[1] == "real"

    # basta um componente 'estimado' para rebaixar o conjunto
    _add_item(con, comp, "COMPOSICAO", id_de("VK-C-001"), 1.0)
    custo, confianca = custo_composicao(con, comp, **base)
    assert confianca == "estimado"
    assert custo == pytest.approx(10.00 + CUSTO_VK_C_001, abs=0.01)


def test_parametrico_domina_estimado_atraves_do_aninhamento(con, base, db_veks):
    """A view colapsa 'parametrico' em 'estimado'; o motor propaga o pior de verdade."""
    insumo = _novo_insumo(con, "VK-I-901", 1.00, db_veks, confianca="parametrico")
    folha = _nova_composicao(con, "VK-C-900", confianca="estimado")
    _add_item(con, folha, "INSUMO", insumo, 1.0)
    topo = _nova_composicao(con, "VK-C-901", confianca="real")
    _add_item(con, topo, "COMPOSICAO", folha, 1.0)
    assert custo_composicao(con, topo, **base)[1] == "parametrico"


# ---------- resolução de data-base por fonte do insumo (D5 + D7) ----------

def test_composicao_mistura_fontes_com_data_bases_distintas(con, id_de, base, db_veks):
    """Material VEKS + mão de obra SINAPI: data-bases diferentes, mesma referência."""
    db_sinapi = _nova_data_base(con, "SINAPI", "2026-06", "SP")
    mo_sinapi = _novo_insumo(con, "88278", 26.90, db_sinapi, confianca="real", fonte_sigla="SINAPI")
    comp = _nova_composicao(con, "VK-C-900", confianca="estimado")
    _add_item(con, comp, "INSUMO", id_de.insumo("VK-I-003"), 1.0)  # VEKS, R$ 46,00
    _add_item(con, comp, "INSUMO", mo_sinapi, 2.0)  # SINAPI, 2h
    custo, confianca = custo_composicao(con, comp, **base)
    assert custo == pytest.approx(46.00 + 2 * 26.90, abs=0.01)
    assert confianca == "estimado"  # a composição é 'estimado', mesmo com insumo 'real'


def test_base_da_uf_ganha_da_base_nacional(con, base):
    db_br = _nova_data_base(con, "SINAPI", "2026-06", None)
    db_sp = _nova_data_base(con, "SINAPI", "2026-06", "SP")
    insumo = _novo_insumo(con, "88278", 20.00, db_br, fonte_sigla="SINAPI")
    con.execute(
        "INSERT INTO insumo_preco (insumo_id, data_base_id, preco, confianca)"
        " VALUES (?, ?, 26.90, 'real')",
        (insumo, db_sp),
    )
    comp = _nova_composicao(con, "VK-C-900", confianca="real")
    _add_item(con, comp, "INSUMO", insumo, 1.0)
    custo, _ = custo_composicao(con, comp, **base)
    assert custo == pytest.approx(26.90, abs=0.01)  # SP, não a nacional


def test_base_nacional_serve_quando_nao_ha_base_da_uf(con, base):
    db_br = _nova_data_base(con, "SINAPI", "2026-06", None)
    insumo = _novo_insumo(con, "88278", 20.00, db_br, fonte_sigla="SINAPI")
    comp = _nova_composicao(con, "VK-C-900", confianca="real")
    _add_item(con, comp, "INSUMO", insumo, 1.0)
    assert custo_composicao(con, comp, **base)[0] == pytest.approx(20.00, abs=0.01)


def test_duas_bases_nacionais_candidatas_e_ambiguo(con, base):
    """UNIQUE(fonte,referencia,uf,desonerado) não pega uf NULL no SQLite: o motor pega."""
    db_a = _nova_data_base(con, "SINAPI", "2026-06", None)
    db_b = _nova_data_base(con, "SINAPI", "2026-06", None)
    insumo = _novo_insumo(con, "88278", 20.00, db_a, fonte_sigla="SINAPI")
    con.execute(
        "INSERT INTO insumo_preco (insumo_id, data_base_id, preco, confianca)"
        " VALUES (?, ?, 30.00, 'real')",
        (insumo, db_b),
    )
    comp = _nova_composicao(con, "VK-C-900", confianca="real")
    _add_item(con, comp, "INSUMO", insumo, 1.0)
    with pytest.raises(PrecoAmbiguo, match="88278"):
        custo_composicao(con, comp, **base)


def test_desonerado_separa_precos(con, base):
    db_nao = _nova_data_base(con, "SINAPI", "2026-06", "SP", desonerado=0)
    db_des = _nova_data_base(con, "SINAPI", "2026-06", "SP", desonerado=1)
    insumo = _novo_insumo(con, "88278", 26.90, db_nao, fonte_sigla="SINAPI")
    con.execute(
        "INSERT INTO insumo_preco (insumo_id, data_base_id, preco, confianca)"
        " VALUES (?, ?, 22.10, 'real')",
        (insumo, db_des),
    )
    comp = _nova_composicao(con, "VK-C-900", confianca="real")
    _add_item(con, comp, "INSUMO", insumo, 1.0)
    assert custo_composicao(con, comp, **base)[0] == pytest.approx(26.90, abs=0.01)
    desonerada = {**base, "desonerado": 1}
    assert custo_composicao(con, comp, **desonerada)[0] == pytest.approx(22.10, abs=0.01)


# ---------- dado ausente é erro, não custo parcial ----------

def test_composicao_sem_analitica_falha(con, id_de, base):
    # 96359 está cadastrada mas sua analítica só chega pela ponte AutoSINAPI.
    with pytest.raises(CustoIndisponivel, match="96359"):
        custo_composicao(con, id_de("96359"), **base)


def test_insumo_sem_preco_falha(con, id_de, base, db_veks):
    sem_preco = _novo_insumo(con, "VK-I-902", None, db_veks)
    comp = _nova_composicao(con, "VK-C-900")
    _add_item(con, comp, "INSUMO", id_de.insumo("VK-I-003"), 1.0)
    _add_item(con, comp, "INSUMO", sem_preco, 10.0)
    with pytest.raises(CustoIndisponivel, match="VK-I-902"):
        custo_composicao(con, comp, **base)


def test_insumo_inexistente_falha_com_id(con, base):
    comp = _nova_composicao(con, "VK-C-900")
    _add_item(con, comp, "INSUMO", 999999, 1.0)  # item_id é FK lógica: nada impede
    with pytest.raises(CustoIndisponivel, match="inexistente"):
        custo_composicao(con, comp, **base)


def test_composicao_inexistente_falha(con, base):
    with pytest.raises(CustoIndisponivel):
        custo_composicao(con, 999999, **base)


def test_referencia_sem_preco_falha_em_vez_de_ignorar(con, id_de, base):
    futura = {**base, "referencia": "2027-01"}
    with pytest.raises(CustoIndisponivel, match="sem preço"):
        custo_composicao(con, id_de("VK-C-001"), **futura)


# ---------- ciclo ----------

def test_ciclo_direto(con, base):
    a = _nova_composicao(con, "VK-C-900")
    _add_item(con, a, "COMPOSICAO", a, 1.0)
    with pytest.raises(CicloDeComposicao):
        custo_composicao(con, a, **base)


def test_ciclo_indireto(con, base):
    a = _nova_composicao(con, "VK-C-900")
    b = _nova_composicao(con, "VK-C-901")
    _add_item(con, a, "COMPOSICAO", b, 1.0)
    _add_item(con, b, "COMPOSICAO", a, 1.0)
    with pytest.raises(CicloDeComposicao):
        custo_composicao(con, a, **base)


# ---------- coerência com a view no único caso que ela cobre ----------

def test_motor_bate_com_a_view_em_composicao_plana(con, id_de, base):
    for codigo in ("VK-C-001", "VK-C-002", "VK-C-003", "VK-C-004"):
        cid = id_de(codigo)
        da_view = con.execute(
            "SELECT custo_unitario FROM vw_custo_composicao WHERE composicao_id = ?", (cid,)
        ).fetchone()[0]
        do_motor, _ = custo_composicao(con, cid, **base)
        assert do_motor == pytest.approx(da_view, abs=0.005), codigo
