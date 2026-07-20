"""Publicação: os gates recusam, e o que foi publicado NÃO muda mais."""
import pytest


def test_publicar_com_macroetapa_zerada_e_recusado(logado, con_app):
    """Gate R7: escopo vazado em preço fechado é prejuízo. Bloqueia, não avisa."""
    logado.post(
        "/projetos",
        data={
            "codigo": "PARCIAL", "nome": "Parcial", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto WHERE codigo='PARCIAL'").fetchone()["id"]
    folha = con_app.execute("SELECT id FROM eap_item WHERE codigo='03.01'").fetchone()["id"]
    logado.post(f"/projetos/{pid}/quantitativos",
                data={"eap_item_id": folha, "quantidade": "100"})

    resposta = logado.post(f"/projetos/{pid}/publicar")
    assert resposta.status_code == 409
    assert "macroetapa" in resposta.text.lower()
    assert con_app.execute("SELECT COUNT(*) FROM proposta").fetchone()[0] == 0


def test_publicar_sem_quantitativo_nenhum_e_recusado(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "VAZIO", "nome": "Vazio", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto WHERE codigo='VAZIO'").fetchone()["id"]
    resposta = logado.post(f"/projetos/{pid}/publicar")
    assert resposta.status_code == 409
    assert con_app.execute("SELECT COUNT(*) FROM proposta").fetchone()[0] == 0


def test_publicar_com_pendencia_estrutural_e_recusado(logado, con_app, projeto_completo):
    """O motor disse que a solução por trás do kg não fecha (vão que reprova, furo
    em viga, peça fora do envelope). O preço existe; a estrutura, não.

    Não é preciosismo: na 109 o gerador exige viga laminada 1VG + pilares 1AL nas
    duas lajes, a obra foi construída com eles, e o orçamento de referência não tem
    linha para nenhum dos dois. Publicar fechado assim é escopo vazado = prejuízo."""
    pid = projeto_completo
    con_app.execute(
        "INSERT INTO pendencia (projeto_id, motor, mensagem) VALUES (?, 'estrutura', ?)",
        (pid, "[PENDÊNCIA ESTRUTURAL] 1LJ: vão 7.9m reprova até viga dupla"))
    con_app.commit()

    resposta = logado.post(f"/projetos/{pid}/publicar")
    assert resposta.status_code == 409
    assert "estrutural" in resposta.text.lower()
    assert con_app.execute("SELECT COUNT(*) FROM proposta").fetchone()[0] == 0


def test_pendencia_resolvida_libera_a_publicacao(logado, con_app, projeto_completo):
    """O gate abre quando a causa some — senão vira obstáculo a contornar."""
    pid = projeto_completo
    con_app.execute(
        "INSERT INTO pendencia (projeto_id, motor, mensagem) VALUES (?, 'estrutura', ?)",
        (pid, "[PENDÊNCIA ESTRUTURAL] vão reprova"))
    con_app.commit()
    assert logado.post(f"/projetos/{pid}/publicar").status_code == 409

    con_app.execute("DELETE FROM pendencia WHERE projeto_id = ?", (pid,))
    con_app.commit()
    assert logado.post(f"/projetos/{pid}/publicar").status_code == 303


def test_publicar_projeto_completo_cria_v1(logado, con_app, projeto_completo):
    pid = projeto_completo
    resposta = logado.post(f"/projetos/{pid}/publicar")
    assert resposta.status_code == 303

    proposta = con_app.execute(
        "SELECT versao, token, status, total_venda, html FROM proposta WHERE projeto_id = ?",
        (pid,),
    ).fetchone()
    assert proposta["versao"] == 1
    assert proposta["status"] == "ativa"
    assert proposta["total_venda"] > 0
    assert len(proposta["token"]) >= 32
    assert "<" in proposta["html"]          # HTML congelado, não vazio


def test_snapshot_gravado_nao_muda_quando_o_preco_muda(logado, con_app, projeto_completo):
    """D5 levado ao limite, verificado no BANCO (a rota /p/{token} chega na Task 8).

    O que importa aqui é que a publicação CONGELOU: mexer no preço depois não pode
    alterar nem o html nem o total já gravados.
    """
    pid = projeto_completo
    logado.post(f"/projetos/{pid}/publicar")
    antes = con_app.execute("SELECT html, total_venda FROM proposta").fetchone()

    con_app.execute("UPDATE insumo_preco SET preco = preco * 2")   # o mundo muda
    con_app.commit()

    depois = con_app.execute("SELECT html, total_venda FROM proposta").fetchone()
    assert depois["html"] == antes["html"]
    assert depois["total_venda"] == pytest.approx(antes["total_venda"])


def test_nova_versao_revoga_a_anterior(logado, con_app, projeto_completo):
    pid = projeto_completo
    logado.post(f"/projetos/{pid}/publicar")
    logado.post(f"/projetos/{pid}/publicar")

    linhas = con_app.execute(
        "SELECT versao, status FROM proposta WHERE projeto_id = ? ORDER BY versao", (pid,)
    ).fetchall()
    assert [(l["versao"], l["status"]) for l in linhas] == [(1, "revogada"), (2, "ativa")]


def test_publicar_sem_sessao_e_recusado(cliente):
    assert cliente.post("/projetos/1/publicar").status_code == 303


def test_eap_de_fabrica_nao_publica_ate_as_4_composicoes_existirem(logado, con_app):
    """LIMITAÇÃO CONHECIDA, fixada em teste para não voltar a passar despercebida.

    01/05/07/08 são folhas sem composicao_id; o trigger da migração 001 recusa
    quantitativo em item sem composição, então o gate R7 bloqueia TODO projeto.
    O caminho feliz só existe porque a fixture `projeto_completo` inventa folhas
    .99 — arranjo de teste, não uso do app.

    Este teste falha DE PROPÓSITO quando as composições dos 4 grupos entrarem no
    seed (backlog docs/02 §6 item 3). Falhou? Ótimo: apague-o e escreva o teste
    do caminho feliz sobre a EAP real.
    """
    from app.servicos.orcamento import montar

    logado.post("/projetos", data={
        "codigo": "FABRICA", "nome": "EAP de fábrica", "referencia": "2026-06",
        "uf": "SP", "desonerado": "0", "sondagem_pendente": "0"})
    pid = con_app.execute(
        "SELECT id FROM projeto WHERE codigo='FABRICA'").fetchone()["id"]

    # preenche TODA folha que a EAP de fábrica permite preencher. A lista é
    # materializada ANTES: cursor de leitura aberto durante o POST trava o banco.
    folhas = [f["id"] for f in con_app.execute(
        "SELECT id FROM eap_item WHERE composicao_id IS NOT NULL").fetchall()]
    for fid in folhas:
        logado.post(f"/projetos/{pid}/quantitativos",
                    data={"eap_item_id": fid, "quantidade": "10"})

    visao = montar(con_app, pid)
    assert visao.macroetapas_zeradas == ["01", "05", "07", "08"], (
        "a EAP de fábrica mudou — se as composições entraram, veja o docstring")
    assert visao.pode_publicar is False
    assert logado.post(f"/projetos/{pid}/publicar").status_code == 409

    sem_composicao = [c for (c,) in con_app.execute(
        "SELECT codigo FROM eap_item WHERE composicao_id IS NULL"
        " AND id NOT IN (SELECT pai_id FROM eap_item WHERE pai_id IS NOT NULL)"
        " ORDER BY codigo")]
    assert sem_composicao == ["01", "05", "07", "08"]


def test_kpi_e_snapshot_mostram_total_em_faixa_quando_estimado(logado, con_app, projeto_completo):
    """Task 3: com a confiança geral 'estimado' (a montagem LSF domina, D7), o
    número-manchete sai em FAIXA, não seco — na tela interna E no snapshot público
    congelado em /p/token. Falsa precisão no item mais caro é o que se evita."""
    from app.servicos.orcamento import montar

    pid = projeto_completo
    visao = montar(con_app, pid)
    assert visao.venda.confianca == "estimado"
    assert visao.preco_total_min is not None

    minimo = f'{visao.preco_total_min:.2f}'  # formato do KPI (Jinja %.2f, ponto)

    # tela interna
    tela = logado.get(f"/projetos/{pid}/orcamento").text
    assert "faixa ±15%" in tela
    assert minimo in tela

    # snapshot público congelado
    logado.post(f"/projetos/{pid}/publicar")
    token = con_app.execute(
        "SELECT token FROM proposta WHERE projeto_id = ? AND status='ativa'",
        (pid,)).fetchone()["token"]
    pagina = logado.get(f"/p/{token}").text
    assert "±15%" in pagina
    assert minimo in pagina
    # e o snapshot CONGELOU a faixa (não recomputa): mexer no preço não a altera
    import json
    snap = json.loads(con_app.execute(
        "SELECT snapshot_json FROM proposta WHERE projeto_id=? AND status='ativa'",
        (pid,)).fetchone()["snapshot_json"])
    assert snap["preco_total_min"] is not None
