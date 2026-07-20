# Calibração dos coeficientes VEKS contra dados PÚBLICOS

**Data:** 2026-07-20 · **Escopo:** confrontar os coeficientes `estimado` das composições
próprias (VK-C-001..005) contra fontes públicas confiáveis (SINAPI, manuais de fabricante,
geometria). **NÃO usa dado interno da Veks nem obra executada.**

## Distinção que governa este documento (não apagar)

Dado público **não é a calibração R6** e **não promove confiança para `real`**. A R6, como
definida no projeto (CLAUDE.md), é confrontar coeficiente contra **consumo medido em obra
executada** (109.1506, Baias Kabod). SINAPI/CBCA/fabricante são *outras estimativas* —
publicadas e competentes, mas não a medição da nossa obra. Portanto o efeito legítimo desta
calibração é:

- trocar coeficiente **sem fonte** por coeficiente **com fonte citável** (melhora proveniência);
- detectar coeficiente **fora da faixa** pública (isso é ERRO, e aí sim corrige);
- **manter a confiança em `estimado`** — nunca `real`. Promover dado público a `real`
  corromperia a semântica D4 e faria a proposta mostrar valor seco onde deve mostrar faixa ±%.

Confiança vira `real` só com R6 (obra). Esta rodada é **proveniência dentro de `estimado`**.

## Ressalva de execução

A coleta foi **truncada pelo limite mensal de gasto da conta** (os 3 subagentes de pesquisa
morreram com "monthly spend limit"). O que segue é o que uma rodada reduzida de busca direta
confirmou. **Itens marcados "ABERTO" não foram encontrados — não estão estimados nem
inventados.** Retomar quando o limite renovar (ou com o arquivo SINAPI real da Rota A, que
dá os coeficientes primários da própria Caixa).

## Achados por coeficiente

### VK-C-005 — Baldrame (m³)

| coef. | nosso | público | veredito |
|---|---|---|---|
| Forma (m²/m³) | 6,7 | **6,67 = geometria exata de seção 30×40** | ✓ confirmado por cálculo, não por chute |
| Aço CA-50 (kg/m³) | 60 | SINAPI tem armação de viga baldrame por kg (cód. 104921 família), não por m³ — taxa de armadura depende do projeto | ABERTO (faixa típica de baldrame leve não fechada nesta rodada) |
| Concreto (m³/m³) | 1,05 | perda 5% é padrão de mercado | plausível, fonte não fechada |
| MO pedreiro/ajudante (h/m³) | 3,5 / 5,0 | ABERTO | ABERTO |

**Forma — cálculo (reproduzível):** seção 30×40 → comprimento 1/(0,30·0,40)=8,33 m/m³ →
forma lateral 2·0,40·8,33 = **6,67 m²/m³**. O `6,7` do seed é essa conta, não um palpite.

**ACOPLAMENTO DESCOBERTO (registrar):** o `fundacao.py` calcula `largura = max(teórica,
0,30)`. Quando a carga faz a largura passar de 0,30 m, a forma por m³ **cai** (seção mais
larga = menos forma/volume): 0,40×0,40 daria 5,0 m²/m³, não 6,7. O coeficiente fixo só é
exato no caso do mínimo construtivo — que, por I3 (LSF é leve), é quase sempre o caso. O
erro é **conservador** (superestima), mas é acoplamento silencioso motor↔composição. Se um
dia a carga governar a largura, a forma da VK-C-005 fica superestimada. Fonte: geometria +
`db/migrations/*` (`fund_larg_min_m` 0,30, `fund_altura_baldrame_m` 0,40).

