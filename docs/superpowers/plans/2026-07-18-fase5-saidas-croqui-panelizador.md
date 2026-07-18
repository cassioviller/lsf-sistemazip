# Fase 5 — Panelizador com romaneio, DXF→planta, TAKEOFF e saídas

**Objetivo** (docs/02 §4, Fase 5): fechar o ciclo comercial-executivo do produto:
(1) o panelizador do spike 5 — que já vive em `_panelizar`/`plano_de_corte` —
evolui para PAINÉIS com ID, kit de corte por painel e romaneio fábrica/obra;
(2) a rota do DXF (spike 1, ezdxf MIT) vira importador real para a
`planta_normalizada` com upload no app; (3) a migração PARAMETRICO→TAKEOFF do
D2 ganha o gesto no app (lançamento medido de executivo troca a linha derivada);
(4) saídas: romaneio CSV/HTML; docx com identidade Veks SE python-docx (MIT)
puder ser instalado — senão registra pendência de ambiente, sem quebrar nada.

**Aceite (adaptado)**: romaneio da 109 cobre 100% das peças de parede geradas
(nenhum kg fora de painel, batido contra o `gerar_estrutura`); DXF do spike
importado vira paredes reais no banco com origem DXF e confiança estimado;
lançar TAKEOFF numa folha PARAMETRICO troca a linha e o orçamento re-lê (D2);
tudo verificado no servidor real.

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origemRegra`).

### Task 1: Panelizador — painéis com ID e peças atribuídas

- `panelizar_parede(estrutura: EstruturaParede, nivel, seq) -> list[Painel]`:
  os limites já saem de `_panelizar` (juntas); cada painel ganha ID
  `{nivel}PV-P{seq:02d}` (padrão 1PV do caderno), faixa [x0,x1] e as PEÇAS da
  parede atribuídas por posição (peça que cruza junta pertence ao painel onde
  começa — guias já são segmentadas por painel no gerador).
- Invariante travado em teste: Σ peças dos painéis == peças da parede (nada
  órfão, nada duplicado), incluindo kg.

### Task 2: Kit de corte + romaneio fábrica/obra (motor + saída + app)

- `romaneio_projeto(con, projeto_id) -> Romaneio`: por painel, kit de corte por
  perfil (comprimentos decrescentes, barras 6 m via first-fit do plano_de_corte)
  + resumo por nível; total bate com `gerar_estrutura` (kg 100%).
- `relatorios.romaneio_csv/html`: fábrica (kits por painel p/ corte) e obra
  (sequência de montagem por nível). Download no app em
  `/projetos/{id}/romaneio.csv` + seção na tela da planta.

### Task 3: Migração PARAMETRICO→TAKEOFF no app (D2)

- Lançamento de quantitativo ganha origem TAKEOFF (checkbox "medido de projeto
  executivo") → grava origem='TAKEOFF', confianca='real', trocando a linha
  existente (inclusive PARAMETRICO). `derivar_quantitativos`/`derivar_fundacao`
  já preservam TAKEOFF (guarda testada) — o caminho de volta é re-derivar após
  apagar a linha (fora de escopo: exclusão de quantitativo já existe? se não,
  botão de excluir linha).
- Teste: PARAMETRICO → TAKEOFF troca; derivar depois preserva TAKEOFF; orçamento
  re-lê a quantidade nova.

### Task 4: Importador DXF → planta_normalizada

- `importar_dxf(con, nivel_id, caminho) -> resultado`: generaliza o spike 1 —
  linhas da layer PAREDE em pares paralelos (0,09–0,25 m) viram eixos; eixos
  viram `no_planta`/`parede` (origem 'DXF', confiança 'estimado', perfil NULL a
  atribuir na tela). Linha sem par vira aviso, nunca parede inventada.
- Upload na tela da planta (multipart, já há python-multipart). Teste com o DXF
  do spike (2 eixos, espessura 0,14) + DXF vazio/sem layer → aviso.

### Task 5: Saídas docx (condicional) + verificação + fechamento

- Tentar `pip install python-docx` (MIT — registrar em docs/04). Sucesso →
  `relatorios.proposta_docx(venda)` mínimo com identidade Veks + download.
  Falha (sem rede) → registrar pendência de ambiente em docs/04 e CLAUDE.md,
  sem quebrar suíte (teste com skipif).
- Verificação no servidor real (romaneio, upload DXF, TAKEOFF). CLAUDE.md
  atualizado; merge + push.
