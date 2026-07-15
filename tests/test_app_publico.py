"""A página do cliente: read-only, congelada, com os gates à vista."""


def test_token_invalido_da_404(anonimo):
    assert anonimo.get("/p/nao-existe-esse-token").status_code == 404


def test_pagina_publica_abre_sem_login(anonimo, logado, con_app, projeto_completo):
    """O cliente final não tem login. Se este teste exigir sessão, o produto não existe."""
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    resposta = anonimo.get(f"/p/{token}")
    assert resposta.status_code == 200
    assert "109.1506" in resposta.text


def test_pagina_publica_traz_o_disclaimer_de_pre_dimensionamento(
    anonimo, logado, con_app, projeto_completo
):
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    texto = anonimo.get(f"/p/{token}").text.lower()
    assert "pré-dimensionamento" in texto or "pre-dimensionamento" in texto
    assert "não substitui projeto" in texto or "nao substitui projeto" in texto


def test_pagina_publica_nao_e_indexavel(anonimo, logado, con_app, projeto_completo):
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    resposta = anonimo.get(f"/p/{token}")
    assert "noindex" in resposta.headers.get("x-robots-tag", "").lower()


def test_proposta_revogada_diz_que_foi_superada(anonimo, logado, con_app, projeto_completo):
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token_v1 = con_app.execute(
        "SELECT token FROM proposta WHERE versao = 1"
    ).fetchone()["token"]
    logado.post(f"/projetos/{projeto_completo}/publicar")   # v2 revoga a v1

    resposta = anonimo.get(f"/p/{token_v1}")
    assert resposta.status_code == 410
    assert "superada" in resposta.text.lower()
    # E não pode exibir o preço obsoleto como se fosse vigente:
    assert "R$" not in resposta.text


def test_sondagem_pendente_aparece_como_gate_aberto(
    anonimo, logado, con_app, projeto_completo
):
    con_app.execute(
        "UPDATE projeto SET sondagem_pendente = 1 WHERE id = ?", (projeto_completo,)
    )
    con_app.commit()
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    texto = anonimo.get(f"/p/{token}").text.lower()
    assert "sondagem" in texto


def test_o_que_o_cliente_ve_nao_muda_quando_o_preco_muda(
    anonimo, logado, con_app, projeto_completo
):
    """O teste que dá sentido a tudo (spec §12.7): a página que o cliente tem em mãos
    é a mesma depois que o mundo mudou. Se esta rota algum dia recalcular, ele quebra."""
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    antes = anonimo.get(f"/p/{token}").text

    con_app.execute("UPDATE insumo_preco SET preco = preco * 2")
    con_app.commit()

    assert anonimo.get(f"/p/{token}").text == antes
