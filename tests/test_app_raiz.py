"""A raiz `/` é o que o webview do Replit abre. Sem ela o preview mostrava 404 com
o app perfeitamente no ar — as rotas começam todas em /login, /projetos, /p/<token>."""


def test_raiz_leva_ao_login_quando_nao_ha_sessao(cliente):
    """O caminho exato do preview num navegador novo: GET / tem que terminar na tela
    de login, não num 404. Segue os redirects como o navegador segue."""
    resposta = cliente.get("/", follow_redirects=True)
    assert resposta.status_code == 200
    assert str(resposta.url).endswith("/login")


def test_raiz_leva_aos_projetos_quando_ha_sessao(logado):
    """Com sessão, a raiz não pode despejar o usuário no login de novo."""
    resposta = logado.get("/", follow_redirects=True)
    assert resposta.status_code == 200
    assert str(resposta.url).endswith("/projetos")


def test_raiz_nao_e_404(cliente):
    """O sintoma que iniciou o diagnóstico, travado: / respondia 404 enquanto
    /login respondia 200 — app no ar, preview vazio."""
    resposta = cliente.get("/", follow_redirects=False)
    assert resposta.status_code != 404
    assert resposta.status_code in (302, 303, 307)
