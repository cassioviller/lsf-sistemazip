# CLAUDE.md — Sistema de Orçamento e Cronograma Físico-Financeiro LSF (Veks Engenharia)

Você está trabalhando no sistema que transforma um projeto arquitetônico (DXF/DWG/croqui) em: quantitativos derivados por cadeia de inferência física, orçamento com base SINAPI + composições próprias, cronograma com caminho crítico (CPM) e curva S físico-financeira — para obras turn-key em Light Steel Frame. Este arquivo é a fonte de verdade do projeto; os detalhes estão em `docs/`.

## Estado atual (o que JÁ existe e funciona — não reescrever, evoluir)

- **`db/schema.sql` + `db/seed.sql` + `db/migrations/`**: base de conhecimento multi-fonte versionada por data-base. 12 fontes, 20 perfis LSF (portados do v7 em `assets/`), 9 regras NBR 15758, pesos por camada, 5 classes de solo, composições próprias, mapeamento item→composição. Migração 001: `projeto` (trava referência+uf+desonerado), `quantitativo` (origem MANUAL|PARAMETRICO|TAKEOFF, trigger só-em-folha), `eap_item` (hierarquia com CHECK nas 8 macroetapas). Migração 002: `parametros_globais` (BDI TCU decomposto). `db/build_db.py` aplica schema+seed+migrações em ordem.
- **`src/lsf/motores/orcamento.py` — FASE 1 CONCLUÍDA (aceite: desvio 0,00% vs orçamento v7 da 109.1506)**: `custo_composicao` recursivo (aninhamento, ciclo detectado, memoização; dado ausente = exceção, nunca custo parcial), `custo_direto_projeto` (linhas + subtotais por macroetapa + total que se recusa a fechar com pendência; `macroetapas_zeradas` alimenta o gate R7), `carregar_parametros_bdi`/`bdi_tcu`/`aplicar_bdi` (27,79% reproduzido do banco). Confiança propagada por rank numérico `real<estimado<parametrico` — NUNCA por MIN() de string (ordem alfabética elege o pior errado). O motor NÃO usa `vw_custo_composicao` (1 nível, INNER JOIN engole dado faltante); a view fica para consulta rápida de composição plana.
- **`src/lsf/relatorios.py`**: relatório analítico CSV (';', decimal vírgula) e HTML estático (D6), com faixa ±% em itens estimado/parametrico (D4) e alertas de macroetapa zerada + pendências.
- **`tests/`**: 67 testes; `tests/spikes_validacao.py` (6 spikes: DXF→eixos, CPM, Curva S + BDI TCU, takedown via banco, panelizador, cadeia item→custo) segue como regressão — se um spike quebrar, o commit está errado. `tests/test_aceite_fase1.py` guarda o aceite contra `tests/fixtures/orcamento_v7_109_1506.json` (engine do v7 executado headless via node; `tools/carregar_orcamento_v7.py` é o carregador + CLI de conferência).
- **`src/lsf/geradores/estrutura.py` — F2.1 (paredes + laje + escada + cobertura + forro)**: porta fiel do `gerarPecas` do v7 lendo `planta_normalizada` + `perfil_lsf`/`regra_lsf`/`guia_de`/`verga_escalonamento` (migração 006 corrigiu os perfis pós-override); migração 008 traz os inputs de projeto dos 4 sistemas horizontais (o footprint NÃO é input: deriva das paredes externas, D3). `gerar_estrutura` soma os 5 sistemas. **O kg líquido bate com o gerador do v7 em 0,0% sistema a sistema** (parede 7.737 · laje 11.599 · cobertura 3.031 · forro 1.082 · escada 224 = 23.673 kg) — oráculo em `tests/fixtures/estrutura_v7_109_1506.json`, gerado por `tools/extrair_estrutura_v7.mjs`. `derivar_quantitativos` grava kg comprado na folha 03.01 como PARAMETRICO (confiança nunca melhor que `estimado`; hoje sai `parametrico`, herdada da laje). Sistema ausente é escopo → alerta, não exceção.
- **LACUNA ABERTA do kg comprado (bloqueia o aceite da Fase 2 — decisão humana)**: o critério abaixo pede ≤10% vs os **31.345 kg comprados da obra**. Nosso nesting global dá 25.710 (**-18,0%**) e o **próprio v7 headless dá 27.412 (-12,5%)** — ou seja, *nenhuma porta fiel do gerador alcança o comprado da obra*. A diferença não é geometria (o líquido bate exato), é o **modelo de perda/compra**: a obra comprou 32,4% sobre o líquido; o nesting em barra de 6 m rende 8,6% (global) ou 15,8% (por sistema). Fechar isso é calibração contra obra (R6). Travado por `tests/test_aceite_estrutura_completa.py::test_lacuna_do_kg_comprado_vs_obra_esta_medida`.
- **`tools/bridge_autosinapi.py`**: ponte staging AutoSINAPI → nosso schema, IDEMPOTENTE (reload mensal integral da analítica, upsert de preço; testada com 3 execuções). Staging alinhado ao DataModel.md real do upstream (`precos_insumos_mensal`, PK com regime). Pin: commit `0020609`. Migração 003 impõe UNIQUE em `composicao_item` (item duplicado = erro de escrita, não preço dobrado). Colheita de referências aplicada e licenças verificadas: docs/05.
- **Migração 004 — `planta_normalizada`** (Fase 2, estágio 1): `nivel`/`no_planta`/`parede`/`vao` como grafo (cantos=nós, paredes=arestas; conceito Raster-to-Graph, zero código — sem licença). Regras de panelização da colheita viraram dados em `regra_lsf` (`largura_painel_max_m` 3,6 · `painel_comp_max_transporte_m` 6,0 · `junta_folga_vao_m` 0,30 · `largura_painel_min_m` 0,60).
- **Decisão SINAPI tomada** (docs/03): Rota A condicional — AutoSINAPI (GPLv3) como serviço isolado em container; a ponte é nossa. Gate pendente: smoke test com 1 arquivo real da Caixa na máquina do usuário.
- **`app/` — casca web (FastAPI + Jinja + htmx)**: login (scrypt + sessão assinada), projetos, quantitativos MANUAL na árvore da EAP, tela de orçamento (KPIs, faixas D4, pendências D4.1, gate R7) e proposta publicada em `/p/<token>` com **snapshot congelado** (o cliente vê o que foi publicado; preço que mude depois não reescreve a proposta). `app/` NÃO contém regra de engenharia: número na UI que não veio de motor é bug de arquitetura. Publicação recusa (409) com macroetapa zerada ou pendência de custo. Migração 005: `usuario`, `proposta`. Sobe com `run_app.py` (exige `LSF_SECRET`); usuário via `tools/criar_usuario.py`. Licenças das deps web em docs/04 (todas permissivas; htmx vendored BSD-2).
- **`db/build_db.py` é não-destrutivo**: schema e migrações aplicados uma vez via `schema_migrations`; seed reaplicado idempotente (é assim que conhecimento novo chega a banco existente). `--recriar` apaga, e só ele.
- **Ambiente**: não há python no PATH deste workspace; usar `.venv/bin/python` (criado do nix store) com `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib` (numpy). Node headless: `/nix/store/0akvkk9k1a7z5vjp34yz6dr91j776jhv-nodejs-20.11.1/bin/node`. Git: `origin=github.com/cassioviller/lsf-sistemazip`.

