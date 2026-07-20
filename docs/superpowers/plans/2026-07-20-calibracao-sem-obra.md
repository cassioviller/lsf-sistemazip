# Plano — Calibração SEM obra: SINAPI oficial como oráculo, `estimado` honesto onde não há

**Data:** 2026-07-20 · **Base:** `main` (após `e15a39d`) · **Branch:** `fase6-calibracao-sem-obra`

## O fato que dispara este plano

A Veks **não tem, e não terá, dados de obra medidos** (decisão do usuário, 2026-07-20). A R6
como o projeto a definiu — coeficiente `estimado` vira `real` confrontando consumo da
109.1506 / Baias Kabod — **não vai acontecer**. Isso não é atraso: é uma premissa que caiu.
Vários aceites assumiam esse oráculo (o ±15% da Fase 3, a promoção de confiança das VK-C-*).

Este plano NÃO inventa o dado que falta. Ele **realinha a estratégia de confiança** ao que
existe de fato, seguindo o D7:

- **Onde o SINAPI cobre o serviço** → a composição oficial da Caixa é o oráculo, e o projeto
  já a trata como `real` (a ponte grava preço SINAPI com `confianca='real'`). Migrar para ela.
- **Onde o SINAPI NÃO cobre** (LSF estrutural, D7) → o coeficiente fica `estimado` **para
  sempre**. A honestidade disso é a faixa ±% na proposta (D4), não uma promessa de calibração
  futura. Dado público secundário (docs/06) melhora a proveniência, nunca promove a `real`.

