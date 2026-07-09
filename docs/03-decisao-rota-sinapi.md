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
