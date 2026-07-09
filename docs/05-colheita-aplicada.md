# Colheita aplicada — o que entrou no aplicativo (09/07/2026)

Licenças verificadas via API do GitHub em 09/07/2026 (não presumidas). Regra do
CLAUDE.md: MIT/Apache = pode embutir · GPL = só processo isolado · sem licença = só conceito.

## O que ENTROU agora

| Fonte | Licença verificada | O que entrou | Onde |
|---|---|---|---|
| LAMP-LUCAS/AutoSINAPI | GPLv3 declarada no README (badge + §Licença); **sem arquivo LICENSE na raiz** — pedir ao upstream. PIN: commit `0020609` (main) | Schema de staging alinhado ao `docs/DataModel.md` real deles: tabela `precos_insumos_mensal` (era `precos_insumos`), PK composta com `regime`; semântica de **reload mensal integral** da analítica → ponte reescrita idempotente (DELETE+INSERT por composição, upsert de preço). Zero código deles | `tools/bridge_autosinapi.py` + `tests/test_bridge.py` |
| Raster-to-Graph (CVPR'24) | **sem licença** → só conceito | Planta como **grafo**: cantos = nós, paredes = arestas, compartilhando nó no encontro (não pontos duplicados). É a estrutura da `planta_normalizada` da Fase 2 | migração `004_planta_normalizada.sql` (nivel, no_planta, parede, vao) + `tests/test_planta.py` |
| FRAMECAD / Vertex BD / StrucSoft MWF / Scottsdale | comerciais, zero código | Régua de auto-panelização como **dado versionado**: largura máx 3,6 m (v7/OBRA 1PV), comprimento máx transporte 6,0 m, junta ≥30 cm de vão, largura mínima 0,60 m (sem painel-lasca) | `regra_lsf` no seed (chaves `*painel*`, `junta_folga_vao_m`) |
| AutoSINAPI DataModel (PK pai+filho em `composicao_insumos`) | idem acima | UNIQUE em `composicao_item` — mata na raiz o bug de duplicação que dobrava preço em silêncio | migração `003_integridade_composicao.sql` |

## Correções de registro em docs/04 (licenças reais ≠ presumidas)

- **augustogoncalves/sinapi: MIT** (não só conceito — código aproveitável; POC Revit→custo de 2017, valor maior como referência de mapeamento modelo→custo p/ `mapeamento_item`).
- **opentakeoff = Kentucky-ai/opentakeoff, Apache-2.0** confirmado (Fase 5, croqui/PDF).
- **alfonsodipace/Critical-Path-Method: MIT** (nosso CPM do spike 2 já cobre; fica como leitura de conferência na Fase 4).
- **frappe/gantt: MIT confirmado** (candidato natural p/ UI Gantt na Fase 4). **DHTMLX/gantt: repo GitHub = MIT (edição standard)**, mas produto é dual GPL/comercial — se um dia usar além do standard, rever.
- **wikihouseproject/Skylark: SEM licença confirmado** → só conceito (biblioteca de blocos/nomenclatura/romaneio, Fase 5).
- **TF2DeepFloorplan: GPL-3.0 confirmado** → se um dia usar, processo isolado (ML é opcional por design).
- **IfcOpenShell: LGPL-3.0 confirmado** (uso como biblioteca respeitando termos; export IFC 4D/5D, Fase 5+).
- bidwright / orama-core / Raster-to-Graph: não reverificados nesta rodada (rate limit) — permanecem tratados como **sem licença** (só arquitetura/conceito).

## O que NÃO entrou agora — e para onde vai

- **Formato de shop drawings/romaneio (Skylark, comerciais)** → Fase 5 (panelizador com IDs, kit de corte, romaneio fábrica/obra). O spike 5 tem bugs conhecidos (loop infinito com vão largo perto da origem, junta negativa, painel-lasca) — o módulo da Fase 5 nasce das regras agora no banco, não do spike.
- **ProjectLibre como oráculo do CPM** → Fase 4 (aceite já prevê).
- **opentakeoff (calibração de escala em PDF)** → Fase 5 (croqui). Apache permite embutir quando chegar a hora.
- **TF2DeepFloorplan / Raster-to-Graph como motor de reconhecimento** → Fase 5+, "IA propõe, humano confirma"; a `planta_normalizada` (já criada) é o alvo comum de qualquer origem.
- **Diferencial confirmado**: nenhum dos quatro comerciais orça em SINAPI/BDI nem gera cronograma físico-financeiro BR — eles param na fábrica. Nosso pipeline pós-fábrica (orçamento→cronograma→curva S) é o que não existe lá.

## Pendências que esta colheita resolveu

- docs/03/04 "fixar commit do AutoSINAPI": **feito** (`0020609`, anotado na ponte).
- CLAUDE.md "ponte não é idempotente": **corrigido e testado** (3 execuções = mesmo preço).
