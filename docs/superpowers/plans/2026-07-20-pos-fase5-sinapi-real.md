# Plano — Pós-Fase 5: do seed de demonstração ao SINAPI real

**Data:** 2026-07-20 · **Base:** `main` @ `bbd80a8` · **Branch:** `fase6-sinapi-real`

## Contexto

A Fase 5 fechou o pipeline (planta → estrutura → orçamento → cronograma → romaneio →
saídas). O que falta não é motor: é **base de preços**. Hoje o banco tem 5 composições
Veks + 2 SINAPI + 11 insumos com preço — seed de demonstração. E o gate R7 bloqueia a
publicação de TODO projeto porque as macroetapas 01/05/07/08 não têm composição
(travado em `tests/test_app_proposta.py::test_eap_de_fabrica_nao_publica_...`).

Por **D7**, essas 4 são escopo SINAPI, não composição própria. Logo tudo converge no
import do SINAPI real — cujo caminho tem 3 lacunas mapeadas em `docs/03`.

**Isto NÃO é uma fase nova com aceite próprio**: é a fila de lacunas de DADO que
destrava aceites já dados (R6/R9). O gate de fase do CLAUDE.md não se aplica; o que
se aplica é: nenhuma Task que dependa de dado externo começa antes do dado chegar.

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
| 1. Subcomposições na ponte | nada | **SIM** |
| 2. Ponte agnóstica de paramstyle | nada p/ escrever; Postgres p/ provar | **SIM (parcial)** |
| 3. Smoke test da Rota A | arquivo da Caixa + Docker (Cássio) | não |
| 4. Composições dos 4 grupos + destravar R7 | Task 3 + decisão de escopo Veks | não |
| 5. Calibração R6 | obra real com custos fechados | não |

---

### Task 1: Subcomposições na ponte (`composicao_subcomposicoes` → `item_tipo='COMPOSICAO'`)

**Desbloqueada. É a única Task que produz código hoje.**

O `docs/03` promete o mapeamento `composicao_subcomposicoes → composicao_item(COMPOSICAO)`,
mas `executar_ponte` lê só `composicao_insumos` e o reload apaga só `item_tipo='INSUMO'`.
Composição SINAPI aninhada — que é a maioria das de instalações/canteiro — entra
incompleta. O schema já suporta (`composicao_item.item_tipo`) e o `custo_composicao` já
é recursivo com detecção de ciclo; falta só a ponte alimentar.

- TDD: primeiro o teste vermelho. Estender `criar_staging_fixture` com a tabela
  `composicao_subcomposicoes` (nomes conforme DataModel.md do upstream) e uma composição
  pai que referencia a 96359 como filha.
- Implementar o import: mesmo padrão de reload integral (DELETE+INSERT), agora cobrindo
  os dois `item_tipo`. Atenção: o DELETE atual filtra `item_tipo='INSUMO'` — passar a
  apagar ambos, senão o reload mensal deixa subcomposição órfã.
- Manter a regra de ouro da ponte: **subcomposição fora do nosso catálogo é PULADA, não
  inventada** (é o que `test_ponte_ignora_composicao_fora_do_catalogo` já guarda p/ INSUMO —
  escrever o par para COMPOSICAO).
- Provar que a idempotência sobrevive: rodar 2× e conferir custo, como os testes atuais.
- Caso de borda que D4.1 exige testar: pai aninhado cuja filha não tem preço → o custo do
  pai vira `CustoIndisponivel`, nunca custo parcial.

### Task 2: Ponte agnóstica de paramstyle (SQLite ↔ Postgres)

`executar_ponte` consulta o staging com placeholders `?`; psycopg usa `%s`. Não há psycopg
neste ambiente. Hoje a ponte só lê staging SQLite — o staging de produção é Postgres.

- Escrever a abstração de paramstyle **e provar contra SQLite** (a suíte roda aqui).
  Nada de driver novo enquanto não houver Postgres à mão para testar de verdade.
- **Antes de adicionar psycopg**: verificar licença e registrar em docs/04. psycopg2 é
  LGPL-3, psycopg3 é Apache-2.0 — a escolha tem consequência de política, não é detalhe.
