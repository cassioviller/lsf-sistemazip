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


# ---------- (a) parser pt-BR + round-trip do formulário ----------

def test_parser_aceita_ambos_formatos_sem_corromper():
    """'1500.5' NÃO é 15005; '1.500' é pt-BR (a UI é pt-BR) → 1500."""
    from app.rotas.quantitativos import _numero_ptbr

    assert _numero_ptbr("1.500,5") == pytest.approx(1500.5)
    assert _numero_ptbr("1500,5") == pytest.approx(1500.5)
    assert _numero_ptbr("1,5") == pytest.approx(1.5)
    assert _numero_ptbr("1500.5") == pytest.approx(1500.5)
    assert _numero_ptbr("1.5") == pytest.approx(1.5)
    assert _numero_ptbr("1.500") == pytest.approx(1500.0)
    assert _numero_ptbr(" 31345 ") == pytest.approx(31345.0)


def test_parser_recusa_lixo_como_400():
    from fastapi import HTTPException

    from app.rotas.quantitativos import _numero_ptbr

    for lixo in ("abc", "", "1.50,0", "1,5,0", "1.5.0", "10 kg", "--3"):
        with pytest.raises(HTTPException) as erro:
            _numero_ptbr(lixo)
        assert erro.value.status_code == 400


def _valor_do_input(html: str) -> str:
    import re

    achado = re.search(r'name="quantidade" value="([^"]*)"', html)
    assert achado, html
    return achado.group(1)


def test_round_trip_salvar_sem_editar_preserva_o_valor(logado, con_app, projeto):
    """O template renderiza pt-BR; re-salvar o que está no input não multiplica por 10."""
    folha = _folha(con_app)
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": folha, "quantidade": "31345,5"},
    )
    valor_renderizado = _valor_do_input(resposta.text)
    assert "." not in valor_renderizado          # NUNCA ponto decimal no template

    logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": folha, "quantidade": valor_renderizado},
    )
    linha = con_app.execute(
        "SELECT quantidade FROM quantitativo WHERE projeto_id = ?", (projeto,)
    ).fetchone()
    assert linha["quantidade"] == pytest.approx(31345.5)


def test_inteiro_renderiza_sem_casa_morta(logado, con_app, projeto):
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": _folha(con_app), "quantidade": "31345"},
    )
    assert _valor_do_input(resposta.text) == "31345"


def test_quantidade_zero_renderiza_zero_nao_vazio(logado, con_app, projeto):
    """`or ''` esconderia o 0 legítimo; o template deve testar `is not none`."""
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": _folha(con_app), "quantidade": "0"},
    )
    assert _valor_do_input(resposta.text) == "0"

    tela = logado.get(f"/projetos/{projeto}/quantitativos")
    assert _valor_do_input(tela.text) == "0" or 'value="0"' in tela.text


# ---------- (b) origem_regra no upsert ----------

def test_editar_linha_do_gerador_limpa_origem_regra(logado, con_app, projeto):
    """Edição manual não pode manter proveniência de gerador obsoleta."""
    folha = _folha(con_app)
    con_app.execute(
        "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem,"
        " confianca, origem_regra) VALUES (?,?,100,'PARAMETRICO','estimado',"
        " 'gerador de estrutura F2.1 (porta do v7)')",
        (projeto, folha),
    )
    con_app.commit()

    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": folha, "quantidade": "200"},
    )
    assert resposta.status_code == 200
    linha = con_app.execute(
        "SELECT origem, origem_regra FROM quantitativo"
        " WHERE projeto_id = ? AND eap_item_id = ?",
        (projeto, folha),
    ).fetchone()
    assert linha["origem"] == "MANUAL"
    assert linha["origem_regra"] is None


# ---------- (c) árvore profunda: folha '03.xx.yy' visível e quantificável ----------

@pytest.fixture
def folha_profunda(con_app):
    """Agrupador '03.90' sob a macroetapa 03 e folha '03.90.01' sob ele (profundidade 3,
    formato documentado na migração 001: '03.01.02')."""
    macro = con_app.execute(
        "SELECT id FROM eap_item WHERE codigo = '03'"
    ).fetchone()["id"]
    composicao = con_app.execute(
        "SELECT composicao_id FROM eap_item WHERE codigo = '03.01'"
    ).fetchone()["composicao_id"]
    sub = con_app.execute(
        "INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap,"
        " composicao_id) VALUES ('03.90', ?, 'Subgrupo de teste', NULL, 'ESTRUTURA', NULL)",
        (macro,),
    ).lastrowid
    folha = con_app.execute(
        "INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap,"
        " composicao_id) VALUES ('03.90.01', ?, 'Folha profunda', 'kg', 'ESTRUTURA', ?)",
        (sub, composicao),
    ).lastrowid
    con_app.commit()
    return {"sub": sub, "folha": folha}


def test_folha_de_profundidade_3_aparece_na_tela(logado, con_app, projeto, folha_profunda):
    resposta = logado.get(f"/projetos/{projeto}/quantitativos")
    assert resposta.status_code == 200
    assert "03.90.01" in resposta.text                       # código completo visível
    assert f'id="item-{folha_profunda["folha"]}"' in resposta.text
    # agrupador intermediário NÃO vira linha quantificável
    assert f'id="item-{folha_profunda["sub"]}"' not in resposta.text


def test_folha_de_profundidade_3_aceita_quantitativo(logado, con_app, projeto, folha_profunda):
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": folha_profunda["folha"], "quantidade": "42,5"},
    )
    assert resposta.status_code == 200
    linha = con_app.execute(
        "SELECT quantidade, origem FROM quantitativo"
        " WHERE projeto_id = ? AND eap_item_id = ?",
        (projeto, folha_profunda["folha"]),
    ).fetchone()
    assert linha["quantidade"] == pytest.approx(42.5)
    assert linha["origem"] == "MANUAL"
