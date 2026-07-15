"""Tela de orçamento: KPIs, faixas ±% (D4), pendências (D4.1), gate R7 visível."""
import pytest


@pytest.fixture
def projeto_com_quantitativo(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "109.1506", "nome": "Edifício", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto").fetchone()["id"]
    folha = con_app.execute(
        "SELECT id FROM eap_item WHERE codigo = '03.01'"
    ).fetchone()["id"]
    logado.post(
        f"/projetos/{pid}/quantitativos",
        data={"eap_item_id": folha, "quantidade": "1500"},
    )
    return pid


def test_orcamento_mostra_total_com_bdi(logado, projeto_com_quantitativo):
    resposta = logado.get(f"/projetos/{projeto_com_quantitativo}/orcamento")
    assert resposta.status_code == 200
    assert "BDI" in resposta.text
    assert "27,79" in resposta.text or "27.79" in resposta.text


def test_orcamento_mostra_macroetapas_zeradas(logado, projeto_com_quantitativo):
    """Só a 03 tem quantitativo; as outras 7 estão vazias — o gate tem que aparecer."""
    resposta = logado.get(f"/projetos/{projeto_com_quantitativo}/orcamento")
    texto = resposta.text.lower()
    assert "zerada" in texto or "sem quantitativo" in texto
    assert "01" in resposta.text and "02" in resposta.text


def test_servico_marca_pode_publicar_falso_com_macroetapa_zerada(con_app, projeto_com_quantitativo):
    from app.servicos.orcamento import montar

    visao = montar(con_app, projeto_com_quantitativo)
    assert visao.pode_publicar is False
    assert len(visao.macroetapas_zeradas) == 7


def test_linha_estimada_ganha_faixa_e_real_nao(con_app, projeto_com_quantitativo):
    from app.servicos.orcamento import montar

    visao = montar(con_app, projeto_com_quantitativo, faixa_pct=0.10)
    linha = visao.linhas[0]
    if linha["confianca"] in ("estimado", "parametrico"):
        assert linha["preco_min"] == pytest.approx(linha["preco_venda"] * 0.90)
        assert linha["preco_max"] == pytest.approx(linha["preco_venda"] * 1.10)
    else:
        assert linha["preco_min"] is None


def test_projeto_sem_quantitativo_nao_fecha_o_total(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "VAZIO", "nome": "Vazio", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto WHERE codigo='VAZIO'").fetchone()["id"]

    from app.servicos.orcamento import montar

    visao = montar(con_app, pid)
    assert visao.venda.preco_total is None      # D4.1: não fecha com pendência
    assert visao.pode_publicar is False
    assert "sem nenhum quantitativo" in " ".join(visao.pendencias)
