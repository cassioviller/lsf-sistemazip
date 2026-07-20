"""Item 5 do contrato da Fase 1: relatório analítico CSV + HTML.
O portão manual do roteiro ("abrir o HTML e conferir as faixas") vira teste aqui:
faixa aparece em TODO item estimado/parametrico e em NENHUM item real."""
import csv
import io

import pytest

from lsf.motores.orcamento import (
    aplicar_bdi,
    carregar_parametros_bdi,
    custo_direto_projeto,
)
from lsf.relatorios import relatorio_csv, relatorio_html
from test_custo_direto import QTD, _analitica_96359


@pytest.fixture
def venda(con):
    _analitica_96359(con)
    pid = con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf) VALUES ('109.1506', 'Máximo', '2026-06', 'SP')"
    ).lastrowid
    for codigo, qtd in QTD.items():
        eap = con.execute("SELECT id FROM eap_item WHERE codigo = ?", (codigo,)).fetchone()[0]
        con.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem, confianca)"
            " VALUES (?, ?, ?, 'MANUAL', 'real')",
            (pid, eap, qtd),
        )
    return aplicar_bdi(custo_direto_projeto(con, pid), carregar_parametros_bdi(con))


def _linhas_csv(texto):
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    cab = linhas[0]
    dados = [dict(zip(cab, l)) for l in linhas[1:] if l and l[0] not in ("", "TOTAL", "ALERTA")]
    return cab, dados, linhas


# ---------- CSV ----------

def test_csv_tem_todas_as_linhas_e_colunas(venda):
    cab, dados, _ = _linhas_csv(relatorio_csv(venda))
    assert cab == ["eap", "descricao", "unidade", "quantidade", "origem", "custo_unitario",
                   "custo_direto", "preco_bdi", "preco_min", "preco_max", "confianca", "pendencia"]
    assert [d["eap"] for d in dados] == ["03.01", "04.01", "04.02", "04.03", "06.01"]


def test_csv_faixa_so_em_item_de_baixa_confianca(venda):
    _, dados, _ = _linhas_csv(relatorio_csv(venda))
    for d in dados:
        if d["confianca"] in ("estimado", "parametrico"):
            assert d["preco_min"] and d["preco_max"], d["eap"]
        else:
            assert d["preco_min"] == "" and d["preco_max"] == "", d["eap"]
    # com o BDI 'estimado' rebaixando tudo (D4), nenhuma linha fica 'real'
    assert all(d["confianca"] == "estimado" for d in dados)


def test_csv_faixa_e_15_pct_parametrizavel(venda):
    _, dados, _ = _linhas_csv(relatorio_csv(venda, faixa_pct=0.10))
    linha = dados[0]
    preco = float(linha["preco_bdi"].replace(",", "."))
    assert float(linha["preco_min"].replace(",", ".")) == pytest.approx(preco * 0.90, abs=0.01)
    assert float(linha["preco_max"].replace(",", ".")) == pytest.approx(preco * 1.10, abs=0.01)


def test_csv_alerta_de_macroetapa_zerada(venda):
    *_, brutas = _linhas_csv(relatorio_csv(venda))
    alertas = [l for l in brutas if l and l[0] == "ALERTA"]
    assert len(alertas) == 5  # 01, 02, 05, 07, 08
    assert any("macroetapa 02" in l[1] for l in alertas)


# ---------- HTML ----------