Fontes: [SINAPI 104921 armação baldrame](https://orcamentor.com/composicao/104921/) ·
[SINAPI 104488 estrutura concreto paramétrica](https://orcamentor.com/composicao/104488/)

### VK-C-004 — Fechamento placa cimentícia 10mm (m²)

| coef. | nosso | público (SINAPI/fabricante) | veredito |
|---|---|---|---|
| Placa 10mm (m²/m²) | 1,05 | SINAPI: **1,050 m²/m²** | ✓ bate exato |
| Parafuso 4,2/4,8×19 (un/m²) | 18 | SINAPI ~15 (0,15 cento); Brasilit: fixar a cada **30 cm em todos os montantes** | dentro da faixa geométrica 14–20 (ver abaixo); nosso é conservador |
| MO montador+ajudante (h/m²) | 0,35+0,35 | ABERTO | ABERTO |

**Parafusos — geometria (reproduzível):** campo (montante @40 cm × parafuso @30 cm) = 8,3
un/m²; borda de chapa 1,20×2,40 @20 cm = 12,5 un/m². Campo+borda cai em ~14–20 un/m². Nosso
18 está na faixa; SINAPI 15 também. Nenhum está errado; o nosso é levemente conservador.

Fontes: [SINAPI placa cimentícia (tabela TJAC)](https://www.tjac.jus.br/wp-content/uploads/2018/08/Tabela-SINAPI.pdf) ·
[Brasilit — instrução de montagem placa cimentícia (fixação @30 cm)](https://www.brasilit.com.br/sites/brasilit.com.br/files/downloads/1/Instru%C3%A7%C3%A3o%20de%20Montagem%20Placa%20Ciment%C3%ADcia.PDF)

### VK-C-002 — Fechamento OSB 11,1mm (m²)

Placa 1,05 m²/m² (5% perda) e 16 parafusos/m² são plausíveis pela mesma geometria da
VK-C-004, mas **não foram confirmados em fonte primária nesta rodada**. ABERTO.

### VK-C-003 — Membrana hidrófuga (m²)

Transpasse típico de membrana tipo Tyvek/DuPont gira em ~10 cm, o que sustenta o 1,10
m²/m² (10%) — **fonte primária não fechada nesta rodada**. ABERTO.

### VK-C-001 — Montagem LSF (kg) — O MAIS MATERIAL, e ABERTO

É a maior composição (a estrutura inteira) e a que menos se confirmou:

- **MO 0,04 h/kg montador + 0,04 h/kg ajudante: NÃO ENCONTRADO em fonte pública.** O CBCA
  publica o "Manual do Light Steel Framing: Engenharia" (grátis), mas ele é de
  **dimensionamento estrutural**, não de **produtividade** (h/m² ou h/kg). Nenhum número de
  produtividade fechou nesta rodada. Continua o item mais frágil e o mais importante.
- Perda de perfil 2% (coef. 1,02): surgiu a distinção **perfil pré-cortado (engineered) vs
  barra** — perda muda conforme a fábrica entrega peça no comprimento ou barra a cortar.
  Não fechado.
- Parafuso 6 un/kg: ABERTO.

Fontes: [CBCA — Manual LSF Engenharia (Skylight/CBCA)](http://www.skylightestruturas.com.br/downloads/101497_manual_lsf_engenharia_2016.pdf)

## Classificação por D7 — SINAPI-cobre vs LSF-próprio (2026-07-20)

Com a Veks sem dados de obra (a R6 de obra está morta), cada composição recebe UMA categoria,
por D7. Ela decide o destino da confiança. Gravada nas observações via migração 016.

| Composição / EAP | Categoria | Confiança-alvo | Como chega lá |
|---|---|---|---|
| **VK-C-001** Montagem LSF estrutural (kg) | **LSF-próprio** | `estimado` **permanente** | SINAPI não tem montagem de painel LSF (D7). Faixa ±% na proposta é a postura honesta; docs/06 estreita a faixa com dado secundário (Task 5), sem promover. |
| VK-C-002 OSB (m²) | SINAPI-cobre | `real` (oficial) | migrar p/ composição SINAPI de fechamento (Task 4, espera Rota A) |
| VK-C-003 Membrana (m²) | SINAPI-cobre | `real` (oficial) | idem |
| VK-C-004 Placa cimentícia (m²) | SINAPI-cobre | `real` (oficial) | SINAPI tem placa cimentícia; nosso 1,05 já bate (acima). Migrar. |
| VK-C-005 Baldrame (m³) | SINAPI-cobre | `real` (oficial) | concreto/forma/aço são serviços SINAPI clássicos. Migrar. |
| EAP 01 Preliminares | SINAPI-cobre | `real` (oficial) | sem composição hoje — travando o R7. Criar via SINAPI (Task 4). |
| EAP 05 Instalações | SINAPI-cobre | `real` (oficial) | idem |
| EAP 07 Complementares | SINAPI-cobre | `real` (oficial) | idem |
| EAP 08 Canteiro/gerenc. | SINAPI-cobre | `real` (oficial) | idem |

**Uma só composição é LSF-próprio: VK-C-001.** É o núcleo do produto e a única cuja incerteza é
permanente. Todo o resto tem composição SINAPI oficial esperando (Task 4, atrás da Rota A). Isso
também confirma, por outro caminho, o achado de que o R7 espera SINAPI e não dado da Veks.

## Conclusão

Nada foi promovido a `real` (correto: isso é R6). Nenhum coeficiente estava **fora de faixa**,
então nenhum foi corrigido — o valor desta rodada é **proveniência**: forma da VK-C-005 é
geometria exata (não chute), placa da VK-C-004 bate com SINAPI, parafusos batem por geometria.
O acoplamento motor↔forma da fundação é achado novo que vale ficar registrado. A MO da
VK-C-001 — o coeficiente mais material — segue **sem confirmação pública** e é o alvo
prioritário quando (a) o limite de gasto renovar para nova pesquisa, ou (b) o SINAPI real
entrar pela Rota A com os coeficientes primários da Caixa.