**Isto não é fase com aceite numérico próprio** — é realinhamento de política de dado +
trabalho que destrava aceites antigos. O gate de fase do CLAUDE.md não se aplica; aplica-se:
Task que dependa de SINAPI real não começa antes do smoke test da Rota A.

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origemRegra`).

## Estado de bloqueio (ler antes de pegar uma Task)

| Task | Depende de | Pode começar hoje? |
|---|---|---|
| 1. Realinhar a política de confiança na doc e no código | nada | **SIM** |
| 2. Classificar cada composição: SINAPI-cobre vs LSF-próprio | nada (catálogo SINAPI ajuda, mas a classificação é por D7) | **SIM** |
| 3. Faixa ±% do `estimado` permanente — provar ponta a ponta na proposta | nada | **SIM** |
| 4. Migrar as SINAPI-cobre para composição oficial → `real` | Task 2 + SINAPI real (Rota A) | não |
| 5. Estreitar a faixa do LSF-próprio com dado público secundário | limite de gasto renovado (pesquisa web) | não agora |

---

### Task 1: Realinhar a política de confiança (doc + código que ainda diz "calibrar em obra")

O CLAUDE.md já recebeu o fato no topo de "Física e domínio". Falta varrer os pontos que
ainda prometem calibração de obra e reescrevê-los para a nova realidade — sem apagar a
história, marcando o que mudou:

- CLAUDE.md: as menções a R6 em "Seed VK-C-005 (...) calibrar R6", "±15% vs obra", "viram
  `real` só com calibração de obra (109.1506 e Baias Kabod)". Reescrever para: `real` vem do
  SINAPI oficial onde ele cobre; onde não cobre, `estimado` é permanente e honesto.
- Seed/observações das composições (`seed.sql`, via migração — nunca no `.db`): trocar
  "calibrar R6" por "SINAPI-cobre: migrar p/ oficial (Task 4)" ou "LSF-próprio: `estimado`
  permanente, faixa ±% (D4)", conforme a classificação da Task 2.
- Este é trabalho de honestidade documental, não de motor. Nenhum coeficiente muda aqui.

### Task 2: Classificar cada composição — SINAPI-cobre vs LSF-próprio (decisão D7)

Para cada folha da EAP e cada VK-C-*, decidir a que categoria pertence. A classificação é
por D7 (o que o SINAPI cobre), não por conveniência:

- **SINAPI-cobre** (candidatas): VK-C-004 placa cimentícia, VK-C-002 OSB, VK-C-003 membrana,
  VK-C-005 baldrame (concreto/forma/aço são serviços SINAPI clássicos), e as 4 macroetapas
  vazias 01/05/07/08 (preliminares, instalações, complementares, canteiro).
- **LSF-próprio, `estimado` permanente**: VK-C-001 (montagem de estrutura LSF) — o SINAPI não
  tem composição de montagem de painel LSF estrutural. É o núcleo do produto e o coeficiente
  mais material; sua incerteza é permanente e comunicada por faixa.
- Saída: uma tabela em docs/06 (ou docs nova) que carimba cada composição com a categoria e a
  consequência de confiança. Sem escrever código de motor.
- Cuidado: "SINAPI-cobre" não significa "já mapeada" — significa que EXISTE composição oficial
  para migrar quando o SINAPI real entrar (Task 4). A classificação pode ser feita hoje; a
  migração não.

### Task 3: A faixa ±% do `estimado` permanente tem que ser sólida na proposta

Se a montagem LSF (VK-C-001) é `estimado` **para sempre**, então a faixa ±% na proposta deixa
de ser estado transitório e passa a ser a postura permanente do produto no item mais caro. Ela
precisa estar impecável ponta a ponta:

- Verificar que o custo com VK-C-001 propaga `estimado` até o total (D4) e que a proposta —
  HTML, `.docx` e snapshot público `/p/<token>` — mostra **faixa ±%**, nunca valor seco, nesse
  item e em tudo que dele herda.
- Teste que fixa isso: projeto cuja estrutura LSF domina o custo → total sai como faixa, e a
  faixa aparece nos 3 canais de saída. Prova de mutação: se alguém trocar a propagação para
  mostrar valor seco, o teste quebra.
- Decidir e DOCUMENTAR o ±% de um `estimado` sem calibração de obra. Hoje o motor usa uma
  faixa; ela precisa de justificativa escrita agora que é permanente (não "até calibrar").
- Isto é o que protege o cliente e a Veks: o número mais incerto é o que mais aparece como
  faixa, honestamente.

### Task 4: Migrar as SINAPI-cobre para composição oficial → `real`

**Depende da Task 2 (classificação) e do SINAPI real (Rota A, smoke test — bloqueado).**

- Para cada composição classificada "SINAPI-cobre", escolher o código SINAPI oficial
  equivalente (decisão de escopo: o que a Veks considera cada serviço) e apontar a folha da
  EAP para ele — via migração, nunca no `.db`.
- Isso resolve DE UMA VEZ dois pendentes: (a) as 4 macroetapas vazias que travam o R7, e (b) a
  confiança `estimado` sem fonte das VK-C-* que o SINAPI cobre. Ambos viram `real` oficial.
- A ponte já importa insumo, preço e subcomposição (Tasks 1 e 2 do plano anterior, feitas). O
  que falta é o import rodar com arquivo real e as folhas apontarem para os códigos.
- Apagar `test_eap_de_fabrica_nao_publica_ate_as_4_composicoes_existirem` (existe para falhar
  nesta hora) e escrever o caminho feliz sobre a EAP real; remover o arranjo `.99` da fixture
  `projeto_completo`.

### Task 5: Estreitar a faixa do LSF-próprio com dado público secundário

**Depende do limite de gasto renovar** (a rodada de 2026-07-20 foi truncada — docs/06).

- Retomar a busca por produtividade de montagem LSF (h/kg ou h/m²): CBCA, teses brasileiras,
  fabricante. Objetivo: ESTREITAR a faixa ±% da VK-C-001 e DOCUMENTAR proveniência — nunca
  promover a `real` (dado secundário não é medição de obra; SINAPI não cobre LSF estrutural).
- Fechar os itens ABERTOS de docs/06: MO do baldrame (h/m³), OSB, membrana, parafuso/kg.
- Cada número entra `estimado` com URL da fonte; divergência entre fontes vira faixa, não média.

## Sequência

```
Task 1 ─┐
Task 2 ─┼──────→ (hoje, sem bloqueio)   Task 2 alimenta a 4
Task 3 ─┘
Task 4 ──── espera Rota A + escopo Veks ────→ produto publica proposta com preço SINAPI real
Task 5 ──── espera limite de gasto ────→ faixa do LSF-próprio mais estreita e documentada
```

## O que este plano NÃO faz, e por que

- **Não promove dado público secundário a `real`.** SINAPI OFICIAL é `real` (é a referência
  nacional que o projeto já aceita assim); blog, manual e geometria são `estimado`. A fronteira
  é primária-oficial vs secundária, não pública vs privada.
- **Não finge que o LSF estrutural vai calibrar.** Ele não vai — o SINAPI não o cobre e não há
  obra. `estimado` permanente com faixa honesta É a resposta certa, não uma pendência.
- **Não inventa coeficiente nem código SINAPI** para preencher lacuna. Gate bloqueando a
  publicação é melhor que preço fechado com escopo vazado.