def test_html_faixa_so_em_item_estimado(con, venda):
    """Cria um cenário misto: zera o BDI p/ 'real' e deixa só a 04.03 estimada."""
    con.execute("UPDATE parametros_globais SET confianca = 'real' WHERE chave LIKE 'bdi_%'")
    con.execute(
        "UPDATE composicao SET confianca = 'real' WHERE codigo_fonte LIKE 'VK-C-%'"
        " AND codigo_fonte != 'VK-C-004'"
    )
    con.execute("UPDATE insumo_preco SET confianca = 'real'")
    pid = con.execute("SELECT id FROM projeto").fetchone()[0]
    venda2 = aplicar_bdi(custo_direto_projeto(con, pid), carregar_parametros_bdi(con))
    html = relatorio_html(venda2)

    por_conf = {l.eap_codigo: l.confianca for l in venda2.linhas}
    assert por_conf["04.03"] == "estimado" and por_conf["03.01"] == "real"
    # a célula de faixa (div class="ref") aparece exatamente 1 vez: só na linha estimada
    # (o rodapé também menciona '±15%' no disclaimer, por isso não se conta o texto)
    assert html.count('class="ref"') == 1
    linha_0403 = html.split('<td>04.03</td>')[1].split("</tr>")[0]
    assert "–" in linha_0403 and "±15%" in linha_0403
    linha_0301 = html.split('<td>03.01</td>')[1].split("</tr>")[0]
    assert "±" not in linha_0301


def test_html_alertas_e_disclaimer(venda):
    html = relatorio_html(venda)
    assert "Macroetapa 02 sem nenhum quantitativo" in html
    assert "PRÉ-DIMENSIONAMENTO" in html          # disclaimer não é rodapé morto
    assert "BDI 27,79%" in html
    assert "R$ 62.532,54" in html                  # custo direto total, formato pt-BR


def test_html_pendencia_visivel_e_total_nao_fecha(con, venda):
    comp = con.execute("SELECT id FROM composicao WHERE codigo_fonte = '96359'").fetchone()[0]
    con.execute("DELETE FROM composicao_item WHERE composicao_id = ?", (comp,))
    pid = con.execute("SELECT id FROM projeto").fetchone()[0]
    venda2 = aplicar_bdi(custo_direto_projeto(con, pid), carregar_parametros_bdi(con))
    html = relatorio_html(venda2)
    assert "NÃO FECHA" in html
    assert "96359" in html  # a pendência aparece no bloco de alertas


def test_proposta_docx_com_identidade_e_gates(con, base, db_veks, id_de):
    """Saída .docx (python-docx MIT, docs/04): identidade Veks, subtotais com
    confiança e a seção de gates — disclaimer é seção, não rodapé morto."""
    import io

    import pytest
    docx = pytest.importorskip("docx")

    from lsf.motores.orcamento import (aplicar_bdi, carregar_parametros_bdi,
                                       custo_direto_projeto)
    from lsf.relatorios import proposta_docx

    con.execute(
        "INSERT INTO projeto (codigo, nome, cliente, referencia, uf, desonerado,"
        " sondagem_pendente) VALUES ('DOCX-1', 'Obra Docx', 'Cliente', '2026-06',"
        " 'SP', 0, 1)")
    pid = con.execute("SELECT id FROM projeto WHERE codigo='DOCX-1'").fetchone()[0]
    folha = con.execute("SELECT id FROM eap_item WHERE codigo='03.01'").fetchone()[0]
    con.execute(
        "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem,"
        " confianca) VALUES (?,?,1000,'MANUAL','real')", (pid, folha))
    con.commit()

    venda = aplicar_bdi(custo_direto_projeto(con, pid),
                        carregar_parametros_bdi(con))
    conteudo = proposta_docx(
        venda, {"codigo": "DOCX-1", "nome": "Obra Docx", "cliente": "Cliente",
                "sondagem_pendente": 1},
        ["[PENDÊNCIA ESTRUTURAL] vão reprova"])

    d = docx.Document(io.BytesIO(conteudo))
    texto = "\n".join(p.text for p in d.paragraphs)
    assert "VEKS ENGENHARIA" in texto
    assert "Sondagem PENDENTE" in texto
    assert "vão reprova" in texto
    assert "PRÉ-DIMENSIONAMENTO" in texto
    tabelas = d.tables[0]
    assert any("03" in c.text for r in tabelas.rows for c in r.cells)
