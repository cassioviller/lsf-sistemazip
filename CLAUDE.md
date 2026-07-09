# CLAUDE.md — Sistema de Orçamento e Cronograma Físico-Financeiro LSF (Veks Engenharia)

Você está trabalhando no sistema que transforma um projeto arquitetônico (DXF/DWG/croqui) em: quantitativos derivados por cadeia de inferência física, orçamento com base SINAPI + composições próprias, cronograma com caminho crítico (CPM) e curva S físico-financeira — para obras turn-key em Light Steel Frame. Este arquivo é a fonte de verdade do projeto; os detalhes estão em `docs/`.

## Estado atual (o que JÁ existe e funciona — não reescrever, evoluir)

- **`db/schema.sql` + `db/seed.sql`**: base de conhecimento multi-fonte versionada por data-base. 12 fontes cadastradas, 20 perfis LSF (portados do v7 em `assets/`), 9 regras NBR 15758, pesos por camada, 5 classes de solo, 4 composições próprias exemplo, mapeamento item→composição. `python3 db/build_db.py` constrói `lsf_base.db`. A view `vw_custo_composicao` já precifica com propagação de confiança.
- **`tests/spikes_validacao.py`**: 6 spikes que provaram cada elo (DXF→eixos, CPM, Curva S + BDI TCU, takedown de cargas via banco, panelizador junta×vão, cadeia item→custo). São a suíte de regressão — `pytest tests/` deve passar SEMPRE. Se um spike quebrar, o commit está errado.
- **`tools/bridge_autosinapi.py`**: ponte staging AutoSINAPI → nosso schema, provada fim-a-fim (SINAPI 96359 custeando a R$ 99,55/m² pela view).
- **Decisão SINAPI tomada** (docs/03): Rota A condicional — AutoSINAPI (GPLv3) como serviço isolado em container; a ponte é nossa. Gate pendente: smoke test com 1 arquivo real da Caixa na máquina do usuário.

## Decisões de arquitetura TRAVADAS (não reabrir sem motivo forte — detalhes em docs/01 §2)

- **D1 — EAP única**: orçamento e cronograma leem a mesma EAP; curva S fecha por construção.
- **D2 — `quantitativo` é o ponto de convergência**: modos paramétrico/executivo diferem só na `origem` (PARAMETRICO|TAKEOFF|MANUAL). Migração proposta→contrato = trocar linhas.
- **D3 — Cadeia de inferência**: arquitetônico → paredes → estrutura (kg, m²) → cargas → fundação → SINAPI.
- **D4 — Confiança propagada**: todo dado derivado carrega `real|estimado|parametrico`; cada estágio herda a PIOR confiança dos inputs; baixa confiança vira faixa (±%), nunca valor seco.
- **D5 — Versionamento por data-base**: projeto trava versão; orçamento antigo nunca muda sozinho.
- **D6 — Motores são funções puras** sobre o banco. Zero acoplamento a framework web. Testáveis isolados.
- **D7 — SINAPI é camada de mapeamento, não de lógica**: LSF estrutural = composições próprias (SINAPI não cobre; drywall sim — caderno oficial, ex. 96359/96114).
- **D8 — Stack**: Python + SQLite (→Postgres quando doer) + saídas HTML/planilha/docx identidade Veks.

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
PROMPT_INICIAL.md       ← primeira mensagem sugerida p/ a sessão
docs/01..04             ← plano v1, plano validado v2, decisão SINAPI, referências/colheita
db/                     ← schema.sql, seed.sql, build_db.py (gera lsf_base.db)
tests/                  ← spikes (regressão) + test_regressao.py
tools/bridge_autosinapi.py
src/lsf/motores/        ← orcamento.py, cronograma.py, cargas.py (stubs com contratos)
assets/calc-...v7.html  ← calculador v7 (READ-ONLY: fonte das regras já portadas; consultar, não editar)
```

## Fase atual: FASE 1 — Motor de orçamento

Implementar em `src/lsf/motores/orcamento.py`:
1. `custo_composicao(con, composicao_id, data_base_id)` — recursivo (item_tipo=COMPOSICAO), retorna (custo, confianca) com confiança = pior componente. A view cobre 1 nível; o motor resolve aninhamento.
2. Tabelas de projeto (schema já previsto em docs/01 §4): `projeto`, `quantitativo` com `origem`.
3. `custo_direto_projeto` agregando por hierarquia da EAP.
4. `aplicar_bdi` (fórmula TCU do spike 3) → preço de venda por linha e total.
5. Relatório analítico (planilha/HTML) com coluna de confiança e faixas para itens `estimado`.

**Critério de aceite da fase**: reproduzir 1 orçamento real da Veks com desvio ≤ 2%, com quantitativos digitados manualmente (isola erro de preço de erro de regra — por isso orçamento vem antes do paramétrico).

Depois: Fase 2 (adaptador DXF completo + gerador de estrutura portado do v7 + takedown por parede real), Fase 3 (fundação + gates), Fase 4 (cronograma + curva S, validação cruzada com ProjectLibre), Fase 5 (saídas, croqui, panelizador com romaneio, migração PARAMETRICO→TAKEOFF). Sequência e aceites completos em docs/02 §4.

## Convenções de trabalho

- Português nos nomes de domínio (tabelas, funções de negócio), como já está no schema.
- Todo número derivado carrega origem e confiança — sem exceção.
- Nenhuma fase N+1 começa sem o aceite da fase N (docs/02 §4).
- `pytest tests/` antes de qualquer commit; novos motores ganham testes no mesmo commit.
- Coeficientes e produtividades novos entram como `estimado` com fonte anotada; viram `real` só com calibração de obra (109.1506 e Baias Kabod são os casos de calibração).
- Ao tocar em regra de engenharia (cargas, fundação, vento): anotar a referência normativa no código, como o v7 fazia (`origemRegra`).

## O que NÃO fazer

- Não reabrir D1–D8 nem a decisão da Rota A sem evidência nova.
- Não embutir código GPL ou sem licença (ver política acima).
- Não pular para o modo paramétrico antes do aceite da Fase 1.
- Não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão (sempre via schema/seed/build).
- Não transformar disclaimers em texto morto: gates bloqueiam, não avisam.