## Decisões de arquitetura TRAVADAS (não reabrir sem motivo forte — detalhes em docs/01 §2)

- **D1 — EAP única**: orçamento e cronograma leem a mesma EAP; curva S fecha por construção.
- **D2 — `quantitativo` é o ponto de convergência**: modos paramétrico/executivo diferem só na `origem` (PARAMETRICO|TAKEOFF|MANUAL). Migração proposta→contrato = trocar linhas.
- **D3 — Cadeia de inferência**: arquitetônico → paredes → estrutura (kg, m²) → cargas → fundação → SINAPI.
- **D4 — Confiança propagada**: todo dado derivado carrega `real|estimado|parametrico`; cada estágio herda a PIOR confiança dos inputs; baixa confiança vira faixa (±%), nunca valor seco.
- **D5 — Versionamento por data-base**: projeto trava versão; orçamento antigo nunca muda sozinho.
- **D6 — Motores são funções puras** sobre o banco. Zero acoplamento a framework web. Testáveis isolados.
- **D7 — SINAPI é camada de mapeamento, não de lógica**: LSF estrutural = composições próprias (SINAPI não cobre; drywall sim — caderno oficial, ex. 96359/96114).
- **D8 — Stack**: Python + SQLite (→Postgres quando doer) + saídas HTML/planilha/docx identidade Veks.

Decisões complementares tomadas na Fase 1 (mesma força das D1–D8):
- **D5.1 — Projeto trava REFERÊNCIA (YYYY-MM + uf + desonerado), não `data_base_id`**: cada insumo é precificado na data-base da SUA fonte naquela referência (base da UF ganha da nacional). É o que permite composição própria (D7) misturar material VEKS com mão de obra SINAPI. Assinatura: `custo_composicao(con, composicao_id, referencia, uf, desonerado)`.
- **D4.1 — Dado ausente é ERRO, não zero nem custo parcial**: insumo sem preço, composição sem analítica ou mapeamento NULL viram `CustoIndisponivel`/pendência, e o total do orçamento fica `None` até resolver. Confiança etiqueta incerteza; ausência derruba.

