"""Lançamento MANUAL. A EAP hoje tem 5 folhas com composição — o resto é agrupador."""
import pytest


@pytest.fixture
def projeto(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "109.1506", "nome": "Edifício", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    return con_app.execute("SELECT id FROM projeto").fetchone()["id"]


def _folha(con_app, codigo="03.01"):
    return con_app.execute(
        "SELECT id FROM eap_item WHERE codigo = ?", (codigo,)
    ).fetchone()["id"]


def _agrupador(con_app, codigo="03"):
    return con_app.execute(
        "SELECT id FROM eap_item WHERE codigo = ?", (codigo,)
    ).fetchone()["id"]


def test_tela_lista_folhas_da_eap(logado, projeto):
    resposta = logado.get(f"/projetos/{projeto}/quantitativos")
    assert resposta.status_code == 200
    assert "03.01" in resposta.text          # folha com composição
    assert "Estrutura LSF" in resposta.text  # macroetapa agrupadora


def test_lancar_quantidade_grava_manual_e_real(logado, con_app, projeto):
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": _folha(con_app), "quantidade": "1500,5"},
    )
    assert resposta.status_code == 200

    linha = con_app.execute(
        "SELECT quantidade, origem, confianca FROM quantitativo WHERE projeto_id = ?",
        (projeto,),
    ).fetchone()
    assert linha["quantidade"] == pytest.approx(1500.5)   # vírgula decimal pt-BR aceita
    assert linha["origem"] == "MANUAL"
    assert linha["confianca"] == "real"


def test_relancar_o_mesmo_item_atualiza_em_vez_de_duplicar(logado, con_app, projeto):
    folha = _folha(con_app)
    logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": folha, "quantidade": "1000"},
    )
    logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": folha, "quantidade": "2000"},
    )
    linhas = con_app.execute(
        "SELECT quantidade FROM quantitativo WHERE projeto_id = ?", (projeto,)
    ).fetchall()
    assert len(linhas) == 1
    assert linhas[0]["quantidade"] == pytest.approx(2000.0)


def test_quantidade_em_agrupador_recusada_como_erro_de_formulario(logado, con_app, projeto):
    """O trigger do banco existe; a UI não pode deixá-lo virar 500."""
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": _agrupador(con_app), "quantidade": "10"},
    )
    assert resposta.status_code == 400
    assert "folha" in resposta.text.lower()


def test_quantidade_negativa_recusada(logado, con_app, projeto):
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": _folha(con_app), "quantidade": "-5"},
    )
    assert resposta.status_code == 400


def test_sem_sessao_nao_lanca(cliente, con_app):
    assert cliente.get("/projetos/1/quantitativos").status_code == 303
