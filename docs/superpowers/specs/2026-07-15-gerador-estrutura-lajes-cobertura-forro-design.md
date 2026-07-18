# Gerador de estrutura — lajes, escadas, cobertura e forro (Fase 2, fecho da estrutura)

**Data:** 2026-07-15
**Branch:** `fase2-estrutura-lajes-cobertura` (base `main`)
**Origem:** brainstorming sobre o que falta para o aceite da Fase 2 — o kg total de aço
do edifício. As paredes já batem com o v7 (aceite parcial ✓); faltam os quatro sistemas
que o v7 gera além das paredes: laje, escada, cobertura e forro.

## Problema

O gerador atual (`src/lsf/geradores/estrutura.py`) porta fielmente só o `gerarPecas` do v7
(paredes). O aceite da Fase 2 exige **kg de aço do edifício com desvio ≤ 10% vs v7**
(referência headless: **23.673 kg líquido / 31.345 kg comprado**, em
`tests/fixtures/orcamento_v7_109_1506.json`). Sem laje/escada/cobertura/forro esse número
não fecha — laje (vigas) e cobertura (tesouras Pratt) são o grosso do kg fora das paredes.

O v7 tem quatro funções ainda não portadas, em `assets/calc-edificio-109_1506-v7-steel.html`
(READ-ONLY): `gerarPecasLaje` (801), `gerarPecasEscada` (893), `gerarPecasCobertura` (949),
`gerarPecasForro` (1045). Elas dependem de infraestrutura que o port de paredes não tem:
o **footprint (polígono) por pavimento** e helpers de geometria (`scan`, `polyArea`,
`cortarSpan`, `chainPolygon`), mais a verificação estrutural de viga (`dimensionaViga`).

## Escopo

Os **quatro sistemas juntos**, num plano coeso — eles compartilham a mesma infra de
geometria e o oráculo é regenerado uma única vez. Decisão de brainstorming.

**Fora de escopo (mantido de propósito):**
- A junta de painel a **0,15 m** da lateral do vão (`estrutura.py` `_panelizar`) — decisão
  humana pendente (fiel ao v7, mas viola a regra de 30 cm e `junta_folga_vao_m=0.30`). Não tocar.
- Calibração de coeficientes contra obra (R6): tudo que entra agora é `estimado`.

## Arquitetura

### 1. Geometria — módulo novo `src/lsf/geradores/geometria.py` (funções puras, sem SQL)

Porta fiel dos helpers do v7 (linhas 684–794), testáveis isoladas:
- `encadear_contorno(paredes_ext)` — `chainPolygon`: encadeia segmentos externos num
  polígono fechado (tolerância 0,02 m, guard 200).
- `poly_area(poligono)` / `poly_perim(poligono)` — shoelace / perímetro.
- `scan(poligono, valor, eixo)` — interseções do polígono com a linha `z=valor` (`eixo='z'`)
  ou `x=valor` (`eixo='x'`) → lista de intervalos internos (filtro >0,05 m).
- `cortar_span(a, b, vaos)` — recorta um intervalo pelos vãos (aberturas de laje/escada).
- `bbox(poligono)` → `{x0,x1,z0,z1}`.

`footprintOf` (retângulo escalado à área-alvo) **não é portado**: `buildBuilding` do v7 usa
`chainPolygon` direto — o footprint é o contorno real das paredes externas (cadeia D3).

### 2. Footprint derivado (não gravado)

`contorno_pavimento(con, projeto_id, nivel)` lê as paredes externas de `planta_normalizada`
naquele nível e chama `encadear_contorno` → polígono. É a cadeia D3
(arquitetônico → paredes → estrutura): o footprint **vem das paredes**, não é dado solto.
Os níveis já existem (migração 004).

### 3. Migração 008 — inputs de projeto (o que o arquitetônico não dá)

O v7 hardcoda em `PROJECT` dados que não saem da planta (como o solo). Viram tabelas de
projeto, cada linha com `origem` + `confianca`, **seedadas para a 109.1506** reproduzir o
oráculo. Todas em português (convenção do projeto):

- `laje` (projeto_id, id_laje, grupo, pav_base, nivel, esp_m, perfil_viga TEXT
  DEFAULT 'auto', perfil_enrijecedor, bloqueador_max_m, chapa_piso_tipo, chapa_piso_larg,
  chapa_piso_alt, confianca)
- `laje_abertura` (laje_id, tipo, x, z, w, d) — vãos de escada na laje
- `laje_extensao` (laje_id, x, z, w, d) — faixas de varanda
- `escada` (projeto_id, id_escada, grupo, vao_x, vao_z, vao_w, vao_d, altura,
  nivel_inicial, formato, confianca)
- `cobertura` (projeto_id, id_cobertura, grupo, grupo_tesouras, nivel_base, beiral_m,
  inclinacao, telha_tipo, telha_perda_pct, confianca)
- `area_descoberta` (projeto_id, nome, x, z, w, d, tipo CHECK IN ('faixa','patio'), confianca)
- `forro` (projeto_id, perfil, perfil_borda, esp_m, grupo, confianca) — 1 por projeto

### 4. Seed — regras, cargas e perfis

