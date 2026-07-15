"""Cadastro de projeto: trava referência+UF+desonerado (D5) e a classe de solo (R3)."""


def test_lista_vazia(logado):
    resposta = logado.get("/projetos")
    assert resposta.status_code == 200
    assert "nenhum projeto" in resposta.text.lower()


def test_cadastrar_projeto(logado, con_app):
    resposta = logado.post(
        "/projetos",
        data={
            "codigo": "109.1506",
            "nome": "Edifício 109.1506",
            "cliente": "Cliente X",
            "referencia": "2026-06",
            "uf": "SP",
            "desonerado": "0",
            "sondagem_pendente": "1",
        },
    )
    assert resposta.status_code == 303

    linha = con_app.execute(
        "SELECT codigo, referencia, uf, desonerado, sondagem_pendente FROM projeto"
    ).fetchone()
    assert linha["codigo"] == "109.1506"
    assert linha["referencia"] == "2026-06"
    assert linha["uf"] == "SP"
    assert linha["desonerado"] == 0
    assert linha["sondagem_pendente"] == 1


def test_codigo_duplicado_recusado_com_mensagem(logado):
    dados = {
        "codigo": "109.1506", "nome": "A", "referencia": "2026-06",
        "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
    }
    assert logado.post("/projetos", data=dados).status_code == 303
    repetido = logado.post("/projetos", data=dados)
    assert repetido.status_code == 400
    assert "já existe" in repetido.text.lower()


def test_referencia_em_formato_errado_recusada(logado):
    resposta = logado.post(
        "/projetos",
        data={
            "codigo": "X", "nome": "X", "referencia": "junho/2026",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    assert resposta.status_code == 400
    assert "aaaa-mm" in resposta.text.lower()


def test_detalhe_mostra_sondagem_pendente(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "109.1506", "nome": "Edifício", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto").fetchone()["id"]
    resposta = logado.get(f"/projetos/{pid}")
    assert resposta.status_code == 200
    assert "sondagem" in resposta.text.lower()


def test_projeto_inexistente_404(logado):
    assert logado.get("/projetos/999").status_code == 404


def test_logout_barra_o_acesso_a_projetos(logado):
    """Fecha o par que a Task 3 não podia fechar: /projetos só existe agora."""
    assert logado.get("/projetos").status_code == 200
    logado.post("/logout")
    assert logado.get("/projetos").status_code == 303
