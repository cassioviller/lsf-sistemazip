# Plano Validado v2.0 — Sistema de Orçamento e Cronograma LSF
**Data:** 08/07/2026 · **Status:** todas as premissas críticas testadas em código executável

---

## 1. O que "sem impedimentos" significa aqui

Nenhum plano elimina imprevistos; um plano validado elimina **bloqueios**. O critério adotado: cada elo do sistema está em um de dois estados — **PROVADO** (código executou e passou em assert hoje, 08/07/2026) ou **ROTA DUPLA** (caminho principal + fallback já disponível, de modo que a falha de um não para o projeto). Não existe elo em estado "esperamos que funcione".

## 2. Matriz de validação (evidência executada)

| Elo do sistema | Status | Evidência |
|---|---|---|
| Base de conhecimento multi-fonte versionada | **PROVADO** | `lsf_base.db` construído; view calcula custo com propagação de confiança |
| Adaptador DXF → eixos de parede | **PROVADO** | ezdxf (MIT): 4 linhas duplas → 2 eixos, espessura 0,14 m detectada por pareamento de paralelas |
| Motor CPM (passagem direta/inversa) | **PROVADO** | Rede-teste: duração 9, caminho crítico A-B-D — confere com cálculo manual |
| Curva S financeira | **PROVADO** | Distribuição por atividade acumulada fecha exatamente no Σ dos custos |
| BDI decomposto (fórmula TCU) | **PROVADO** | AC/S/R/G/DF/L/I → 27,79%, dentro da faixa paradigma |
| Takedown de cargas lendo o banco | **PROVADO** | Parede LSF 41,4 kg/m² → 4,92 kN/m (coerente com sistema leve) |
| Pré-dim. de fundação | **PROVADO + regra nova** | Em solo S3 a largura teórica deu 4,9 cm → **governa o mínimo construtivo (30 cm)**. Regra incorporada: `largura = max(teórica, mínimo)` |
| Panelizador (junta × vão) | **PROVADO** | Parede 9,20 m, vão 3,00–4,20 → junta em 6,00 m, fora da zona proibida (±30 cm do vão) |
| Cadeia fim-a-fim item→composição→custo | **PROVADO** | `estrutura.aco_kg` → VK-C-001 → R$ 18,15/kg → 1.500 kg = R$ 27.225,00 |
| Importação SINAPI | **ROTA DUPLA** | A: AutoSINAPI como serviço isolado (GPL não contamina via processo separado). B: importador próprio — o formato é `SINAPI_Referência_AAAA_MM.xlsx` lido com pandas, complexidade conhecida e baixa |
| Obtenção mensal dos arquivos SINAPI | **ROTA DUPLA** | A: download automatizado. B: download manual no site da Caixa (sempre disponível) — o importador lê arquivo local, então automação é conveniência, nunca dependência |
| Entrada DWG | **ROTA DUPLA** | A: exportação DXF pelo autor do projeto (todo AutoCAD faz, custo zero). B: conversor ODA File Converter (gratuito) como ferramenta interna. DWG nunca é parseado por nós |
| Entrada croqui/foto | **ROTA DUPLA** | A (principal): calibração de escala + traçado assistido em canvas — tecnologia trivial e provada. B (acelerador opcional): IA de visão propõe segmentos. O ML é *opcional por design*: sua ausência não bloqueia nada |
| Validação do CPM em produção | **ROTA DUPLA** | Testes próprios (já passando) + oráculo externo: mesmo projeto rodado no ProjectLibre deve bater |

Os spikes estão em `spikes_validacao.py` e **viram a suíte de testes de regressão da Fase 1** — validação que continua valendo a cada commit.

## 3. Impedimentos reais encontrados — e neutralizados

**I1. AutoSINAPI é GPLv3.** Embutir o código contaminaria o sistema proprietário. *Neutralização:* usá-lo como **processo separado** que popula o banco (dados não herdam GPL; a fronteira de processo é a fronteira da licença) — ou apenas como referência de formato, escrevendo importador próprio (Rota B, esforço baixo confirmado pela inspeção do código: pandas + xlsx).