- **`regra_lsf`** (chave-valor com `referencia`): os escalares de `REGRAS_SIS.laje/escada/`
  `cobertura/fr` viram chaves prefixadas (`laje_esp_m`, `laje_bloqueador_max_m`,
  `laje_vao_ue200`, `laje_enrij_c_f200/f250`, `escada_espelho_max`, `escada_piso_min`,
  `cobertura_esp_tesoura`, `cobertura_passo_mont`, `cobertura_beiral_m`, …). `regra_lsf.valor`
  é `REAL NOT NULL`, então **referências de perfil não escalares** (pares como
  `longarina:[Ue140#1.25,U142#1.25]`, `banzo`, `alma`, `painelCB`) **entram como colunas de
  texto nas tabelas de sistema do §3** (ex.: `escada.longarina_perfil_a/_b`,
  `escada.degrau_perfil`, `cobertura.banzo_perfil`, `cobertura.alma_perfil`,
  `cobertura.guia_banzo_perfil`), FK conceitual para `perfil_lsf.codigo` — nunca em `regra_lsf`.
- **Cargas estruturais** (`dimensionaViga` usa `CARGAS` global): `carga_sc`, `carga_g`,
  `aco_fy`, `aco_E`, `coef_gM`, `flecha_lim` → `regra_lsf` com `referencia` = NBR 6120 / 14762.
  Seção `SEC_Ue250` (A, Wx, Ix) idem.
- **`perfil_lsf`** (já tem tipo `laminado` desde a migração 006): perfis novos com massa_kg_m —
  `U202#0.95` (2,10), `U252#1.25` (3,26), `Ue140#0.80`, `U142#0.80`, `Ue90` variantes,
  `W310x32.7` (32,7), `HSS100x100x4.8` (14,2). **Todos `estimado`** (sem calibração — R6).

### 5. Motor estrutural — `dimensionar_viga`

`dimensionar_viga(vao_m, trib_m, cargas)` → `{modo, M, MRd, delta, dLim, V, VRd}` com
`modo ∈ {simples, dupla, laminada}`. Porta de `dimensionaViga` (v7:635). **Regra de
engenharia**: `origem_regra` obrigatório citando NBR 6120 (SC/G) e NBR 14762 (ELU M/V,
flambagem de alma, flecha L/350). Cargas e seção vêm do seed (§4), nunca constantes no código.

### 6. Geradores — 4 funções em `estrutura.py` (porta fiel, epsilons = contrato)

`gerar_laje`, `gerar_escada`, `gerar_cobertura`, `gerar_forro`. Cada peça carrega
`sistema`, `grupo`, `origem_regra` e `confianca` propagada pela pior dos inputs (rank
numérico, nunca `MIN()` de string — D4). Dado ausente (perfil/regra/footprint vazio) é
`DadoIndisponivel`, nunca kg parcial (D4.1).

**`Peca` ganha `sistema`, `grupo` e coordenada z** (x,y,z 3D): parede é plano 2D, mas
laje/cobertura/escada são 3D. `comp = hypot(Δx,Δy,Δz)` — a agregação de kg segue uniforme
(só depende de `comp` + `perfil`). Peças de parede permanecem compatíveis (z=0).

### 7. Agregação

`gerar_estrutura` passa a somar paredes + 4 sistemas; `plano_de_corte` e
`derivar_quantitativos` agregam o kg comprado de **todos** os sistemas na folha 03.01 como
PARAMETRICO (guarda existente: nunca sobrescreve MANUAL/TAKEOFF).

## Oráculo e aceite

Regenerar `tests/fixtures/estrutura_v7_109_1506.json` estendendo
`tools/extrair_estrutura_v7.mjs` para chamar as 4 funções do v7 headless — agora com os 4
sistemas. **Aceite**: peças por tipo/sistema batem com o v7; **kg total do edifício com
desvio ≤ 10%** (líquido 23.673 / comprado 31.345), faixa por sistema como no aceite das paredes.

## Testes (TDD — vermelho pelo motivo certo, depois verde)

- `tests/test_geometria.py` — `scan`/`encadear_contorno`/`cortar_span`/`poly_area` contra
  casos fechados à mão (retângulo, L, vão recortado).
- `tests/test_dimensiona_viga.py` — os 3 modos (simples/dupla/laminada) nos vãos-limite do v7.
- `tests/test_gerador_estrutura_completo.py` — aceite kg total + peças por sistema vs oráculo.
- Spikes (`tests/spikes_validacao.py`) seguem verdes — regressão.
- Suíte inteira verde antes de cada commit (comando exato no bloco de constraints).

## Riscos conhecidos

1. **Footprint derivado ≠ footprint do v7.** O v7 monta o footprint com `chainPolygon` das
   paredes externas de `W_T`/`W_S`. Se a `planta_normalizada` da 109.1506 não encadear no
   mesmo polígono fechado, o kg de laje/cobertura desvia. **O próprio aceite detecta.**
   Mitigação se falhar: gravar o footprint como fallback (degradar só o footprint para a
   opção "tabela explícita", sem mudar o resto).
2. **`dimensionaViga` global.** `CARGAS`/`SEC_Ue250` são globais no v7; viram seed. Conferir
   que reproduzem os 3 modos idênticos antes de confiar no kg de vigas duplas/laminadas.

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origem_regra`).