- Não marcar esta Task como concluída sem execução contra Postgres real: código de driver
  não testado é dívida disfarçada de feature. Até lá, a saída (a) do runbook — dump do
  staging para SQLite — é o caminho oficial do smoke test.

### Task 3: Smoke test da Rota A com arquivo real da Caixa

**Ação do Cássio; máquina dele.** É o gate que decide se a Rota A sobrevive ou se a Rota B
(nosso parser) é acionada — e o `docs/03` já garante que Rota B é drop-in atrás da ponte.

- Passo 0 do runbook (`docs/03`), já verificado aqui: `.venv/bin/python tools/bridge_autosinapi.py`
  → `96359 → R$ 99,55/m²`, idempotente. Isso prova a ponte contra fixture, nada além.
- Subir AutoSINAPI **em container isolado** (fronteira GPL: nenhuma linha deles no nosso
  código — a fronteira é o staging) com um `SINAPI_Referência_AAAA_MM.xlsx` real.
- Dump do staging → SQLite → apontar a ponte. Conferir: nº de insumos, nº de composições,
  e o custo de uma composição conhecida contra o site da Caixa.
- Parser alpha falhou no arquivo real? → aciona Rota B, sem redesenho.

### Task 4: Composições dos 4 grupos + destravar o R7

Depende da Task 3 **e** de uma decisão de escopo que é comercial, não técnica: o que entra
em "serviços preliminares", "instalações", "serviços complementares" e "canteiro" numa obra
turn-key LSF da Veks. Sem essa lista, qualquer código SINAPI que eu escolher é chute com
cara de referência.

- Escolher os códigos SINAPI de cada grupo (decisão Veks, registrada com justificativa).
- Inseri-los em `composicao` (fonte SINAPI) e criar as folhas de EAP — **via migração**,
  nunca na mão no `.db`.
- Rodar a ponte: os preços chegam como `real`.
- **Apagar** `test_eap_de_fabrica_nao_publica_ate_as_4_composicoes_existirem` — ele existe
  para falhar nesta hora — e escrever o teste do caminho feliz sobre a EAP REAL.
- Revisar a fixture `projeto_completo`: com a EAP real completa, o arranjo das folhas `.99`
  deixa de ser necessário e vira maquiagem. Remover.
- Verificar no servidor real: publicar um projeto ponta a ponta, 303 e não 409.

### Task 5: Calibração R6 — coeficientes de `estimado` para `real`

Depende de obra com custos fechados (109.1506, Baias Kabod). É lacuna de DADO, a mais
antiga do projeto, e destrava a honestidade dos aceites das Fases 1–4.

- Confrontar coeficientes das composições próprias (VK-C-001..005) contra consumo real.
- Coeficiente confirmado sobe para `real`; divergente é corrigido COM a divergência
  anotada — o que se aprendeu é mais valioso que o número novo.
- O baldrame VK-C-005 (~R$ 1.542/m³, coef. `estimado` em ordem SINAPI) é o mais frágil.
- Ao subir confiança, conferir que a propagação D4 reflete na proposta: item que era faixa
  ±% e vira valor seco tem que mudar na tela e no `.docx`.
- Fechar aqui o aceite ±15% da Fase 3, que ficou como lacuna de dado.

## Sequência e paralelismo

Tasks 1 e 2 são independentes e rodam agora, sem esperar ninguém. A 3 é gate: destrava
4 e influencia 2. A 5 é ortogonal — entra quando a obra chegar, em qualquer momento.

```
Task 1 ─┐
Task 2 ─┴─────→ (nada bloqueia)
Task 3 ───────→ Task 4 ───→ produto publica proposta
Task 5 ───────→ (independente; chega com a obra)
```

## O que este plano NÃO faz

Não inventa coeficiente, código SINAPI ou preço para preencher as 4 macroetapas. Foi
exatamente essa tentação que a política de confiança do projeto existe para barrar: número
plausível sem fonte entra em proposta para cliente real e vira prejuízo com cara de
orçamento. Preferimos o gate bloqueando a publicação a um preço fechado com escopo vazado.