**I2. Repositórios sem licença** (Raster-to-Graph, Skylark, bidwright) = todos os direitos reservados. *Neutralização:* código deles **nunca** entra no projeto; conceitos e papers, sim (ideias não são protegidas por copyright). TF2DeepFloorplan (GPL-3.0) segue a mesma regra do I1 se algum dia for usado.

**I3. Física do LSF invalida o dimensionamento ingênuo de fundação.** O spike revelou que cargas LSF são tão baixas que a tensão do solo raramente governa. *Neutralização:* regra `max(teórica, mínimo construtivo)` já incorporada; o motor também deve verificar ancoragem/arrancamento (vento), que em LSF pode governar antes da compressão — entra como verificação da Fase 3.

**I4. Bibliotecas de terceiros embutidas.** Política definida: **MIT/Apache/BSD podem ser embutidas** (ezdxf MIT ✓, opentakeoff Apache ✓ como referência); **GPL só via processo isolado**; **sem licença = só leitura**.

## 4. Fases (v2 — o que mudou com a validação)

**Fase 0 — Fundação de dados** *(parcialmente concluída hoje)*: schema + seed + view **prontos e testados**. Restante: decidir Rota A/B do SINAPI (critério: se o AutoSINAPI popular Postgres num schema mapeável ao nosso em <1 dia de integração, Rota A; senão B), importar data-base SP, completar composições próprias dos 8 grupos.

**Fase 1 — Motor de orçamento**: inalterada, com bônus — os spikes 3 e 6 já provaram BDI e cadeia de custo; falta agregação por EAP e relatório. Aceite: reproduzir orçamento Veks real com desvio ≤ 2%. `spikes_validacao.py` entra no CI.

**Fase 2 — Cadeia paramétrica (estágios 1–3)**: o spike 1 provou o núcleo do adaptador DXF; o spike 4 provou o takedown lendo o banco. Falta: extração de vãos, classificador portante, generalização por parede real. Aceite: kg de aço da 109.1506 com desvio ≤ 10% vs. v7.

**Fase 3 — Fundação + gates**: incorporar I3 (mínimo construtivo + verificação de ancoragem ao vento). Aceite: ±15% vs. obra com projeto real; gate bloqueia macroetapa zerada.

**Fase 4 — Cronograma + Curva S**: spikes 2 e 3 provaram os motores; falta rede real de precedências LSF e distribuição ponderada (aço adiantado). Validação cruzada com ProjectLibre.

**Fase 5 — Saídas, DWG/croqui e migração de modo**: rotas duplas definidas acima; panelizador (spike 5) evolui para IDs, kits de corte por painel e romaneio fábrica/obra.

## 5. Riscos residuais (honestos — nenhum bloqueante)

Os coeficientes das composições próprias e as produtividades são `estimado` até calibração com obra real (109.1506, Baias Kabod) — isso **degrada precisão, não bloqueia funcionamento**, e a etiqueta de confiança comunica a incerteza na proposta. A extração DXF em plantas "sujas" do mundo real exigirá heurísticas extras — mitigado porque o traçado manual assistido é o mesmo caminho do croqui, sempre disponível. E a verificação de vento/arrancamento (I3) precisa de fórmula validada com engenheiro estrutural antes do gate da Fase 3 — agendar essa revisão técnica é a única dependência humana externa do plano.

## 6. Backlog imediato (2 semanas, atualizado)

1. Decisão Rota A/B do SINAPI (teste de 1 dia com AutoSINAPI em container isolado).
2. Importar SINAPI SP (data-base vigente) → `insumo`/`insumo_preco` com `confianca='real'`.
3. Completar composições próprias dos 8 grupos (coeficientes CBCA/fabricante, tudo `estimado`).
4. Motor de orçamento: agregação por EAP + relatório analítico (spikes como testes).
5. Reproduzir 1 orçamento Veks real — aceite da Fase 1.
6. Agendar revisão de engenharia p/ regra de ancoragem/vento (destrava gate da Fase 3).

---
*Conclusão da validação: os 6 elos algorítmicos estão provados por código executado; os 4 pontos de dependência externa (SINAPI, DWG, croqui-ML, licenças) têm rota dupla com fallback já disponível. Não existe caminho no plano cujo fracasso pare o projeto — o pior caso em qualquer elo é degradação de conveniência ou precisão, nunca bloqueio.*