## Política de licenças (OBRIGATÓRIA — docs/02 §3-I4)

MIT/Apache/BSD → pode embutir (ezdxf MIT ✓). GPL (AutoSINAPI, TF2DeepFloorplan) → SOMENTE processo/container isolado; nenhuma linha no código proprietário; a fronteira é o banco de staging. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO; conceitos/papers liberados. Antes de qualquer dependência nova: verificar licença e registrar em docs/04.

## Física e domínio (aprendizados que custaram caro — não perder)

- LSF é LEVE: parede típica ~41 kg/m², carga ~5 kN/m no térreo. Consequência provada no spike 4: **fundação governada pelo mínimo construtivo** (`largura = max(teorica, 0.30m)`), não pela tensão do solo. Verificação de ancoragem/arrancamento por vento pode governar antes da compressão — implementar na Fase 3, mas a fórmula exige revisão com engenheiro estrutural (única dependência humana externa do plano).
- Solo é o input que o arquitetônico não dá: classe S1–S5 com tensão presumida conservadora + flag "sondagem pendente" que rebaixa a confiança de toda a fundação. S1 BLOQUEIA pré-dimensionamento.
- Panelização: junta NUNCA a menos de 30cm da lateral de um vão (montante duplo do vão × montante de emenda). Comprimento máx. por transporte/manuseio é parâmetro (ref. 6,0 m).
- O produto emite PRÉ-DIMENSIONAMENTO para orçamento, nunca projeto. Disclaimer + gates jurídico-técnicos (sondagem, ART, verificação estrutural) são mecanismo, não rodapé.
- Gate de completude turn-key: macroetapa da EAP zerada bloqueia geração de proposta (escopo vazado em preço fechado = prejuízo).

## Estrutura da pasta

```
CLAUDE.md               ← você está aqui (fonte de verdade)
PROMPT_INICIAL.md       ← primeira mensagem sugerida p/ a sessão (Fase 1, já executada)
docs/01..05             ← plano v1, plano validado v2, decisão SINAPI, referências/colheita
docs/superpowers/       ← specs (brainstorming) e plans (writing-plans) gerados pelas skills
db/                     ← schema.sql, seed.sql, migrations/ (001..005), build_db.py (não-destrutivo)
app/                    ← casca web FastAPI+Jinja+htmx: rotas/, servicos/, templates/, static/
run_app.py              ← sobe o app (exige LSF_SECRET; constrói/atualiza o banco no boot)
tests/                  ← 123 testes: spikes (regressão), motor, aceite F1, app + fixtures/
tools/                  ← bridge_autosinapi.py, carregar_orcamento_v7.py, criar_usuario.py
src/lsf/motores/        ← orcamento.py (Fase 1 ✓), cronograma.py, cargas.py (stubs com contratos)
src/lsf/relatorios.py   ← CSV/HTML analítico com faixas D4
saida/                  ← relatórios gerados (orcamento_109_1506.html/csv)
assets/calc-...v7.html  ← calculador v7 (READ-ONLY: fonte das regras já portadas; consultar, não editar)
```

## Fase atual: FASE 2 — Cadeia de inferência paramétrica (estágios 1–3)

(Fase 1 concluída: aceite em `tests/test_aceite_fase1.py`, desvio 0,00% vs orçamento v7 da 109.1506 — quantidades e preços oficiais da obra, quantitativos MANUAL. Ressalva honesta: preços e quantidades vieram da mesma referência; o que o aceite prova é o pipeline quantitativo→composição→EAP→BDI. Calibração de coeficientes contra obra segue pendente — R6.)

Implementar (docs/02 §4, Fase 2):
1. ~~Portar o gerador de estrutura do v7~~ **FEITO** (paredes + laje + escada + cobertura + forro): kg líquido do edifício = 23.673 kg, 0,0% vs v7 sistema a sistema. **Mas o kg comprado não fecha o critério** (-18,0% vs a obra; o v7 headless também não fecha, -12,5%) — ver "LACUNA ABERTA" acima. Pendente de decisão humana: calibrar a perda contra obra (R6) e/ou rever o critério, já que ele não é alcançável por porta fiel.
2. Schema da `planta_normalizada` (paredes/vãos/níveis com confiança) + entrada manual/assistida.
3. Motor de takedown de cargas por parede real (generalizar spike 4), escrevendo `quantitativo` origem=PARAMETRICO.

**Critério de aceite**: kg de aço da 109.1506 com desvio ≤ 10% vs v7 (referência headless: 23.673 kg líquido / 31.345 kg comprado, em `tests/fixtures/orcamento_v7_109_1506.json`); cargas por parede validadas contra 1 obra com projeto estrutural (R9).

