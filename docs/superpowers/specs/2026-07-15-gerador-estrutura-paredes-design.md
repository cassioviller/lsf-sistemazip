# Gerador de estrutura de paredes (F2.1) — Design

Data: 2026-07-15 · Estágio: Fase 2, estágio 1 (parcial: só paredes) · Status: aprovado no brainstorm

## 1. Problema e visão

O v7 (`assets/calc-edificio-109_1506-v7-steel.html`, read-only) gera as peças de aço de uma
parede LSF — guias, montantes, kings/jacks, vergas, cripples, bloqueadores, contraventamento,
panelização — com regras embutidas em JavaScript. O produto precisa disso como **motor puro
sobre o banco** (D6): ler `planta_normalizada` (migração 004), decidir perfis por
`perfil_lsf`/`regra_lsf` (nunca hardcode), devolver peças rastreáveis e alimentar o orçamento
paramétrico.

**Decisão de abordagem: porta fiel 1:1.** Mesmo algoritmo, mesmos tipos de peça, parede a
parede — comparável peça a peça com o v7 headless. É o que garante o aceite. Melhorias
físicas (cantos compartilhados do grafo) só depois do aceite, com obra calibrando.

**Escopo deste estágio: só paredes** (`gerarPecas`). Lajes, escadas, cobertura e forro são
sub-projetos seguintes; o aceite da fase (23.673 kg líquido / 31.345 kg comprado do edifício
inteiro, desvio ≤ 10%) só fecha ao fim da série. O gate parcial deste estágio é o kg das
PAREDES vs v7.

## 2. Componentes e interfaces

| Unidade | Responsabilidade | Depende de |
|---|---|---|
| `src/lsf/geradores/estrutura.py` · `gerar_parede(con, parede_id) -> EstruturaParede` | Algoritmo do v7 para UMA parede: aberturas posicionadas → panelização (juntas fora dos vãos) → guias por painel → enquadramento de vãos (kings/jacks/vergas/cripples/diagonais sobre verga) → montantes de campo → bloqueadores → contraventamento (treliça/fita/OSB) → acessórios (ancoragem, fita) | `parede`/`vao`/`nivel` (migração 004), `perfil_lsf`, `regra_lsf` |
| `gerar_estrutura(con, projeto_id) -> EstruturaProjeto` | Itera as paredes do projeto; agrega peças, kg líquido por perfil, plano de corte em barras de 6 m (algoritmo de sobras do v7) e kg comprado; propaga a PIOR confiança dos inputs (D4, rank numérico) | `gerar_parede` |
| `derivar_quantitativos(con, projeto_id)` | Grava o kg comprado na folha **03.01** da EAP (estrutura LSF, kg) como `quantitativo` `origem='PARAMETRICO'`, confiança herdada do gerador; re-executar substitui a linha (UNIQUE projeto+item, D2) | `gerar_estrutura`, `eap_item` |
| `tools/` (estender runner headless do v7) | Despeja do v7: paredes W_T/W_S (coordenadas, tipo, aberturas) e, por parede, contagem de peças por tipo + ml + kg → `tests/fixtures/estrutura_v7_109_1506.json` | node headless, asset v7 (read-only, nunca editado) |

Dataclasses (frozen): `Peca` (tag, tipo, perfil, x0/y0/x1/y1, comp, origem_regra, confianca),
`EstruturaParede` (pecas, acessorios, alertas, kg_por_perfil), `EstruturaProjeto` (paredes,
kg_liquido, kg_comprado, plano_corte, confianca, alertas).

## 3. Fluxo de dados (D3)

`parede`+`vao` (grafo, confiança própria) → `gerar_parede` decide o perfil: usa
`parede.perfil_codigo` se preenchido; senão regra de default por nível/externa em
`regra_lsf`, gravando `origem_regra` — como o v7 faz com `PERFIL_PISO` por pavimento →
peças 2D no plano da parede (comprimento = hipotenusa dos nós) → kg líquido
(`massa_kg_m × comprimento`) → plano de corte em barras de 6 m → kg comprado →
`quantitativo` PARAMETRICO.

Contraventamento: derivado de `parede.externa` como no v7 (`externa=1` → fita em X;
interna → nenhum), com a derivação anotada em `origem_regra`. Quando F2.2 der entrada
explícita por parede, o campo vence a derivação.

## 4. Dados: migração 006 + seed (conhecimento, nunca à mão)

