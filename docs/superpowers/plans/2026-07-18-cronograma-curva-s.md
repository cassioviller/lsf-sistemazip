# Fase 4 — Cronograma (CPM sobre a EAP) + Curva S físico-financeira

**Objetivo**: fechar D1 pela outra ponta — orçamento e cronograma leem a MESMA
EAP, então a curva S fecha no total por construção. Atividade = macroetapa com
quantitativo; duração DERIVADA: homem-horas = Σ(quantidade × coef MO h/un da
composição, recursivo) ÷ (equipe × jornada). A rede de precedências LSF é DADO
(migração 015 + seed com origem anotada), não código. CPM com TI/II/TT + lag
(contrato do stub). Curva S com **aço adiantado**: a parcela MATERIAL de cada
atividade desembolsa no INÍCIO dela (compra antecipada de kit LSF), a MO
uniforme na duração. Saída MSPDI (.xml) importável no ProjectLibre.

**Aceite (docs/02 §4, adaptado)**: "validação cruzada com ProjectLibre" — o que
o repositório PODE provar: CPM reproduz rede de referência calculada à mão
(incl. II/TT com lag), curva S fecha exatamente no custo direto do orçamento, e
o XML MSPDI é bem-formado com datas/durações/vínculos corretos re-parseados em
teste. A conferência visual no ProjectLibre é ação do usuário sobre o arquivo
gerado em `saida/` (registrada como passo, não como teste automatizado).

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origemRegra`).

### Task 1: Migração 015 + seed — rede de precedências LSF e equipes como DADO

- `precedencia_macroetapa (grupo_pred, grupo_succ, tipo TI|II|TT, lag_dias)` e
  `equipe_macroetapa (grupo_eap PK, trabalhadores, hammock)`.
- Seed da rede LSF (origem anotada, `estimado`): PRELIM→FUNDACAO TI+0;
  FUNDACAO→ESTRUTURA TI+3 (cura p/ ancoragem química Parabolt, fck mínimo);
  ESTRUTURA→FECHAMENTO II+5 e TT+2 (montagem painel a painel: fechamento
  acompanha com defasagem e não termina antes); ESTRUTURA→INSTALACOES II+8
  (instalações nas paredes abertas); FECHAMENTO→ACABAMENTO TI+0;
  INSTALACOES→ACABAMENTO TI+0; ACABAMENTO→COMPLEMENTO TI+0. GERENCIAMENTO
  hammock=1 (acompanha o projeto inteiro). Equipes por grupo + regra
  `jornada_h_dia` 8 (CLT).
- Teste: rede sem ciclo, grupos válidos, seed idempotente.

### Task 2: Motor — homem-horas, atividades e CPM TI/II/TT com lag

- `horas_mo_composicao(con, composicao_id)`: h/un somando insumos MO
  recursivamente (aninhamento como o custo; ausência de analítica = exceção).
- `montar_atividades(con, projeto_id)`: macroetapa com quantitativo → duração
  em dias = ceil(Σ hh / (trabalhadores × jornada)); custo do subtotal do
  `custo_direto_projeto` (D1); confiança = pior(quantitativo, composição,
  'estimado'). Macroetapa zerada fica FORA com alerta (o R7 já bloqueia
  publicação; o cronograma dos presentes continua computável).
- `cpm(atividades, precedencias)`: passagem direta/inversa generalizada —
  TI: ES_j ≥ EF_i+lag · II: ES_j ≥ ES_i+lag · TT: EF_j ≥ EF_i+lag; folga e
  caminho crítico. Hammock entra depois do CPM com duração = makespan.
- Testes: rede do spike 2 (A-B-D=9) reproduzida; rede com II e TT conferida à
  mão no docstring; ciclo detectado vira exceção.

### Task 3: Curva S ponderada (aço adiantado)

- `custo_composicao_por_tipo`: reparte o custo unitário por tipo de insumo
  (MAT/MO/...), recursivo, consistente com `custo_composicao`.
- `curva_s(con, projeto_id, cronograma)`: desembolso diário — MAT da atividade
  no dia do INÍCIO (aço adiantado: kit comprado antes da montagem), resto
  uniforme na duração; hammock uniforme no makespan. Acumulado final ==
  `custo_direto_projeto().total` EXATO (é a prova de D1) + opção preço de venda
  (× (1+BDI)).
- Teste: igualdade exata no fecho; MAT da estrutura concentrado no início
  (primeiro dia da atividade 03 carrega o kg comprado × preço MAT).

### Task 4: Saída MSPDI + app

- `exportar_mspdi(cronograma, inicio) -> str` (XML MS Project/ProjectLibre:
  Tasks com UID/Duration/Start/Finish + PredecessorLink TI→1, II→3, TT→0; dias
  corridos, documentado). Gravação em `saida/cronograma_<codigo>.xml`.
- Tela `/projetos/{id}/cronograma`: tabela de atividades (ES/EF, folga,
  crítico), curva S acumulada (tabela por semana) e link para baixar o XML.
  Zero regra no app (D6).
- Teste: XML re-parseado (ElementTree) — datas, durações e vínculos batem com o
  CPM; app 200 com atividades; projeto sem quantitativo → mensagem, não 500.

### Task 5: Validação, CLAUDE.md e fechamento

- Cronograma da 109 (quantitativos derivados) sai com makespan plausível e
  crítico passando por FUNDACAO→ESTRUTURA; curva fecha no custo direto.
- Verificação no servidor real (tela + download). CLAUDE.md: Fase 4 concluída,
  validação ProjectLibre = passo do usuário sobre o XML. Merge + push.
