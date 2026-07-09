# Primeira mensagem sugerida para o Claude Code

---
Leia o CLAUDE.md e os docs/ para carregar o contexto do projeto. Depois:

1. Rode o setup e confirme que a regressão passa:
   `python3 db/build_db.py && pytest tests/ -q`

2. Estamos na FASE 1 (motor de orçamento). Implemente em `src/lsf/motores/orcamento.py`
   o item 1 do contrato: `custo_composicao(con, composicao_id, data_base_id)` recursivo,
   com propagação de confiança (D4: pior componente vence), cobrindo composição-em-composição
   — a view do banco só resolve 1 nível. Escreva os testes no mesmo commit, incluindo um caso
   de composição aninhada e um caso de confiança mista (real + estimado → estimado).

3. Em seguida, crie as tabelas de projeto (`projeto`, `quantitativo` com campo `origem`)
   como migração em `db/`, seguindo o modelo do docs/01 §4, e me mostre o plano
   para `custo_direto_projeto` antes de implementar.

Regras: não reabrir decisões D1-D8; política de licenças do CLAUDE.md; todo número
derivado carrega origem e confiança; pytest verde antes de cada commit.
---
