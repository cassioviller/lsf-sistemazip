"""Autenticação da área interna. O app está exposto na internet para servir o link
do cliente — área interna sem login seria porta aberta."""


def test_hash_de_senha_nao_guarda_a_senha():
    from app.auth import hash_senha, senha_confere

    h = hash_senha("segredo123")
    assert "segredo123" not in h
    assert h.startswith("scrypt$")
    assert senha_confere("segredo123", h) is True
    assert senha_confere("errada", h) is False


def test_hash_tem_sal_diferente_a_cada_chamada():
    from app.auth import hash_senha

    assert hash_senha("igual") != hash_senha("igual")


def test_rota_interna_sem_sessao_redireciona_ao_login(cliente):
    resposta = cliente.get("/projetos")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_rota_interna_sem_sessao_via_htmx_devolve_hx_redirect(cliente):
    """XHR do htmx segue 303 e faria swap da página de login dentro do <tr>.
    Com HX-Request presente, a resposta carrega HX-Redirect e corpo sem o form:
    o htmx vendored processa HX-Redirect antes de olhar o status (401 ok)."""
    resposta = cliente.post("/projetos", headers={"HX-Request": "true"})
    assert resposta.status_code == 401
    assert resposta.headers["hx-redirect"] == "/login"
    assert "location" not in resposta.headers
    assert "<form" not in resposta.text


def test_rota_interna_sem_sessao_sem_htmx_segue_303(cliente):
    resposta = cliente.post("/projetos", headers={})
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"
    assert "hx-redirect" not in resposta.headers


def test_login_com_senha_certa_abre_sessao(cliente, usuario):
    resposta = cliente.post(
        "/login", data={"email": usuario["email"], "senha": usuario["senha"]}
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/projetos"


def test_login_com_senha_errada_recusa(cliente, usuario):
    resposta = cliente.post(
        "/login", data={"email": usuario["email"], "senha": "nao-e-essa"}
    )
    assert resposta.status_code == 401
    assert "senha" in resposta.text.lower() or "inválid" in resposta.text.lower()


def test_usuario_inativo_nao_entra(cliente, usuario, con_app):
    con_app.execute("UPDATE usuario SET ativo = 0 WHERE id = ?", (usuario["id"],))
    con_app.commit()
    resposta = cliente.post(
        "/login", data={"email": usuario["email"], "senha": usuario["senha"]}
    )
    assert resposta.status_code == 401


def test_logout_limpa_a_sessao(logado):
    """Não usa /projetos (que só existe na Task 4): checa a sessão pela rota protegida
    mais simples que já existe — se ainda houvesse sessão, /login redirecionaria."""
    logado.post("/logout")
    assert logado.get("/login").status_code == 200
