# docs/previews — mockups de UI/UX (design, não gerado)

Protótipos **estáticos** de tela para calibrar a identidade visual das saídas do sistema.
São HTML autocontido (CSS/JS inline, tema claro/escuro, responsivo) com **dados fixos** da
obra 109.1506 — servem para decidir layout, hierarquia e cores, **não** são produzidos pelo motor.

| Arquivo | Tela | Status |
|---|---|---|
| `cadeia_inferencia.html` | Cadeia de inferência física (D3): arquitetônico → paredes → estrutura → cargas → fundação → SINAPI, com confiança propagada (D4) e o gate do solo | mockup |
| `orcamento_analitico.html` | Orçamento analítico turn-key: KPIs, composição do custo, medidor de completude turn-key (macroetapas zeradas / R7), tabela com faixa ±% | mockup |

## O que estes previews respeitam do domínio

- **Confiança propagada (D4)**: todo número derivado exibe origem/confiança; a cadeia herda a **pior**
  (rank numérico `real < estimado < parametrico`, nunca `MIN()` de string). Baixa confiança vira faixa ±%, não valor seco.
- **Dado ausente é erro (D4.1)**: o solo (input que o arquitetônico não dá) derruba a cadeia para `pendente`
  até a sondagem resolver; macroetapa zerada é gate de escopo vazado (R7), não rodapé.
- **LSF é leve**: fundação governada pelo mínimo construtivo `max(teórica, 0,30 m)`, não pela tensão do solo.

## Próximo passo (quando aprovado)

Portar o layout para funções puras sobre o banco (D6), gerando as telas a partir de dados reais em
`src/lsf/relatorios.py` (`relatorio_html` já existe para o orçamento; a cadeia pediria uma `relatorio_cadeia_html`),
substituindo os dados fixos destes mockups.
