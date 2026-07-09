"""MOTOR 1 — Orçamento (Fase 1, EM CONSTRUÇÃO).
Contratos a implementar (ver CLAUDE.md, Fase atual):
  custo_composicao(con, composicao_id, data_base_id) -> (custo_unitario, confianca)
      # recursivo p/ item_tipo=COMPOSICAO; confiança = pior dos componentes (D4)
  custo_direto_projeto(con, projeto_id) -> linhas por eap_item
  aplicar_bdi(custo_direto, params) -> preco_venda   # fórmula TCU (provada no spike 3)
Aceite da fase: reproduzir 1 orçamento Veks real com desvio <= 2%.
"""
