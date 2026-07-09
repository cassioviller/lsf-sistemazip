"""Item 3 do contrato da Fase 1: custo_direto_projeto — agregação pela EAP (D1/D2/D4/D5)."""
import pytest

from lsf.motores.orcamento import custo_direto_projeto

# Custos unitários exatos do seed (conferidos à mão nos testes do custo_composicao):
CU = {
    "03.01": 18.15,     # VK-C-001  kg
    "04.01": 63.72,     # VK-C-002  m2
    "04.02": 8.53,      # VK-C-003  m2
    "04.03": 84.09,     # VK-C-004  m2
    "06.01": 99.5517,   # SINAPI 96359 m2 (fixture da ponte: 0.606*26.90 + 0.303*20.10
                        #   + 2.10*29.80 + 30*0.31 + 0.90*4.60 + 3.00*0.38)
}
QTD = {"03.01": 1500.0, "04.01": 120.0, "04.02": 120.0, "04.03": 80.0, "06.01": 200.0}
TOTAL_MANUAL = sum(CU[k] * QTD[k] for k in CU)  # 62.532,54


def _analitica_96359(con):
    """96359 vem do seed sem analítica; aqui entra o que a ponte AutoSINAPI popularia."""
    sinapi = con.execute("SELECT id FROM fonte WHERE sigla = 'SINAPI'").fetchone()[0]
    db = con.execute(
        "INSERT INTO data_base (fonte_id, referencia, uf, desonerado) VALUES (?, '2026-06', 'SP', 0)",
        (sinapi,),
    ).lastrowid
    comp = con.execute("SELECT id FROM composicao WHERE codigo_fonte = '96359'").fetchone()[0]
    itens = [  # mesmos códigos/preços/coeficientes de tools/bridge_autosinapi.py
        ("88278", "MONTADOR DE ESTRUTURA METÁLICA", "MO", "H", 26.90, 0.606),
        ("88316", "SERVENTE", "MO", "H", 20.10, 0.303),
        ("10774", "CHAPA DE GESSO DRYWALL ST 12,5MM", "MAT", "M2", 29.80, 2.10),
        ("39443", "PARAFUSO DRYWALL LB 4,2X13MM", "MAT", "UN", 0.31, 30.0),
        ("20111", "MASSA DE REJUNTE PARA DRYWALL", "MAT", "KG", 4.60, 0.90),
        ("37595", "FITA PAPEL MICROPERFURADA", "MAT", "M", 0.38, 3.00),
    ]
    for codigo, desc, tipo, un, preco, coef in itens:
        iid = con.execute(
            "INSERT INTO insumo (fonte_id, codigo_fonte, descricao, tipo, unidade)"
            " VALUES (?, ?, ?, ?, ?)",
            (sinapi, codigo, desc, tipo, un),
        ).lastrowid
        con.execute(
            "INSERT INTO insumo_preco (insumo_id, data_base_id, preco, confianca)"
            " VALUES (?, ?, ?, 'real')",
            (iid, db, preco),
        )
        con.execute(
            "INSERT INTO composicao_item (composicao_id, item_tipo, item_id, coeficiente)"
            " VALUES (?, 'INSUMO', ?, ?)",
            (comp, iid, coef),
        )


@pytest.fixture
def projeto(con):
    """Projeto-fixture: as 4 composições VK + a SINAPI 96359, quantitativos MANUAL."""
    _analitica_96359(con)
    pid = con.execute(
        "INSERT INTO projeto (codigo, nome, cliente, referencia, uf, desonerado)"
        " VALUES ('109.1506', 'Máximo Tintas', 'Máximo', '2026-06', 'SP', 0)"
    ).lastrowid
    confianca_qtd = {"04.03": "estimado"}  # quantidade da cimentícia ainda não medida
    for codigo, qtd in QTD.items():
        eap = con.execute("SELECT id FROM eap_item WHERE codigo = ?", (codigo,)).fetchone()[0]
        con.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem, confianca,"
            " origem_regra) VALUES (?, ?, ?, 'MANUAL', ?, 'orçamento manual de teste')",
            (pid, eap, qtd, confianca_qtd.get(codigo, "real")),
        )
    return pid


# ---------- (a) total bate com a soma manual ----------

def test_total_bate_com_soma_manual(con, projeto):
    orc = custo_direto_projeto(con, projeto)
    assert orc.total == pytest.approx(TOTAL_MANUAL, abs=0.01)
    assert not orc.pendencias
    assert len(orc.linhas) == 5