Depois: Fase 3 (fundação + gates), Fase 4 (cronograma + curva S, validação ProjectLibre), Fase 5 (saídas, croqui, panelizador com romaneio, migração PARAMETRICO→TAKEOFF). Sequência completa em docs/02 §4.

## Fluxo de trabalho: Superpowers (skills) + as regras deste projeto

Este projeto usa o plugin **Superpowers** (`obra/superpowers`, MIT). As skills disparam sozinhas: `brainstorming` antes de qualquer trabalho criativo → `writing-plans` → `subagent-driven-development` (ou `executing-plans`) → `requesting-code-review` → `finishing-a-development-branch`; mais `test-driven-development`, `systematic-debugging` e `verification-before-completion` como leis de fundo. Siga as skills — MAS este arquivo tem precedência sobre elas (a própria `using-superpowers` diz: "User instructions (CLAUDE.md) take precedence over skills"). Onde há atrito, valem as regras abaixo.

**Onde os artefatos vivem** (defaults do plugin, mantidos de propósito — `docs/01..05` continua sendo doc curada à mão):
- Specs do `brainstorming`: `docs/superpowers/specs/YYYY-MM-DD-<tema>-design.md` (commitados).
- Planos do `writing-plans`: `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`.
- `.superpowers/` e `.worktrees/` já estão no `.gitignore` — não commitar, não "consertar" o .gitignore.

**Overrides deste projeto sobre o comportamento padrão das skills:**

1. **O gate de fase vence a execução contínua.** A `subagent-driven-development` manda "execute todas as tarefas do plano sem parar para checar com o humano". Aqui isso só é aceitável DENTRO de uma fase/estágio. Portanto: **um plano por fase (ou por estágio da fase)** — nunca um plano que atravesse o aceite de duas fases. O gate "nenhuma fase N+1 começa sem o aceite da fase N" mora na fronteira entre planos e é humano, não negociável.
2. **Comando de teste exato** (as skills chutam `pytest` puro e `poetry install` — ambos errados aqui): `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/`. Não existe python no PATH; não há poetry. Suíte inteira antes de **todo** commit — inclusive nos commits de fix despachados por subagente (a SDD permite rodar só o teste da mudança; aqui não permite).
3. **Branch e base**: trabalho em branch `fase<N>-<slug>` (ex.: `fase2-gerador-estrutura`), base sempre `main`. Nunca implementar direto na `main`.
4. **`finishing-a-development-branch` não fecha fase**: ela oferece merge/PR assim que as tarefas acabam. Merge é permitido; **o aceite da fase é outra coisa** — depende do critério numérico escrito na seção "Fase atual" e é declarado pelo humano.
5. **Revisão de licença é obrigatória e as skills não a fazem**: nenhum rubrico de review do Superpowers olha proveniência de código ou licença de dependência. Por isso ela entra no bloco de constraints abaixo, que é o único canal que a SDD garante copiar verbatim para todo implementador e todo revisor.

### Global Constraints — copiar VERBATIM na seção `## Global Constraints` de todo plano

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origemRegra`).

Planos precisam de títulos de tarefa na forma literal `### Task N: <nome>` — o script `task-brief` do Superpowers extrai por regex e falha silenciosamente com qualquer outro formato. Fase/estágio é agrupamento ACIMA das tarefas, nunca renomeia o heading.

## Convenções de trabalho

- Português nos nomes de domínio (tabelas, funções de negócio), como já está no schema.
- Todo número derivado carrega origem e confiança — sem exceção.
- Nenhuma fase N+1 começa sem o aceite da fase N (docs/02 §4) — e isso vence a execução contínua da SDD (ver acima).
- Suíte inteira verde antes de qualquer commit (comando exato acima); novos motores ganham testes no mesmo commit. TDD de verdade: teste vermelho pelo motivo certo, depois verde.
- Coeficientes e produtividades novos entram como `estimado` com fonte anotada; viram `real` só com calibração de obra (109.1506 e Baias Kabod são os casos de calibração).
- Ao tocar em regra de engenharia (cargas, fundação, vento): anotar a referência normativa no código, como o v7 fazia (`origemRegra`).

## O que NÃO fazer

- Não reabrir D1–D8 nem a decisão da Rota A sem evidência nova.
- Não embutir código GPL ou sem licença (ver política acima).
- Não pular para o modo paramétrico antes do aceite da Fase 1.
- Não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão (sempre via schema/seed/build).
- Não transformar disclaimers em texto morto: gates bloqueiam, não avisam.
- Não deixar um plano do Superpowers atravessar o aceite de duas fases, nem deixar a SDD "seguir em frente" por cima de um gate de fase.
- Não despachar subagente sem o bloco de Global Constraints: ele não vê o histórico da sessão nem este arquivo por osmose — sem o bloco, o implementador embute GPL e o revisor reprova nome em português.
