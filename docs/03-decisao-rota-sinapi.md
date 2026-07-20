# Registro de Decisão — Importação SINAPI (Rota A vs Rota B)
**Data:** 08/07/2026 · **Decisão:** ROTA A CONDICIONAL — AutoSINAPI como serviço isolado, com ponte própria

## Evidências coletadas (executadas hoje)

1. **Suíte de testes do AutoSINAPI: 35/35 aprovados** neste ambiente (único teste excluído exige o arquivo real da Caixa, indisponível aqui por restrição de rede — não por defeito do projeto).
2. **Schema deles mapeia 1:1 no nosso:** `insumos→insumo`, `precos_insumos (uf, data, regime)→data_base+insumo_preco`, `composicoes→composicao`, `composicao_insumos→composicao_item(INSUMO)`, `composicao_subcomposicoes→composicao_item(COMPOSICAO)`. Eles modelam aninhamento e versionamento (sinapi_versao, etl_run_id) de forma compatível com nossas decisões D5/D7.
3. **Ponte implementada e provada: 54 linhas** (`bridge_autosinapi.py`). Teste fim-a-fim: staging → nosso banco → view precifica a composição SINAPI 96359 a R$ 99,55/m² com confiança `real`.
4. **Critério do plano atendido:** integração em muito menos de 1 dia.

## Condições da adoção (Rota A)

- **Isolamento GPL:** AutoSINAPI roda em container/processo separado (compatível com a infraestrutura Docker/Postgres já existente no SIGE). Nenhuma linha GPL entra no código proprietário; a fronteira é o banco de staging.
- **Gate de 10 minutos pendente (única verificação fora deste ambiente):** rodar o pipeline com **um arquivo real** `SINAPI_Referência_AAAA_MM.xlsx` baixado da Caixa, na máquina do Cássio. Se o parser alpha falhar no arquivo real → aciona Rota B sem redesenho (ver abaixo).
- **Postgres obrigatório** para o serviço (já disponível em produção).

## Por que a Rota B permanece viva sem custo

A ponte é **nossa** e é a costura do sistema: ela lê tabelas de staging, não o AutoSINAPI em si. Se o upstream quebrar ou o projeto morrer, escrevemos nosso parser (formato já caracterizado: pandas + abas ISD/ICD/ISE/CSD/CCD/CSE + "Analítico") alimentando **as mesmas tabelas de staging** — a ponte e todo o resto do sistema não mudam uma linha. Rota B é um drop-in atrás da ponte, não um plano paralelo.

## Efeito no backlog

- Item 1 (decisão A/B): **concluído**.
- Item 2 (importar SINAPI SP): vira "subir AutoSINAPI em container + rodar gate de 10 min + executar ponte" — estimativa reduzida de dias para horas.
- Novo item: fixar versão/commit do AutoSINAPI usado (pin) e documentar o procedimento de atualização mensal.

---

## Runbook do smoke test — e as 3 lacunas entre ele e o destravamento do R7

*(escrito em 2026-07-20, quando ficou claro que o gate R7 espera SINAPI e não dado da Veks — ver CLAUDE.md. Auditado contra o código, não contra a memória.)*

**Passo 0 — sanity check, roda aqui e agora** (verificado em 2026-07-20):

```
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python tools/bridge_autosinapi.py
# PONTE OK ✓ (2x, idempotente)  SINAPI 96359 ... → R$ 99.55/m² [real]
```

Isso prova a ponte **contra o staging-fixture em SQLite**. É o que está provado hoje — nada além.

### Lacuna 1 — a ponte fala SQLite; o staging de produção é Postgres

`executar_ponte(st, db)` consulta o staging com placeholders `?` e `SELECT * FROM insumos`
(`tools/bridge_autosinapi.py`). Postgres/psycopg usa `%s`. Não há psycopg neste ambiente
(verificado: `ModuleNotFoundError` para `psycopg` e `psycopg2`). Ou seja: **"executar a ponte"
contra o container não funciona como está escrito.** Duas saídas, ambas baratas:

- **(a) Dump staging → SQLite** e apontar a ponte para o arquivo. Não toca no código; é o
  caminho de menor risco para o smoke test de 10 minutos.
- **(b) Parametrizar o placeholder** na ponte (um `paramstyle` no topo) + dependência psycopg
  (LGPL-3 no psycopg2 / Apache-2.0 no psycopg3 — **verificar e registrar em docs/04 antes**).
  É o caminho de produção, mas exige Postgres à mão para testar; não escrever no escuro.

### ~~Lacuna 2 — a ponte não importa subcomposições~~ FECHADA em 2026-07-20

A ponte lia **só** `composicao_insumos` e o reload apagava só `item_tipo='INSUMO'`, apesar de a
evidência 2 acima prometer o mapeamento. Composição SINAPI aninhada — a maioria das de
instalações/canteiro, justamente as macroetapas travadas no R7 — entrava incompleta.

Implementada por TDD (4 testes em `tests/test_bridge.py`, vermelhos primeiro):
- `composicao_subcomposicoes` no staging-fixture; 96114 (forro drywall) aninha a 96359;
- o custo **atravessa** o aninhamento: 96114 = 1,0 × 96359 = R$ 99,55/m², confiança `real`;
- o DELETE do reload passou a apagar os **dois** `item_tipo` — filtrar só INSUMO fazia o
  vínculo acumular a cada execução (o mesmo bug de duplicação já corrigido p/ insumos);
- subcomposição fora do catálogo é **pulada, não inventada** (par do teste que já existia
  para INSUMO), e a filha inexistente não vira zero;
- D4.1 provado no aninhamento: sem preço na filha, o pai levanta `CustoIndisponivel`
  (`"insumo 10774, usado por 96359, sem preço"`) — nunca custo parcial.

O CLI da ponte também prova o aninhamento: `aninhamento ✓ 96114 → 96359 (1 vínculo)`.

### Lacuna 3 — importar SINAPI NÃO cria as composições de 01/05/07/08 sozinho

A ponte pula composição fora do nosso catálogo (`if comp is None: continue` — "pulada, não
inventada", e está certa em fazê-lo). Então o import popula insumos e preços, mas as macroetapas
**01, 05, 07 e 08 continuam sem folha e sem composição**. Destravar o R7 exige, depois do import:

1. escolher os códigos SINAPI de cada grupo (preliminares, instalações, complementares, canteiro);
2. inseri-los em `composicao` (fonte SINAPI) e criar as folhas de EAP correspondentes — via
   **seed/migração**, nunca na mão no `.db`;
3. apagar `tests/test_app_proposta.py::test_eap_de_fabrica_nao_publica_ate_as_4_composicoes_existirem`
   (ele existe para falhar nessa hora) e escrever o teste do caminho feliz sobre a EAP real.

O passo 1 é decisão de ESCOPO da Veks (o que entra em "serviços preliminares" de uma obra
turn-key LSF), não escolha técnica — por isso não está pré-preenchido aqui.
