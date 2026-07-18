"""Entrada MANUAL da planta (Fase 2, item 2): níveis → paredes → vãos, e o botão
que dispara a cadeia paramétrica (derivar). O app é CRUD + chamada de motor:
número que não veio de motor é bug de arquitetura (CLAUDE.md)."""
import pytest


@pytest.fixture
def projeto(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "CAIXA", "nome": "Caixa 6x4", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    return con_app.execute("SELECT id FROM projeto").fetchone()["id"]


def _criar_nivel(logado, pid, indice=0, pe_direito="3,10"):
    return logado.post(
        f"/projetos/{pid}/planta/niveis",
        data={"indice": str(indice), "nome": f"pav-{indice}",
              "pe_direito": pe_direito, "cota": "0"},
    )


def _criar_parede(logado, pid, nivel_id, x0, y0, x1, y1, externa="1"):
    return logado.post(
        f"/projetos/{pid}/planta/paredes",
        data={"nivel_id": str(nivel_id), "x0": x0, "y0": y0, "x1": x1, "y1": y1,
              "perfil_codigo": "Ue90#0.95", "externa": externa},
    )


def test_tela_da_planta_existe_e_oferece_nivel(logado, projeto):
    resposta = logado.get(f"/projetos/{projeto}/planta")
    assert resposta.status_code == 200
    assert "nível" in resposta.text.lower()


def test_criar_nivel_parede_e_vao(logado, con_app, projeto):
    assert _criar_nivel(logado, projeto).status_code == 303
    nivel = con_app.execute("SELECT * FROM nivel WHERE projeto_id = ?",
                            (projeto,)).fetchone()
    assert nivel["pe_direito_m"] == pytest.approx(3.10)

    r = _criar_parede(logado, projeto, nivel["id"], "0", "0", "6", "0")
    assert r.status_code == 303
    parede = con_app.execute("SELECT * FROM parede").fetchone()
    assert parede["origem"] == "MANUAL"
    assert parede["externa"] == 1
    assert parede["perfil_codigo"] == "Ue90#0.95"

    r = logado.post(
        f"/projetos/{projeto}/planta/paredes/{parede['id']}/vaos",
        data={"tipo": "JANELA", "posicao": "2,0", "largura": "1,2",
              "altura": "1,2", "peitoril": ""},
    )
    assert r.status_code == 303
    vao = con_app.execute("SELECT * FROM vao").fetchone()
    assert vao["peitoril_m"] is None       # em branco = não informado (migração 007)
    assert vao["largura_m"] == pytest.approx(1.2)

    pagina = logado.get(f"/projetos/{projeto}/planta").text
    assert "JANELA" in pagina and "Ue90#0.95" in pagina


def test_nos_de_canto_sao_compartilhados(logado, con_app, projeto):
    """Cantos são NÓS (grafo da migração 004): duas paredes que se encontram em
    (6,0) têm que apontar para o MESMO nó, senão a planta vira sopa de segmentos."""
    _criar_nivel(logado, projeto)
    nid = con_app.execute("SELECT id FROM nivel").fetchone()["id"]
    _criar_parede(logado, projeto, nid, "0", "0", "6", "0")
    _criar_parede(logado, projeto, nid, "6", "0", "6", "4")
    assert con_app.execute("SELECT COUNT(*) FROM no_planta").fetchone()[0] == 3


def test_parede_de_nivel_de_outro_projeto_e_recusada(logado, con_app, projeto):
    logado.post(
        "/projetos",
        data={"codigo": "OUTRO", "nome": "Outro", "referencia": "2026-06",
              "uf": "SP", "desonerado": "0", "sondagem_pendente": "1"})
    outro = con_app.execute("SELECT id FROM projeto WHERE codigo='OUTRO'"
                            ).fetchone()["id"]
    _criar_nivel(logado, outro)
    nid_alheio = con_app.execute("SELECT id FROM nivel").fetchone()["id"]

    r = _criar_parede(logado, projeto, nid_alheio, "0", "0", "6", "0")
    assert r.status_code == 404
    assert con_app.execute("SELECT COUNT(*) FROM parede").fetchone()[0] == 0


def test_numero_invalido_e_400_nao_500(logado, con_app, projeto):
    _criar_nivel(logado, projeto)
    nid = con_app.execute("SELECT id FROM nivel").fetchone()["id"]
    r = _criar_parede(logado, projeto, nid, "abc", "0", "6", "0")
    assert r.status_code == 400
    assert con_app.execute("SELECT COUNT(*) FROM parede").fetchone()[0] == 0


def test_excluir_parede_leva_vaos_e_nos_orfaos(logado, con_app, projeto):
    _criar_nivel(logado, projeto)
    nid = con_app.execute("SELECT id FROM nivel").fetchone()["id"]
    _criar_parede(logado, projeto, nid, "0", "0", "6", "0")
    _criar_parede(logado, projeto, nid, "6", "0", "6", "4")
    p1 = con_app.execute("SELECT id FROM parede ORDER BY id").fetchone()["id"]
    logado.post(f"/projetos/{projeto}/planta/paredes/{p1}/vaos",
                data={"tipo": "PORTA", "posicao": "2,0", "largura": "0,9",
                      "altura": "2,1", "peitoril": ""})

    r = logado.post(f"/projetos/{projeto}/planta/paredes/{p1}/excluir")
    assert r.status_code == 303
    assert con_app.execute("SELECT COUNT(*) FROM parede").fetchone()[0] == 1
    assert con_app.execute("SELECT COUNT(*) FROM vao").fetchone()[0] == 0
    # o nó (0,0) ficou órfão e saiu; (6,0) segue em uso pela outra parede
    assert con_app.execute("SELECT COUNT(*) FROM no_planta").fetchone()[0] == 2


def test_derivar_sem_planta_e_409_com_mensagem(logado, projeto):
    r = logado.post(f"/projetos/{projeto}/planta/derivar")
    assert r.status_code == 409
    assert "parede" in r.text.lower()


def test_derivar_grava_parametrico_e_mostra_resultado(logado, con_app, projeto):
    """A caixa 6×4 inteira pelo app: paredes MANUAL → derivar → kg PARAMETRICO na
    folha 03.01 + pendências do motor de cargas na tabela (gate as vê). Sistema
    horizontal ausente (laje/cobertura) é escopo → alerta, não exceção."""
    _criar_nivel(logado, projeto)
    nid = con_app.execute("SELECT id FROM nivel").fetchone()["id"]
    for x0, y0, x1, y1 in [(0, 0, 6, 0), (6, 0, 6, 4), (6, 4, 0, 4), (0, 4, 0, 0)]:
        _criar_parede(logado, projeto, nid, str(x0), str(y0), str(x1), str(y1))

    r = logado.post(f"/projetos/{projeto}/planta/derivar")
    assert r.status_code == 200

    linha = con_app.execute(
        "SELECT q.quantidade, q.origem, q.confianca FROM quantitativo q"
        " JOIN eap_item e ON e.id = q.eap_item_id"
        " WHERE q.projeto_id = ? AND e.codigo = '03.01'", (projeto,)).fetchone()
    assert linha is not None
    assert linha["origem"] == "PARAMETRICO"
    assert linha["quantidade"] > 0
    assert "kg" in r.text.lower()


def test_derivar_nao_sobrescreve_manual(logado, con_app, projeto):
    """D2 + guarda do derivar_quantitativos: linha MANUAL é dado melhor que regra
    — a derivação preserva e a tela avisa, em vez de trocar por baixo."""
    _criar_nivel(logado, projeto)
    nid = con_app.execute("SELECT id FROM nivel").fetchone()["id"]
    for x0, y0, x1, y1 in [(0, 0, 6, 0), (6, 0, 6, 4), (6, 4, 0, 4), (0, 4, 0, 0)]:
        _criar_parede(logado, projeto, nid, str(x0), str(y0), str(x1), str(y1))
    folha = con_app.execute("SELECT id FROM eap_item WHERE codigo='03.01'"
                            ).fetchone()["id"]
    logado.post(f"/projetos/{projeto}/quantitativos",
                data={"eap_item_id": folha, "quantidade": "31345"})

    r = logado.post(f"/projetos/{projeto}/planta/derivar")
    assert r.status_code == 200
    linha = con_app.execute(
        "SELECT origem, quantidade FROM quantitativo WHERE projeto_id = ?"
        " AND eap_item_id = ?", (projeto, folha)).fetchone()
    assert linha["origem"] == "MANUAL"
    assert linha["quantidade"] == pytest.approx(31345)
    assert "preservad" in r.text.lower()
