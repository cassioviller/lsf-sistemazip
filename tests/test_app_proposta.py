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
