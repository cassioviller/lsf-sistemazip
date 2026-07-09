"""Relatório analítico do orçamento (Fase 1, item 5 do contrato).

Dois formatos, ambos gerados como string pelo motor (D6 — zero framework web):
  relatorio_csv(venda)  -> CSV ';' com decimal vírgula (conferência em planilha pt-BR)
  relatorio_html(venda) -> HTML estático

D4 na saída: itens 'estimado'/'parametrico' exibem FAIXA (±faixa_pct, default 15%)
em vez de valor seco. Rodapé traz alertas: macroetapas zeradas (aviso na Fase 1;
vira gate duro na Fase 3) e pendências de preço.
"""
from __future__ import annotations

import csv
import html
import io

from lsf.motores.orcamento import OrcamentoVenda

FAIXA_PCT_DEFAULT = 0.15


def _brl(valor: float | None) -> str:
    if valor is None:
        return ""
    return f"{valor:,.2f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def _num(valor: float | None, casas: int = 2) -> str:
    if valor is None:
        return ""
    return f"{valor:.{casas}f}".replace(".", ",")


def _tem_faixa(confianca: str | None) -> bool:
    return confianca in ("estimado", "parametrico")


def _faixa(valor: float | None, confianca: str | None, faixa_pct: float):
    """(mínimo, máximo) para valores de baixa confiança; (None, None) para 'real'."""
    if valor is None or not _tem_faixa(confianca):
        return None, None
    return valor * (1 - faixa_pct), valor * (1 + faixa_pct)


def relatorio_csv(venda: OrcamentoVenda, faixa_pct: float = FAIXA_PCT_DEFAULT) -> str:
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\n")
    w.writerow([
        "eap", "descricao", "unidade", "quantidade", "origem",
        "custo_unitario", "custo_direto", "preco_bdi",
        "preco_min", "preco_max", "confianca", "pendencia",
    ])
    for l in venda.linhas:
        pmin, pmax = _faixa(l.preco_venda, l.confianca, faixa_pct)
        w.writerow([
            l.eap_codigo, l.descricao, l.unidade, _num(l.quantidade), l.origem,
            _num(l.custo_unitario, 4), _num(l.custo_direto), _num(l.preco_venda),
            _num(pmin), _num(pmax), l.confianca or "", l.pendencia or "",
        ])
    orc = venda.orcamento
    w.writerow([])
    w.writerow(["TOTAL", f"BDI {_num(venda.bdi * 100)}%", "", "", "",
                "", _num(orc.total), _num(venda.preco_total), "", "",
                venda.confianca or "", "; ".join(orc.pendencias)])
    for codigo in orc.macroetapas_zeradas:
        w.writerow(["ALERTA", f"macroetapa {codigo} sem quantitativo (escopo vazado? R7)"])
    return saida.getvalue()


def relatorio_html(venda: OrcamentoVenda, faixa_pct: float = FAIXA_PCT_DEFAULT) -> str:
    orc = venda.orcamento
    e = html.escape

    def celula_preco(l):
        if l.preco_venda is None:
            return f'<td class="pend" colspan="1">pendente</td>'
        if _tem_faixa(l.confianca):
            pmin, pmax = _faixa(l.preco_venda, l.confianca, faixa_pct)
            return (f"<td>R$ {_brl(pmin)} – R$ {_brl(pmax)}"
                    f'<div class="ref">ref. R$ {_brl(l.preco_venda)} ±{_num(faixa_pct * 100, 0)}%</div></td>')
        return f"<td>R$ {_brl(l.preco_venda)}</td>"

    linhas_html = []
    for l in venda.linhas:
        linhas_html.append(
            f'<tr class="{e(l.confianca or "pendente")}">'
            f"<td>{e(l.eap_codigo)}</td><td>{e(l.descricao)}</td><td>{e(l.unidade)}</td>"
            f'<td class="n">{_num(l.quantidade)}</td><td>{e(l.origem)}</td>'
            f'<td class="n">{_brl(l.custo_unitario)}</td><td class="n">{_brl(l.custo_direto)}</td>'
            f"{celula_preco(l)}<td>{e(l.confianca or '—')}</td></tr>"
        )

    subtotais_html = []
    for s in orc.subtotais:
        valor = "ZERADA" if s.zerada else ("pendente" if s.custo is None else f"R$ {_brl(s.custo)}")
        subtotais_html.append(
            f"<tr><td>{e(s.eap_codigo)}</td><td>{e(s.descricao)}</td>"
            f'<td class="n">{valor}</td><td>{e(s.confianca or "—")}</td></tr>'
        )

    alertas = [
        f"Macroetapa {codigo} sem nenhum quantitativo — escopo vazado em turn-key é prejuízo (R7). "
        f"Aviso na Fase 1; bloqueia proposta a partir da Fase 3."
        for codigo in orc.macroetapas_zeradas
    ] + list(orc.pendencias)
    alertas_html = "".join(f"<li>{e(a)}</li>" for a in alertas) or "<li>nenhum</li>"

    total_html = (
        f"R$ {_brl(venda.preco_total)}" if venda.preco_total is not None
        else "NÃO FECHA — resolver pendências"
    )

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Orçamento analítico — {e(orc.projeto_codigo)}</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;color:#222}}
 table{{border-collapse:collapse;width:100%;margin:1rem 0}}
 th,td{{border:1px solid #ccc;padding:.35rem .5rem;font-size:.9rem;text-align:left}}
 td.n{{text-align:right;font-variant-numeric:tabular-nums}}
 tr.estimado td,tr.parametrico td{{background:#fff8e6}}
 tr.pendente td,td.pend{{background:#fdecea}}
 .ref{{font-size:.75rem;color:#666}}
 .alertas{{background:#fdecea;padding:1rem;border-left:4px solid #c0392b}}
 .rodape{{font-size:.8rem;color:#666;margin-top:2rem}}
</style></head><body>
<h1>Orçamento analítico — {e(orc.projeto_codigo)}</h1>
<p>Referência {e(orc.referencia)}/{e(orc.uf or "BR")} · {"desonerado" if orc.desonerado else "não desonerado"}
 · BDI {_num(venda.bdi * 100)}% (TCU, {e(venda.parametros.confianca)}) · confiança geral: {e(venda.confianca or "—")}</p>
<table><thead><tr><th>EAP</th><th>Descrição</th><th>Un</th><th>Qtd</th><th>Origem</th>
<th>Custo unit. (R$)</th><th>Custo direto (R$)</th><th>Preço c/ BDI</th><th>Confiança</th></tr></thead>
<tbody>{"".join(linhas_html)}</tbody></table>
<h2>Subtotais por macroetapa (custo direto)</h2>
<table><thead><tr><th>EAP</th><th>Macroetapa</th><th>Custo direto</th><th>Confiança</th></tr></thead>
<tbody>{"".join(subtotais_html)}</tbody></table>
<h2>Total</h2>
<p><strong>Custo direto: {"R$ " + _brl(orc.total) if orc.total is not None else "NÃO FECHA"}
 · Preço de venda: {total_html}</strong></p>
<div class="alertas"><h2>Alertas</h2><ul>{alertas_html}</ul></div>
<p class="rodape">PRÉ-DIMENSIONAMENTO para fins de orçamento — não substitui projeto estrutural,
sondagem ou ART. Itens 'estimado'/'parametrico' exibidos em faixa ±{_num(faixa_pct * 100, 0)}% (D4).
Gerado pelo motor de orçamento LSF Veks.</p>
</body></html>"""