def test_cada_linha_e_quantidade_vezes_unitario(con, projeto):
    orc = custo_direto_projeto(con, projeto)
    for linha in orc.linhas:
        assert linha.custo_unitario == pytest.approx(CU[linha.eap_codigo], abs=0.005)
        assert linha.custo_total == pytest.approx(
            QTD[linha.eap_codigo] * CU[linha.eap_codigo], abs=0.01
        )
        assert linha.origem == "MANUAL"


# ---------- (b) confiança da linha = pior entre quantitativo e composição (D4) ----------

def test_composicao_estimada_rebaixa_linha_mesmo_com_quantitativo_real(con, projeto):
    orc = custo_direto_projeto(con, projeto)
    por_codigo = {l.eap_codigo: l for l in orc.linhas}
    # 03.01: quantitativo 'real', composição VK-C-001 'estimado' -> linha 'estimado'
    assert por_codigo["03.01"].confianca == "estimado"
    # 06.01: quantitativo 'real', SINAPI 96359 'real' com preços 'real' -> linha 'real'
    assert por_codigo["06.01"].confianca == "real"
    # 04.03: o próprio quantitativo é 'estimado'
    assert por_codigo["04.03"].confianca == "estimado"
    # geral: pior das linhas
    assert orc.confianca == "estimado"


def test_quantitativo_parametrico_rebaixa_linha_com_preco_real(con, projeto):
    eap = con.execute("SELECT id FROM eap_item WHERE codigo = '06.01'").fetchone()[0]
    con.execute(
        "UPDATE quantitativo SET confianca = 'parametrico' WHERE projeto_id = ? AND eap_item_id = ?",
        (projeto, eap),
    )
    orc = custo_direto_projeto(con, projeto)
    linha = next(l for l in orc.linhas if l.eap_codigo == "06.01")
    assert linha.confianca == "parametrico"
    assert orc.confianca == "parametrico"


# ---------- (c) subtotais por macroetapa fecham no total ----------

def test_subtotais_fecham_no_total(con, projeto):
    orc = custo_direto_projeto(con, projeto)
    soma = sum(s.custo for s in orc.subtotais if s.custo is not None)
    assert soma == pytest.approx(orc.total, abs=0.01)


def test_subtotal_por_macroetapa(con, projeto):
    orc = custo_direto_projeto(con, projeto)
    por_codigo = {s.eap_codigo: s for s in orc.subtotais}
    assert por_codigo["03"].custo == pytest.approx(1500 * CU["03.01"], abs=0.01)
    esperado_04 = 120 * CU["04.01"] + 120 * CU["04.02"] + 80 * CU["04.03"]
    assert por_codigo["04"].custo == pytest.approx(esperado_04, abs=0.01)
    assert por_codigo["06"].custo == pytest.approx(200 * CU["06.01"], abs=0.01)
    assert por_codigo["06"].confianca == "real"
    assert por_codigo["04"].confianca == "estimado"


def test_macroetapas_sem_quantitativo_sao_apontadas(con, projeto):
    """Insumo do gate R7: turn-key com macroetapa zerada é escopo vazado."""
    orc = custo_direto_projeto(con, projeto)
    assert orc.macroetapas_zeradas == ["01", "02", "05", "07", "08"]
    zeradas = [s for s in orc.subtotais if s.zerada]
    assert all(s.custo is None for s in zeradas)


# ---------- pendência: dado faltando não vira zero ----------

def test_linha_sem_preco_vira_pendencia_e_total_nao_fecha(con, projeto):
    # some com a analítica da 96359 (como se a ponte nunca tivesse rodado)
    comp = con.execute("SELECT id FROM composicao WHERE codigo_fonte = '96359'").fetchone()[0]
    con.execute("DELETE FROM composicao_item WHERE composicao_id = ?", (comp,))
    orc = custo_direto_projeto(con, projeto)
    linha = next(l for l in orc.linhas if l.eap_codigo == "06.01")
    assert linha.custo_total is None
    assert "96359" in linha.pendencia
    assert orc.total is None                      # o orçamento se recusa a fechar
    assert any("06.01" in p for p in orc.pendencias)
    por_codigo = {s.eap_codigo: s for s in orc.subtotais}
    assert por_codigo["06"].custo is None         # subtotal também não fecha
    assert por_codigo["03"].custo is not None     # as demais macroetapas seguem íntegras


def test_projeto_sem_quantitativos(con):
    pid = con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf) VALUES ('X', 'vazio', '2026-06', 'SP')"
    ).lastrowid
    orc = custo_direto_projeto(con, pid)
    assert orc.total is None
    assert orc.pendencias == ["projeto sem nenhum quantitativo"]
    assert len(orc.macroetapas_zeradas) == 8


def test_projeto_inexistente_falha(con):
    from lsf.motores.orcamento import OrcamentoError
    with pytest.raises(OrcamentoError, match="não existe"):
        custo_direto_projeto(con, 999999)