1. **Correção de perfis** — o seed portou valores PRÉ-`Object.assign` (linha 645 do v7):
   corrigir `Ue70#0.80` e `U72#0.80`; adicionar `U202#0.95`, `U252#1.25`, `Ue140#0.80`,
   `U142#0.80` e os laminados `W310x32.7` / `HSS100x100x4.8` (laje/cobertura — entram porque
   a correção é de conhecimento, não de escopo).
2. **Regras do gerador em `regra_lsf`**, cada uma com a origem do v7 anotada, confiança
   `estimado` (coeficiente novo sem calibração de obra): `king_duplo_lim_m` 2.0 [GATE2 1P4],
   `jack_duplo_lim_m` 2.0 [CBCA/AISI, pendente], `apoio_verga_m` 0.10, `passo_hb_m` 0.70,
   `peitoril_padrao_m` 1.0, `passo_trelica_m` 0.28, `colunas_trelica_se_m` 0.45,
   `diag_sobre_verga_min_m` 1.0, `barra_m` 6.0, `alt_min_porta_giro_m` 2.15,
   `alt_min_porta_correr_m` 2.20, `margem_abertura_m` 0.10, `folga_entre_aberturas_m` 0.15.
3. **Escalonamento de verga** (`vergaPorVao` do v7) vira dado: faixas (≤1,2 m → mesmo perfil
   da parede; ≤2,0 m → Ue140#1.25 + U142#1.25; acima → Ue250#2.00 + U252#2.00), em tabela
   própria `verga_escalonamento` (faixa_ate_m, perfil_montante, perfil_guia, origem) — a
   decisão fica consultável e versionada por seed.

## 5. Aceite e testes (TDD)

Unitários por comportamento (teste vermelho pelo motivo certo antes do código):
- distribuição de aberturas no espaço livre; aberturas fixas respeitadas; excedente avisado;
- junta de painel NUNCA a menos de 30 cm da lateral de um vão (regra que custou caro);
- king/jack simples ≤ 2 m, duplos acima; verga escalonada por faixa do vão;
- cripples sobre verga e sob peitoril mantendo a modulação; diagonais sobre verga em vão ≥ 1 m;
- bloqueadores HB cortados pelos vãos que a linha cruza;
- contraventamento: treliça (zigzag, 2 colunas se módulo > 0,45 m), fita (acessório em m), OSB (placas);
- guias por painel segmentadas em barras de 6 m;
- confiança propagada = pior dos inputs (parede estimado + perfil real → estimado).

Aceite do estágio, contra `estrutura_v7_109_1506.json`:
- por parede: contagem de peças por tipo idêntica e kg com desvio ≤ 1% (porta fiel);
- total das paredes: kg líquido e comprado com desvio ≤ 10% (gate parcial; o aceite dos
  23.673 kg do edifício fecha nos estágios seguintes).

## 6. Erros e alertas (D4.1)

- Perfil sem `massa_kg_m`, regra ausente, faixa de verga não coberta → exceção
  `DadoIndisponivel` (nunca peça pulada, nunca kg parcial).
- Parede degenerada (comprimento ≤ 0, pé-direito ≤ 0) → erro.
- Vão que não cabe / sobreposto / porta abaixo do mínimo → alerta estruturado no resultado
  (equivalente aos `warns` do v7), nunca descarte silencioso.

## 7. Fora de escopo (YAGNI)

- Lajes, escadas, cobertura, forro (próximos sub-projetos da Fase 2.1).
- Ramo drywall do `gerarPecas`: na nossa EAP, vedação drywall é quantificada por m² via
  composição SINAPI (D7), não por peças. A `parede` da migração 004 nem tem coluna
  `sistema` — neste estágio TODA parede da `planta_normalizada` é tratada como LSF
  estrutural; a distinção (coluna ou derivação em F2.2) fica fora daqui.
- Cantos compartilhados do grafo (pós-aceite, com calibração de obra).
- Romaneio/panelizador de fábrica (Fase 5).
- Verificação de ancoragem/arrancamento por vento (Fase 3, exige engenheiro estrutural).

## 8. Critério de pronto

Suíte inteira verde (inclusive spikes), fixture do v7 gerada por ferramenta reproduzível,
aceite parcial das paredes atingido, `derivar_quantitativos` fazendo o orçamento paramétrico
da 109.1506 aparecer na casca web com origem PARAMETRICO e confiança correta.
