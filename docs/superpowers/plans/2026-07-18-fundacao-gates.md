# Fase 3 — Fundação + gates (pré-dimensionamento por classe de solo, vento/ancoragem)

**Objetivo**: fechar a cadeia D3 até a fundação: `takedown_por_parede` (Fase 2) →
pré-dimensionamento de baldrame corrido por parede (NBR 6122, tensão presumida da
`classe_solo`, mínimo construtivo 0,30 m) → m³ de concreto na folha 02.01 da EAP
(PARAMETRICO) → preço via composição própria VK-C-005. Gates: S1 BLOQUEIA o
pré-dimensionamento; sondagem pendente REBAIXA a confiança; verificação de
vento/ancoragem (NBR 6123 simplificada) roda sempre e vira pendência quando a
demanda excede a capacidade das fitas mínimas.

**Contexto herdado**: o produto emite PRÉ-DIMENSIONAMENTO para orçamento, nunca
projeto (CLAUDE.md). A fórmula de vento é cálculo próprio autorizado pelo usuário
em 2026-07-18 (sem revisão externa de engenheiro — decisão registrada na memória
e no aceite da Fase 2); toda regra de engenharia entra com `origemRegra` anotada
e confiança `estimado`/`parametrico`, nunca `real`.

**Aceite da fase (docs/02 §4, adaptado)**: "±15% vs. obra com projeto real" NÃO
tem oráculo no repositório (o orçamento v7 da 109.1506 não tem linhas de
fundação) — vira lacuna de DADO registrada, como o R9. A validação é por conta
de mão: caixa 6×4 com volume exato conferível no papel + gates provados na 109.
O gate de macroetapa zerada (R7) já existe e é coberto por teste.

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origemRegra`).

### Task 1: Seed de fundação — regras, insumos, composição VK-C-005, folha 02.01

- `regra_lsf`: `fund_larg_min_m` 0,30 (spike 4 / prática executiva baldrame),
  `fund_altura_baldrame_m` 0,40 (viga baldrame 30×40, prática NBR 6122),
  `vento_pressao_kn_m2` 0,61 (v7 CARGAS.vento; NBR 6123 simplificada),
  `fita_trd_kn` 17,9 (v7: T_Rd fita ZAR230), `fitas_min_por_linha` 3 (v7/NBR 6123).
- Insumos VEKS (preços `estimado`, praça SP, calibrar R6): `VK-I-006` concreto
  usinado C30 m³, `VK-I-007` aço CA-50 kg, `VK-I-008` forma de tábua m²,
  `VK-I-103` pedreiro h.
- `VK-C-005` "Baldrame corrido em concreto armado (fundação LSF)" m³, grupo
  FUNDACAO, coeficientes `estimado` (ordem SINAPI: concreto 1,05; aço 60 kg/m³;
  forma 6,7 m²/m³; pedreiro 3,5 h; ajudante 5,0 h).
- Folha EAP `02.01` (m³) → VK-C-005; `mapeamento_item` `fundacao.concreto_m3`.
- Teste: seed idempotente (2× build), folha com composição, custo fecha no motor.

### Task 2: Motor `fundacao.py` — pré-dimensionamento por parede

- `pre_dimensionar(con, projeto_id)`: consome `takedown_por_parede` do MENOR
  nível (radier é o menor nível, não o índice 0). Por parede portante:
  `largura = max(total_kn_m / tensao_adm_kpa, fund_larg_min_m)`, quem governa,
  `volume = largura × fund_altura_baldrame_m × comp`.
- Projeto sem `classe_solo_id` → `DadoIndisponivel` (D4.1). Classe S1 → resultado
  BLOQUEADO: sem volume, com pendência (gate, não aviso).
- Confiança: pior(confiança da carga, `estimado`); `sondagem_pendente=1` rebaixa
  para `parametrico` (solo presumido sem sondagem).
- Teste TDD: caixa 6×4 (S3): largura teórica ≈0,13 m < 0,30 → mínimo governa;
  volume = perímetro 20 m × 0,30 × 0,40 = 2,400 m³ exato. S1 bloqueia; sem solo erro.

### Task 3: Verificação de vento/ancoragem (NBR 6123 simplificada)

- `verificar_vento(con, projeto_id)`: fachadas do bbox das paredes externas do
  menor nível; altura = (max cota+pé-direito) − cota do radier. Por direção:
  `F = vento_pressao_kn_m2 × altura × largura_da_fachada_normal`;
  `fitas_necessarias_por_linha = ceil(F / (2 linhas × fita_trd_kn))`;
  hold-downs = 2 por extremo de linha × 2 linhas × 2 direções + 4 cantos.
- Pendência (motor `fundacao`) quando `fitas_necessarias > fitas_min_por_linha`:
  a capacidade mínima não fecha — anotar F, T_Rd e o n necessário na mensagem.
- `origemRegra` NBR 6123 em cada número. Teste: 109 reproduz a ordem do v7
  (F≈101 kN na maior fachada) e a caixa 6×4 não gera pendência.

### Task 4: `derivar_fundacao` + integração no app

- Grava m³ na 02.01 (PARAMETRICO, guarda MANUAL/TAKEOFF como os outros motores),
  pendências `motor='fundacao'` (S1, vento) com re-derivação idempotente.
- `app/rotas/planta.py::derivar` passa a chamar também `derivar_fundacao`;
  template mostra m³/confiança/governa + hold-downs. S1 → deriva estrutura e
  cargas mas fundação fica pendente (mensagem clara).
- Testes de app: caixa com S3 → m³ na EAP; projeto sem solo → 409 explicando;
  S1 → pendência gravada e publicação bloqueada.

### Task 5: Validação e fechamento

- Equilíbrio: m³ derivado × altura×largura confere com Σ comp das portantes.
- Registrar no CLAUDE.md: aceite ±15% vs obra real = lacuna de dado (como R9);
  validação por conta de mão travada em teste. Verificação no servidor real
  (fluxo planta → derivar com solo/sem solo/S1). Suíte inteira verde.
