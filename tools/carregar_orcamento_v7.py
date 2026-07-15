# -*- coding: utf-8 -*-
"""ACEITE DA FASE 1 — carrega o orçamento real da obra 109.1506 (Máximo Tintas).

Fonte: tests/fixtures/orcamento_v7_109_1506.json, extraído executando o engine do
calculador v7 (assets/, read-only) headless em node — quantidades e preços são os
oficiais da obra de referência. Cada linha vira: insumo (preço 'estimado', fonte
anotada) → composição de 1 insumo com coeficiente (1+perda_extra), espelhando o
cálculo do v7 → folha de EAP → quantitativo origem=MANUAL.

O BDI da obra é margem simples de 22% (PRECOS.bdi do v7), não o TCU decomposto do
seed: entra como ParametrosBDI(l=0.22, resto 0) — a fórmula TCU degenera para
(1+L), reproduzindo o markup original sem tocar em parametros_globais.

Uso CLI:  .venv/bin/python tools/carregar_orcamento_v7.py
  (constrói banco em memória, carrega, imprime tabela de desvio e grava
   saida/orcamento_109_1506.{html,csv})
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from lsf.motores.orcamento import (  # noqa: E402
    ParametrosBDI,
    aplicar_bdi,
    custo_direto_projeto,
)

FIXTURE = RAIZ / "tests" / "fixtures" / "orcamento_v7_109_1506.json"

# item do v7 → (código de folha na EAP, macroetapa)
MAPA_EAP = {
    "Aço (comprado em barras 6m)": ("03.02", "ESTRUTURA"),
    "Chapa OSB/piso": ("03.03", "ESTRUTURA"),
    "Parafusos/fixadores": ("03.04", "ESTRUTURA"),
    "Chapas gusset": ("03.05", "ESTRUTURA"),
    "Mão de obra": ("03.06", "ESTRUTURA"),
    "Chapa cimentícia": ("04.04", "FECHAMENTO"),
    "Telha": ("04.05", "FECHAMENTO"),
    "Cumeeira": ("04.06", "FECHAMENTO"),
    "Calha": ("04.07", "FECHAMENTO"),
    "Chapa drywall": ("06.02", "ACABAMENTO"),
}


def carregar_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def parametros_bdi_da_obra(fixture: dict) -> ParametrosBDI:
    """Margem simples do v7 expressa na estrutura TCU: só L, resto zero."""
    return ParametrosBDI(ac=0, s=0, r=0, g=0, df=0, l=fixture["bdi"], i=0,
                         confianca="estimado")


def carregar(con, fixture: dict) -> int:
    """Cria insumos, composições, folhas de EAP, projeto e quantitativos. -> projeto_id"""
    veks = con.execute("SELECT id FROM fonte WHERE sigla = 'VEKS'").fetchone()[0]
    db_id = con.execute(
        "SELECT db.id FROM data_base db WHERE db.fonte_id = ? AND db.referencia = '2026-06'",
        (veks,),
    ).fetchone()[0]
    coef = 1 + fixture["perda_extra"]

    pid = con.execute(
        "INSERT INTO projeto (codigo, nome, cliente, referencia, uf, desonerado, observacao)"
        " VALUES ('109.1506', 'Edifício Máximo Tintas', 'Máximo Tintas', '2026-06', 'SP', 0,"
        "         'aceite Fase 1: reprodução do orçamento v7')"
    ).lastrowid

    for n, linha in enumerate(fixture["linhas"], start=1):
        eap_codigo, grupo = MAPA_EAP[linha["item"]]
        iid = con.execute(
            "INSERT INTO insumo (fonte_id, codigo_fonte, descricao, tipo, unidade)"
            " VALUES (?, ?, ?, ?, ?)",
            (veks, f"VK-A-{n:02d}", linha["item"],
             "MO" if linha["item"] == "Mão de obra" else "MAT", linha["un"]),
        ).lastrowid
        con.execute(
            "INSERT INTO insumo_preco (insumo_id, data_base_id, preco, confianca)"
            " VALUES (?, ?, ?, 'estimado')",
            (iid, db_id, linha["preco_unit"]),
        )
        cid = con.execute(
            "INSERT INTO composicao (fonte_id, codigo_fonte, descricao, unidade, grupo_eap,"
            " confianca, observacao) VALUES (?, ?, ?, ?, ?, 'estimado',"
            " 'aceite F1: preço do orçamento v7 109.1506; coef = 1+perda_extra (3%)')",
            (veks, f"VK-CA-{n:02d}", f"{linha['item']} — obra 109.1506", linha["un"], grupo),
        ).lastrowid
        con.execute(
            "INSERT INTO composicao_item (composicao_id, item_tipo, item_id, coeficiente)"
            " VALUES (?, 'INSUMO', ?, ?)",
            (cid, iid, coef),
        )
        pai = con.execute(
            "SELECT id FROM eap_item WHERE codigo = ?", (eap_codigo.split(".")[0],)
        ).fetchone()[0]
        eid = con.execute(
            "INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap, composicao_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (eap_codigo, pai, linha["item"], linha["un"], grupo, cid),
        ).lastrowid
        con.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem, confianca,"
            " origem_regra) VALUES (?, ?, ?, 'MANUAL', 'estimado',"
            " 'orçamento v7 109.1506 executado headless')",
            (pid, eid, linha["qtd"]),
        )
    return pid


def tabela_desvio(venda, fixture):
    """[(item, nosso_custo, custo_v7, desvio_pct)] + (nosso_total, total_v7, desvio_pct)."""
    v7 = {MAPA_EAP[l["item"]][0]: l for l in fixture["linhas"]}
    linhas = []
    for lv in venda.linhas:
        ref = v7[lv.eap_codigo]
        desvio = (lv.custo_direto - ref["total"]) / ref["total"] * 100
        linhas.append((lv.eap_codigo, ref["item"], lv.custo_direto, ref["total"], desvio))
    total_v7 = fixture["total_com_bdi"]
    desvio_total = (venda.preco_total - total_v7) / total_v7 * 100
    return linhas, (venda.preco_total, total_v7, desvio_total)


def montar_banco() -> sqlite3.Connection:
    """Banco em memória na MESMA ordem de db/build_db.py e do fixture `con` dos testes:
    estrutura primeiro (schema + migrações ordenadas), seed por último — o seed depende
    das migrações (perfil 'laminado' exige o CHECK relaxado da 006; ON CONFLICT da 003)."""
    con = sqlite3.connect(":memory:")
    con.executescript((RAIZ / "db" / "schema.sql").read_text())
    for m in sorted((RAIZ / "db" / "migrations").glob("*.sql")):
        con.executescript(m.read_text())
    con.executescript((RAIZ / "db" / "seed.sql").read_text())
    con.execute("PRAGMA foreign_keys = ON")
    return con


def main():
    from lsf.relatorios import relatorio_csv, relatorio_html

    con = montar_banco()

    fixture = carregar_fixture()
    pid = carregar(con, fixture)
    orc = custo_direto_projeto(con, pid)
    venda = aplicar_bdi(orc, parametros_bdi_da_obra(fixture))

    linhas, (nosso, deles, desvio_total) = tabela_desvio(venda, fixture)
    print(f"ACEITE FASE 1 — {fixture['obra']} (referência {orc.referencia}/{orc.uf})\n")
    print(f"{'EAP':6} {'item':32} {'nosso R$':>14} {'v7 R$':>14} {'desvio':>8}")
    for eap, item, nosso_l, v7_l, d in linhas:
        print(f"{eap:6} {item[:32]:32} {nosso_l:14,.2f} {v7_l:14,.2f} {d:7.4f}%")
    print(f"\ncusto direto : nosso {orc.total:14,.2f} · v7 {fixture['custo_direto']:14,.2f}")
    print(f"com BDI {fixture['bdi']*100:.0f}%  : nosso {nosso:14,.2f} · v7 {deles:14,.2f}")
    print(f"DESVIO TOTAL : {desvio_total:.6f}%  (meta ≤ 2%)")
    print(f"macroetapas zeradas (R7): {', '.join(orc.macroetapas_zeradas)}")

    (RAIZ / "saida").mkdir(exist_ok=True)
    (RAIZ / "saida" / "orcamento_109_1506.html").write_text(relatorio_html(venda))
    (RAIZ / "saida" / "orcamento_109_1506.csv").write_text(relatorio_csv(venda))
    print("\nrelatórios gravados em saida/orcamento_109_1506.{html,csv}")


if __name__ == "__main__":
    main()
