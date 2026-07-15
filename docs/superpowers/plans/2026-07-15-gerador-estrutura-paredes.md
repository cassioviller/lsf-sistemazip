# Gerador de estrutura de paredes (F2.1 parcial) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portar o `gerarPecas` do v7 (paredes LSF: guias, montantes, kings/jacks, vergas, cripples, bloqueadores, contraventamento, panelização) para `src/lsf/geradores/estrutura.py` como motor puro sobre o banco, e gravar o kg comprado como `quantitativo` origem=PARAMETRICO.

**Architecture:** Porta fiel 1:1 do algoritmo do v7 (`assets/calc-edificio-109_1506-v7-steel.html`, READ-ONLY), lendo `planta_normalizada` (migração 004) e `perfil_lsf`/`regra_lsf`/`guia_de`/`verga_escalonamento` (migração 006 + seed). Oráculo: dump headless do v7 por parede (`tests/fixtures/estrutura_v7_109_1506.json`). Aceite parcial do estágio: por parede, contagem de peças por tipo idêntica e kg ≤1%; total das paredes ≤10%.

**Tech Stack:** Python 3.11 (`.venv/bin/python`), SQLite, node headless (`/nix/store/0akvkk9k1a7z5vjp34yz6dr91j776jhv-nodejs-20.11.1/bin/node`), pytest.

**Spec:** `docs/superpowers/specs/2026-07-15-gerador-estrutura-paredes-design.md`

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origemRegra`).

**Constraints adicionais desta feature:**

- **Porta FIEL**: onde este plano transcreve o algoritmo do v7, a ordem das operações, os epsilons (`1e-3`, `1e-6`, `0.02`, `0.1`…) e os arredondamentos são parte do contrato — mudá-los quebra o aceite peça-a-peça. Arredondamento "meio para cima" do JS ≠ `round()` do Python (banker's): usar o helper `_round_js`.
- **Branch:** `fase2-gerador-estrutura`, base `fase-app-casca-web` (desvio consciente da regra "base main": a spec, este plano e as fixtures de conftest vivem na branch da casca, que aguarda PR; quando ela mergear, esta rebaseia em `main`).

**Desvios conscientes da spec** (descobertos ao detalhar; anotados aqui para o revisor):

1. **Distribuição automática de aberturas não existe**: `vao.posicao_m` é `NOT NULL` (migração 004) — toda abertura tem posição explícita, e o ramo "autos" do v7 é inalcançável pelo nosso modelo de dados (as paredes do v7 também têm todas `p` explícito). Portamos só validação/clamp/sobreposição, com alertas.
2. **Perfil da parede é obrigatório**: a spec previa default por nível via `regra_lsf`, mas `regra_lsf.valor` é `REAL` (não guarda texto) e o default do v7 (`PERFIL_PISO` por pavimento) é dado da obra, não conhecimento. `perfil_codigo NULL` → `DadoIndisponivel` (D4.1). A fixture preenche o perfil por parede, como o `wallToP` fazia.
3. **Persiana fora**: `vao` não tem flag de persiana e nenhuma parede do aceite usa; a regra `caixa_persiana_m` já seeded fica para F2.2.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `db/migrations/006_perfis_gerador.sql` (criar) | Rebuild de `perfil_lsf` (CHECK aceita 'laminado'); tabelas `guia_de` e `verga_escalonamento` |
| `db/seed.sql` (modificar) | Perfis pós-override + novos; linhas de `guia_de`, `verga_escalonamento` e regras do gerador |
| `tools/extrair_estrutura_v7.mjs` (criar) | Dump headless do v7: paredes + referência por parede + totais → fixture |
| `tests/fixtures/estrutura_v7_109_1506.json` (criar, gerado) | Oráculo do aceite (53 paredes, 3 pavimentos) |
| `src/lsf/geradores/__init__.py` (criar) | Pacote |
| `src/lsf/geradores/estrutura.py` (criar) | `gerar_parede`, `gerar_estrutura`, `plano_de_corte`, `derivar_quantitativos`, dataclasses, `DadoIndisponivel` |
| `tests/test_gerador_estrutura.py` (criar) | Unitários por comportamento (TDD) |
| `tests/test_aceite_estrutura_v7.py` (criar) | Aceite por parede e total vs fixture |
| `tests/conftest.py` (modificar) | Fixture-fábrica `planta` (nivel/nós/parede/vãos via SQL) |
| `CLAUDE.md` (modificar, só na Task 8) | Estado atual + fase |

---

### Task 1: Migração 006 — perfis pós-override, `guia_de`, `verga_escalonamento`, regras do gerador

**Files:**
- Create: `db/migrations/006_perfis_gerador.sql`
- Modify: `db/seed.sql` (bloco de perfis + novas tabelas + regras)
- Test: `tests/test_migracao_006.py` (criar)

**Interfaces:**
- Consumes: `perfil_lsf`/`regra_lsf` do schema; padrão de seed idempotente (ON CONFLICT).
- Produces: `perfil_lsf` aceita tipo `'laminado'` e tem os valores PÓS-`Object.assign` (linha 645 do v7); `guia_de(familia_montante PK, familia_guia)`; `verga_escalonamento(faixa_ate_m PK, perfil_montante, perfil_guia, origem)` — `NULL` = mesmo perfil da parede; regras novas em `regra_lsf`. Tasks 3–6 leem tudo isso.

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_migracao_006.py`:

```python
"""Migração 006: conhecimento do gerador de estrutura (perfis pós-override do v7)."""


def test_perfis_corrigidos_pos_override(con):
    """O seed portou valores PRÉ-Object.assign do v7 (linha 645); agora tem que bater
    com o v7 PÓS-override — é com esses kg/m que o aceite fecha."""
    linhas = {c: (a, e, m) for c, a, e, m in con.execute(
        "SELECT codigo, aba_mm, enrijecedor_mm, massa_kg_m FROM perfil_lsf")}
    assert linhas["Ue70#0.80"] == (35, 10, 1.00)
    assert linhas["U72#0.80"] == (34, None, 0.90)


def test_perfis_novos_existem(con):
    codigos = {c for (c,) in con.execute("SELECT codigo FROM perfil_lsf")}
    assert {"U202#0.95", "U252#1.25", "Ue140#0.80", "U142#0.80",
            "W310x32.7", "HSS100x100x4.8"} <= codigos


def test_laminado_e_tipo_valido(con):
    tipo = con.execute(
        "SELECT tipo FROM perfil_lsf WHERE codigo='W310x32.7'").fetchone()[0]
    assert tipo == "laminado"


def test_guia_de_completo(con):
    mapa = dict(con.execute("SELECT familia_montante, familia_guia FROM guia_de"))
    assert mapa == {"Ue70": "U72", "Ue90": "U92", "Ue140": "U142",
                    "Ue200": "U202", "Ue250": "U252",
                    "M48": "G48", "M70": "G70", "M90": "G90"}


def test_verga_escalonamento(con):
    faixas = con.execute(
        "SELECT faixa_ate_m, perfil_montante, perfil_guia FROM verga_escalonamento"
        " ORDER BY faixa_ate_m").fetchall()
    assert [tuple(f) for f in faixas] == [
        (1.2, None, None),
        (2.0, "Ue140#1.25", "U142#1.25"),
        (9.9, "Ue250#2.00", "U252#2.00"),
    ]


def test_regras_do_gerador_presentes(con):
    chaves = {c for (c,) in con.execute("SELECT chave FROM regra_lsf")}
    assert {"modulacao_lsf_m", "barra_m", "king_duplo_lim_m", "jack_duplo_lim_m",
            "apoio_verga_m", "passo_hb_m", "peitoril_padrao_m", "passo_trelica_m",
            "colunas_trelica_se_m", "diag_sobre_verga_min_m", "alt_min_porta_giro_m",
            "alt_min_porta_correr_m", "margem_abertura_m", "folga_entre_aberturas_m",
            "passo_conex_painel_m", "ancor_esp_padrao_m"} <= chaves
    valores = dict(con.execute("SELECT chave, valor FROM regra_lsf"))
    assert valores["modulacao_lsf_m"] == 0.40
    assert valores["barra_m"] == 6.0
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_migracao_006.py -v
```

Esperado: FAIL — valores antigos em `perfil_lsf`, `no such table: guia_de`.

- [ ] **Step 3: Escrever a migração**

Criar `db/migrations/006_perfis_gerador.sql`:

```sql
-- ============================================================
-- 006 — Conhecimento do gerador de estrutura (F2.1)
-- Spec: docs/superpowers/specs/2026-07-15-gerador-estrutura-paredes-design.md
-- perfil_lsf ganha tipo 'laminado' (W310/HSS de laje/cobertura, do
-- Object.assign linha 645 do v7). SQLite não altera CHECK: rebuild.
-- ============================================================
PRAGMA foreign_keys = OFF;

CREATE TABLE perfil_lsf_novo (
  codigo TEXT PRIMARY KEY,
  familia TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('montante','guia','laminado')),
  drywall INTEGER NOT NULL DEFAULT 0,
  alma_mm REAL NOT NULL, aba_mm REAL NOT NULL,
  enrijecedor_mm REAL, espessura_mm REAL NOT NULL,
  massa_kg_m REAL NOT NULL,
  fonte TEXT NOT NULL DEFAULT 'LSF_DB v7 (obra ref. 484125)'
);
INSERT INTO perfil_lsf_novo SELECT * FROM perfil_lsf;
DROP TABLE perfil_lsf;
ALTER TABLE perfil_lsf_novo RENAME TO perfil_lsf;

PRAGMA foreign_keys = ON;

-- Correspondência montante→guia (DB.guiaDe do v7, linha 163)
CREATE TABLE guia_de (
  familia_montante TEXT PRIMARY KEY,
  familia_guia TEXT NOT NULL
);

-- Escalonamento de verga por vão (DB.regras.vergaPorVao do v7)
-- NULL = mesmo perfil da parede (faixa leve)
CREATE TABLE verga_escalonamento (
  faixa_ate_m REAL PRIMARY KEY,
  perfil_montante TEXT REFERENCES perfil_lsf(codigo),
  perfil_guia TEXT REFERENCES perfil_lsf(codigo),
  origem TEXT NOT NULL
);
```

- [ ] **Step 4: Atualizar o seed**

Em `db/seed.sql`, no bloco `-- PERFIS (portados do LSF_DB v7)`, **trocar as duas linhas divergentes** pelos valores pós-override e **acrescentar seis linhas** antes do `ON CONFLICT` (vírgulas!):

```sql
 ('Ue70#0.80','Ue70','montante',0,70,35,10,0.80,1.00),
 ('U72#0.80','U72','guia',0,72,34,NULL,0.80,0.90),
```

e, junto às demais linhas da lista:

```sql
 ('U202#0.95','U202','guia',0,202,40,NULL,0.95,2.10),
 ('U252#1.25','U252','guia',0,252,40,NULL,1.25,3.26),
 ('Ue140#0.80','Ue140','montante',0,140,40,12,0.80,1.53),
 ('U142#0.80','U142','guia',0,142,40,NULL,0.80,1.39),
 ('W310x32.7','W310','laminado',0,310,102,NULL,6.6,32.7),
 ('HSS100x100x4.8','HSS100','laminado',0,100,100,NULL,4.8,14.2)
```

Ao final do arquivo, acrescentar (padrão idempotente do projeto):

```sql
-- ---------- Gerador de estrutura F2.1: guia correspondente (guiaDe v7) ----------
INSERT INTO guia_de (familia_montante, familia_guia) VALUES
 ('Ue70','U72'),('Ue90','U92'),('Ue140','U142'),('Ue200','U202'),('Ue250','U252'),
 ('M48','G48'),('M70','G70'),('M90','G90')
ON CONFLICT (familia_montante) DO UPDATE SET familia_guia=excluded.familia_guia;

-- ---------- Escalonamento de verga (vergaPorVao v7) ----------
INSERT INTO verga_escalonamento (faixa_ate_m, perfil_montante, perfil_guia, origem) VALUES
 (1.2, NULL, NULL, 'OBRA DX-11: até 1,2m verga no perfil da parede'),
 (2.0, 'Ue140#1.25', 'U142#1.25', 'OBRA DX-11 caso pesado; escalonamento pendente'),
 (9.9, 'Ue250#2.00', 'U252#2.00', 'OBRA DX-11 caso pesado; escalonamento pendente')
ON CONFLICT (faixa_ate_m) DO UPDATE SET
  perfil_montante=excluded.perfil_montante, perfil_guia=excluded.perfil_guia,
  origem=excluded.origem;

-- ---------- Regras do gerador de paredes (REGRAS do v7, linhas 164-190) ----------
-- Coeficiente novo sem calibração de obra = estimado (referência anotada).
INSERT INTO regra_lsf (chave,valor,unidade,referencia) VALUES
 ('modulacao_lsf_m',0.40,'m','wallToP v7: passo de montante LSF estrutural (drywall usa modulacao_m)'),
 ('barra_m',6.0,'m','REGRA BOX-003 [mont. p.53]'),
 ('king_duplo_lim_m',2.0,'m','GATE2 painel 1P4: 1 king+1 jack por lado até 2m'),
 ('jack_duplo_lim_m',2.0,'m','CBCA/AISI, pendente'),
 ('apoio_verga_m',0.10,'m','OBRA aprox: apoio da verga sobre jack, por lado'),
 ('passo_hb_m',0.70,'m','OBRA-1P4, pendente: bloqueadores ~700mm'),
 ('peitoril_padrao_m',1.0,'m','v7 peitorilPadrao'),
 ('passo_trelica_m',0.28,'m','GATE2 1P4: passo vertical do zigzag (~21 diag)'),
 ('colunas_trelica_se_m',0.45,'m','v7: módulo > 0,45m → 2 colunas c/ montante curto'),
 ('diag_sobre_verga_min_m',1.0,'m','GATE2 1P4 BRR1-3: vão >= 1m → diagonais entre cripples'),
 ('alt_min_porta_giro_m',2.15,'m','GUIA SMART: vão mín. porta de giro'),
 ('alt_min_porta_correr_m',2.20,'m','GUIA SMART: vão mín. porta-janela de correr'),
 ('margem_abertura_m',0.10,'m','v7 gerarPecas: folga mínima da abertura à borda'),
 ('folga_entre_aberturas_m',0.15,'m','v7 gerarPecas: folga mínima entre aberturas'),
 ('passo_conex_painel_m',0.20,'m','OBRA DP-07: parafusos entre painéis, ziguezague'),
 ('ancor_esp_padrao_m',1.20,'m','OBRA "por modulação", pendente')
ON CONFLICT (chave) DO UPDATE SET
  valor=excluded.valor, unidade=excluded.unidade, referencia=excluded.referencia;
```

- [ ] **Step 5: Rodar os testes da migração, depois a suíte inteira**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_migracao_006.py -v
.venv/bin/python -m pytest tests/
```

Esperado: 6 passed; suíte inteira verde (o rebuild de `perfil_lsf` não pode quebrar nada — se `test_build_db` falhar, o PRAGMA do rebuild está dentro de transação).

- [ ] **Step 6: Commit**

```bash
git add db/migrations/006_perfis_gerador.sql db/seed.sql tests/test_migracao_006.py
git commit -m "feat(db): migração 006 — perfis pós-override v7, guia_de, verga_escalonamento, regras do gerador"
```

---

### Task 2: Oráculo headless — fixture `estrutura_v7_109_1506.json`

**Files:**
- Create: `tools/extrair_estrutura_v7.mjs`
- Create (gerado e commitado): `tests/fixtures/estrutura_v7_109_1506.json`
- Test: `tests/test_fixture_estrutura.py` (criar)

**Interfaces:**
- Consumes: `assets/calc-edificio-109_1506-v7-steel.html` (READ-ONLY — o script LÊ o arquivo, jamais o edita).
- Produces: JSON com `pe_direito_m`, `niveis` (cotas), `paredes[]` (uma por parede×pavimento: id, pav, nós a/b, externa, perfil, aberturas no formato da tabela `vao`, e `ref` = contagem de peças por tipo + ml + kg) e `total_paredes` (kg_liquido, kg_comprado). Tasks 3–7 usam como oráculo. São **53 paredes**: 19 do térreo (W_T) + 17 × 2 pavimentos (W_S).

**Como o v7 roda headless:** o HTML tem blocos `<script>` com o engine puro (dados + funções) e UI. O engine que interessa — `LSF_DB`, `W_T`/`W_S`, `PD`, `wallToP`, `gerarPecas`, `nestingCorte` — não depende de DOM; um stub `Proxy` engole as referências de UI avaliadas na carga dos blocos.

- [ ] **Step 1: Escrever o extrator**

Criar `tools/extrair_estrutura_v7.mjs`:

```js
// Extrai do v7 (headless) as paredes da 109.1506 e a referência de peças/kg
// por parede. O asset é READ-ONLY: este script só o lê.
// Uso: node tools/extrair_estrutura_v7.mjs > tests/fixtures/estrutura_v7_109_1506.json
import fs from 'node:fs';

const html = fs.readFileSync(
  new URL('../assets/calc-edificio-109_1506-v7-steel.html', import.meta.url), 'utf8');
const blocos = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);

// stub de DOM: qualquer acesso vira no-op encadeável
const noop = new Proxy(function () {}, {
  get: () => noop, set: () => true, apply: () => noop, construct: () => noop,
});
globalThis.document = noop;
globalThis.window = globalThis;
globalThis.localStorage = noop;
globalThis.addEventListener = () => {};
globalThis.requestAnimationFrame = () => 0;

for (const b of blocos) {
  try { (0, eval)(b); } catch (e) { /* blocos de UI podem falhar; engine não */ }
}
for (const nome of ['LSF_DB', 'W_T', 'W_S', 'PD', 'NIV', 'wallToP', 'gerarPecas', 'nestingCorte'])
  if (typeof globalThis[nome] === 'undefined') {
    console.error(`engine incompleto: ${nome} não carregou`); process.exit(1);
  }

// wallToP já converteu {t,ab} → P.aberturas com alt/peitoril resolvidos; o gerador
// só distingue JANELA vs não-JANELA, então todo não-janela vira PORTA
function aberturasVao(P) {
  return P.aberturas.map(a => ({
    tipo: a.tipo === 'janela' ? 'JANELA' : 'PORTA',
    posicao_m: a.x, largura_m: a.larg, altura_m: a.alt,
    peitoril_m: a.tipo === 'janela' ? (a.peitoril ?? 1.0) : 0,
  }));
}

const paredes = [];
const todas = [];
const fatias = [{ walls: W_T, fi: 0 }, { walls: W_S, fi: 1 }, { walls: W_S, fi: 2 }];
for (const { walls, fi } of fatias) {
  for (const w of walls) {
    const P = wallToP(w, fi);
    const res = gerarPecas(P);
    if (res.erro) { console.error(`parede ${w.id}: ${res.erro}`); process.exit(1); }
    const porTipo = {};
    let ml = 0, kg = 0;
    for (const p of res.pecas) {
      porTipo[p.tipo] = (porTipo[p.tipo] || 0) + 1;
      ml += p.comp;
      kg += p.comp * (LSF_DB.perfis[p.perfil]?.massaKgM || 0);
      todas.push({ perfil: p.perfil, comp: p.comp });
    }
    paredes.push({
      id: `${fi}/${w.id}`, pav: fi,
      a: w.a, b: w.b, externa: w.t === 'ext' ? 1 : 0, est: w.est ? 1 : 0,
      perfil: P.perfil,
      aberturas: aberturasVao(P),
      ref: { pecas_por_tipo: porTipo, ml: +ml.toFixed(2), kg: +kg.toFixed(2),
             alertas: res.warns.length, n_paineis: res.nPaineis, juntas: res.juntas },
    });
  }
}

const plano = nestingCorte(todas, LSF_DB, 'solto');
let kgLiq = 0, kgComp = 0;
for (const p of plano) {
  kgLiq += p.kg;
  kgComp += p.barras * 6 * (LSF_DB.perfis[p.perfil]?.massaKgM || 0);
}

process.stdout.write(JSON.stringify({
  origem: 'assets/calc-edificio-109_1506-v7-steel.html — gerarPecas headless (paredes)',
  pe_direito_m: PD, niveis: NIV,
  paredes,
  total_paredes: { kg_liquido: +kgLiq.toFixed(0), kg_comprado: +kgComp.toFixed(0) },
}, null, 1));
```

- [ ] **Step 2: Gerar a fixture e conferir de olho**

```bash
/nix/store/0akvkk9k1a7z5vjp34yz6dr91j776jhv-nodejs-20.11.1/bin/node \
  tools/extrair_estrutura_v7.mjs > tests/fixtures/estrutura_v7_109_1506.json
head -40 tests/fixtures/estrutura_v7_109_1506.json
```

Esperado: JSON com 53 paredes (19 do térreo + 17 × 2 pavimentos), `total_paredes.kg_liquido` na casa de milhares (as paredes são parte dos 23.673 kg do edifício — a soma de paredes+lajes+escadas+cobertura+forro é que fecha o total).

- [ ] **Step 3: Teste de invariantes da fixture**

Criar `tests/test_fixture_estrutura.py`:

```python
"""A fixture do oráculo é gerada por tools/extrair_estrutura_v7.mjs — estes testes
garantem que ninguém a truncou/editou à mão."""
import json
import pathlib

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "estrutura_v7_109_1506.json"


def test_fixture_tem_53_paredes_em_3_pavimentos():
    d = json.loads(FIXTURE.read_text())
    assert len(d["paredes"]) == 53          # 19 (W_T) + 17 + 17 (W_S nos pav. 1 e 2)
    assert {p["pav"] for p in d["paredes"]} == {0, 1, 2}
    assert d["pe_direito_m"] == 3.10


def test_toda_parede_tem_referencia_e_perfil():
    d = json.loads(FIXTURE.read_text())
    for p in d["paredes"]:
        assert p["ref"]["kg"] > 0, p["id"]
        assert p["perfil"].startswith("Ue"), p["id"]
        for a in p["aberturas"]:
            assert a["tipo"] in ("JANELA", "PORTA")
            assert a["posicao_m"] >= 0


def test_total_de_paredes_positivo_e_menor_que_o_edificio():
    d = json.loads(FIXTURE.read_text())
    assert 0 < d["total_paredes"]["kg_liquido"] < 23673
    assert d["total_paredes"]["kg_comprado"] > d["total_paredes"]["kg_liquido"]
```

- [ ] **Step 4: Rodar, depois suíte inteira, commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_fixture_estrutura.py -v
.venv/bin/python -m pytest tests/
git add tools/extrair_estrutura_v7.mjs tests/fixtures/estrutura_v7_109_1506.json tests/test_fixture_estrutura.py
git commit -m "feat(tools): oráculo headless do gerador — paredes da 109.1506 por parede (v7)"
```

---

### Task 3: Esqueleto do gerador — dataclasses, regras/perfis do banco, parede lisa

**Files:**
- Create: `src/lsf/geradores/__init__.py` (vazio)
- Create: `src/lsf/geradores/estrutura.py`
- Modify: `tests/conftest.py` (fixture-fábrica `planta`)
- Test: `tests/test_gerador_estrutura.py` (criar)

**Interfaces:**
- Consumes: tabelas das migrações 004/006 + seed (Task 1).
- Produces (assinaturas FINAIS — Tasks 4–8 dependem delas):
  - `DadoIndisponivel(Exception)`
  - `Peca(tag, tipo, perfil, x0, y0, x1, y1, comp, origem_regra)` (frozen)
  - `Acessorio(item, qtd, un)` (frozen)
  - `EstruturaParede(parede_id, pecas, acessorios, alertas, juntas, n_paineis, kg_por_perfil, confianca)` (frozen)
  - `gerar_parede(con, parede_id, contrav=None, vaos_contrav=1) -> EstruturaParede` — `contrav` em `{None, 'trelica', 'fita', 'osb', 'nenhum'}`; `None` = derivar de `parede.externa` (externa→'fita', interna→'nenhum', como o `wallToP`)
  - `_round_js(x, nd=0)` — arredondamento meio-para-cima do JS

- [ ] **Step 1: Fixture-fábrica no conftest**

Acrescentar ao final de `tests/conftest.py`:

```python
@pytest.fixture
def planta(con):
    """Fábrica de plantas mínimas para o gerador: cria projeto+nível e devolve
    função que cadastra uma parede (com vãos) e retorna o parede_id."""
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf, desonerado)"
        " VALUES ('TESTE-GER', 'Gerador', '2026-06', 'SP', 0)"
    )
    projeto_id = con.execute("SELECT id FROM projeto WHERE codigo='TESTE-GER'").fetchone()[0]

    def criar(comp=4.0, pd=3.10, perfil="Ue90#0.95", externa=0, vaos=(),
              confianca="real"):
        cur = con.execute(
            "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m) VALUES (?,?,?,?)",
            (projeto_id, criar.seq, f"nivel-{criar.seq}", pd),
        )
        nivel_id = cur.lastrowid
        criar.seq += 1
        no_a = con.execute(
            "INSERT INTO no_planta (nivel_id, x, y) VALUES (?,0,0)", (nivel_id,)
        ).lastrowid
        no_b = con.execute(
            "INSERT INTO no_planta (nivel_id, x, y) VALUES (?,?,0)", (nivel_id, comp)
        ).lastrowid
        parede_id = con.execute(
            "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, portante, externa,"
            " perfil_codigo, origem, confianca) VALUES (?,?,?,0.14,1,?,?, 'MANUAL', ?)",
            (nivel_id, no_a, no_b, externa, perfil, confianca),
        ).lastrowid
        for v in vaos:
            con.execute(
                "INSERT INTO vao (parede_id, tipo, posicao_m, largura_m, altura_m,"
                " peitoril_m, confianca) VALUES (?,?,?,?,?,?,?)",
                (parede_id, v["tipo"], v["posicao_m"], v["largura_m"], v["altura_m"],
                 v.get("peitoril_m", 0), v.get("confianca", "real")),
            )
        return parede_id

    criar.seq = 0
    criar.projeto_id = projeto_id
    return criar
```

- [ ] **Step 2: Testes que falham (parede lisa)**

Criar `tests/test_gerador_estrutura.py`:

```python
"""Gerador de estrutura de paredes — porta fiel do gerarPecas do v7 (unitários)."""
import pytest


def test_parede_lisa_tem_guias_montantes_e_extremos(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=2.0, pd=3.10))          # 1 painel, sem vãos
    tipos = {}
    for p in r.pecas:
        tipos[p.tipo] = tipos.get(p.tipo, 0) + 1
    assert tipos["guia"] == 2                                  # TBOT + TTOP (2m < barra 6m)
    assert tipos["montante_ext"] == 2                          # x=0 e x=comp
    assert tipos["montante"] == 4                              # 0.40, 0.80, 1.20, 1.60
    assert r.n_paineis == 1 and r.juntas == []


def test_parede_longa_panelizada_com_montantes_de_junta(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=7.0))                    # ceil(7/3.6) = 2 painéis
    assert r.n_paineis == 2
    assert r.juntas == [3.5]
    # cada junta traz um PAR de montantes de borda [OBRA layout]
    extras = [p for p in r.pecas if p.tipo == "montante_ext" and 3.3 < p.x0 < 3.7]
    assert len(extras) == 2
    # guias por painel: 2 painéis × (TBOT+TTOP), cada segmento < 6m
    assert sum(1 for p in r.pecas if p.tipo == "guia") == 4


def test_guia_de_parede_muito_longa_segmenta_em_barras_de_6m(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=13.0))                   # 4 painéis de 3.25m
    guias = [p for p in r.pecas if p.tipo == "guia"]
    assert all(p.comp <= 6.0 + 1e-9 for p in guias)


def test_perfil_ausente_e_erro_nao_silencio(con, planta):
    from lsf.geradores.estrutura import DadoIndisponivel, gerar_parede

    pid = planta()
    con.execute("UPDATE parede SET perfil_codigo = NULL WHERE id = ?", (pid,))
    with pytest.raises(DadoIndisponivel):
        gerar_parede(con, pid)


def _degenerada(con, planta):
    """Nós distintos no MESMO ponto: passa no CHECK (no_a<>no_b compara ids),
    mas comp=0 — o gerador tem que recusar."""
    planta()                                       # garante nível existente
    nivel_id = con.execute("SELECT id FROM nivel LIMIT 1").fetchone()[0]
    a = con.execute("INSERT INTO no_planta (nivel_id,x,y) VALUES (?,1,1)", (nivel_id,)).lastrowid
    b = con.execute("INSERT INTO no_planta (nivel_id,x,y) VALUES (?,1,1)", (nivel_id,)).lastrowid
    return con.execute(
        "INSERT INTO parede (nivel_id,no_a,no_b,espessura_m,portante,externa,"
        " perfil_codigo,origem,confianca) VALUES (?,?,?,0.14,1,0,'Ue90#0.95','MANUAL','real')",
        (nivel_id, a, b),
    ).lastrowid


def test_parede_degenerada_e_erro(con, planta):
    from lsf.geradores.estrutura import DadoIndisponivel, gerar_parede

    with pytest.raises(DadoIndisponivel):
        gerar_parede(con, _degenerada(con, planta))


def test_confianca_propagada_pior_dos_inputs(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(confianca="estimado")
    assert gerar_parede(con, pid).confianca == "estimado"
```

- [ ] **Step 3: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_gerador_estrutura.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'lsf.geradores'`.

- [ ] **Step 4: Implementar o esqueleto**

Criar `src/lsf/geradores/__init__.py` (vazio) e `src/lsf/geradores/estrutura.py`:

```python
"""Gerador de estrutura de paredes LSF — porta FIEL do gerarPecas do v7.

Cada bloco reproduz o algoritmo do calculador v7 (assets/, READ-ONLY), lendo
perfis e regras do banco em vez de constantes JS. Epsilons e ordem de operações
são contrato: o aceite compara peça a peça com o v7 headless.
origem_regra anota a proveniência de cada decisão, como o v7 fazia.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from lsf.motores.orcamento import pior_confianca


class DadoIndisponivel(Exception):
    """Perfil/regra/dado ausente é ERRO — nunca peça pulada, nunca kg parcial (D4.1)."""


def _round_js(x: float, nd: int = 0) -> float:
    """Math.round/toFixed do JS arredondam 0.5 para cima; round() do Python é
    banker's. A porta fiel exige o comportamento JS."""
    m = 10 ** nd
    return math.floor(x * m + 0.5) / m


@dataclass(frozen=True)
class Peca:
    tag: str
    tipo: str          # guia|montante|montante_ext|montante_curto|king|jack|
                       # verga_mont|verga_guia|peitoril|cripple|diagonal|bloqueador
    perfil: str
    x0: float
    y0: float
    x1: float
    y1: float
    comp: float
    origem_regra: str = ""


@dataclass(frozen=True)
class Acessorio:
    item: str
    qtd: float
    un: str


@dataclass(frozen=True)
class EstruturaParede:
    parede_id: int
    pecas: list[Peca]
    acessorios: list[Acessorio]
    alertas: list[str]
    juntas: list[float]
    n_paineis: int
    kg_por_perfil: dict[str, float]
    confianca: str


# ---------- leitura de conhecimento (dado ausente = DadoIndisponivel) ----------

def _regras(con: sqlite3.Connection) -> dict[str, float]:
    return {chave: valor for chave, valor in con.execute("SELECT chave, valor FROM regra_lsf")}


def _regra(regras: dict, chave: str) -> float:
    if chave not in regras:
        raise DadoIndisponivel(f"regra_lsf sem a chave '{chave}'")
    return regras[chave]


def _perfil(con, codigo: str) -> dict:
    linha = con.execute(
        "SELECT alma_mm, massa_kg_m FROM perfil_lsf WHERE codigo = ?", (codigo,)
    ).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"perfil '{codigo}' não cadastrado em perfil_lsf")
    return {"alma_mm": linha[0], "massa_kg_m": linha[1]}


def _guia_correspondente(con, perfil_montante: str) -> str:
    """Porta de perfilGuiaCorrespondente: guia_de[família] com a mesma espessura;
    se o código exato não existir, a primeira guia da família."""
    familia, _, t = perfil_montante.partition("#")
    g = con.execute(
        "SELECT familia_guia FROM guia_de WHERE familia_montante = ?", (familia,)
    ).fetchone()
    if g is None:
        raise DadoIndisponivel(f"guia_de sem a família '{familia}'")
    exato = f"{g[0]}#{t}"
    if con.execute("SELECT 1 FROM perfil_lsf WHERE codigo = ?", (exato,)).fetchone():
        return exato
    alternativa = con.execute(
        "SELECT codigo FROM perfil_lsf WHERE familia = ? ORDER BY codigo", (g[0],)
    ).fetchone()
    if alternativa is None:
        raise DadoIndisponivel(f"nenhuma guia da família '{g[0]}' em perfil_lsf")
    return alternativa[0]


def _perfil_verga(con, vao_larg: float, perfil_parede: str) -> tuple[str, str]:
    """Porta de perfilVerga: primeira faixa que acomoda o vão; NULL = perfil da parede."""
    faixas = con.execute(
        "SELECT faixa_ate_m, perfil_montante, perfil_guia FROM verga_escalonamento"
        " ORDER BY faixa_ate_m"
    ).fetchall()
    if not faixas:
        raise DadoIndisponivel("verga_escalonamento vazio")
    for ate, mont, guia in faixas:
        if vao_larg <= ate:
            return (mont or perfil_parede, guia or _guia_correspondente(con, perfil_parede))
    ate, mont, guia = faixas[-1]
    if mont is None or guia is None:
        raise DadoIndisponivel(f"vão de {vao_larg} m acima da última faixa de verga")
    return (mont, guia)


# ---------- o gerador ----------

def gerar_parede(con, parede_id: int, contrav: str | None = None,
                 vaos_contrav: int = 1) -> EstruturaParede:
    linha = con.execute(
        "SELECT p.externa, p.perfil_codigo, p.confianca,"
        "       a.x, a.y, b.x, b.y, n.pe_direito_m"
        "  FROM parede p"
        "  JOIN no_planta a ON a.id = p.no_a"
        "  JOIN no_planta b ON b.id = p.no_b"
        "  JOIN nivel n ON n.id = p.nivel_id"
        " WHERE p.id = ?", (parede_id,)
    ).fetchone()
    if linha is None:
        raise DadoIndisponivel(f"parede {parede_id} não existe")
    externa, perfil_m, conf, ax, ay, bx, by, pd = tuple(linha)
    comp = math.hypot(bx - ax, by - ay)
    if comp <= 0 or pd <= 0:
        raise DadoIndisponivel(f"parede {parede_id} degenerada (comp={comp}, pd={pd})")
    if perfil_m is None:
        raise DadoIndisponivel(
            f"parede {parede_id} sem perfil_codigo — dado ausente é erro (D4.1)")

    R = _regras(con)
    perfil_g = _guia_correspondente(con, perfil_m)
    alma_m = _perfil(con, perfil_m)["alma_mm"] / 1000
    passo = _regra(R, "modulacao_lsf_m")
    barra = _regra(R, "barra_m")

    pecas: list[Peca] = []
    alertas: list[str] = []
    seq: dict[str, int] = {}

    def mk(pfx, tipo, perfil, x0, y0, x1, y1, origem=""):
        seq[pfx] = seq.get(pfx, 0) + 1
        c = math.hypot(x1 - x0, y1 - y0)
        p = Peca(f"{pfx}{seq[pfx]}", tipo, perfil, _round_js(x0, 4), _round_js(y0, 4),
                 _round_js(x1, 4), _round_js(y1, 4), _round_js(c, 4), origem)
        pecas.append(p)
        return p

    ops, conf = _aberturas(con, parede_id, comp, pd, R, alertas, conf)
    juntas, n_paineis = _panelizar(comp, ops, R)

    # ---- guias: por painel, segmentadas em barras (v7: TTOP/TBOT próprios) ----
    limites = [0.0, *juntas, comp]
    for i in range(len(limites) - 1):
        a, b = limites[i], limites[i + 1]
        for y, pfx in ((0.0, "TBOT"), (pd, "TTOP")):
            x = a
            while x < b - 1e-6:
                fim = min(x + barra, b)
                mk(pfx, "guia", perfil_g, x, y, fim, y,
                   origem="guia por painel [OBRA layout 1PV]")
                x = fim

    # ---- posições de montantes de campo ----
    xs: list[float] = []
    i = 0
    while i * passo < comp - 1e-3:
        xs.append(_round_js(i * passo, 4))
        i += 1
    xs.append(_round_js(comp, 4))

    _enquadrar_vaos(con, ops, xs, pd, perfil_m, alma_m, R, mk)          # Task 4
    _montantes_de_campo(ops, xs, juntas, comp, pd, perfil_m, alma_m, pecas, mk)
    _bloqueadores(ops, comp, pd, perfil_m, R, pecas, mk)                # Task 5
    acess = _contraventamento_e_ancoragem(                              # Task 5
        contrav, externa, vaos_contrav, ops, juntas, comp, pd,
        perfil_m, alma_m, R, pecas, mk)

    kg: dict[str, float] = {}
    massas: dict[str, float] = {}
    for p in pecas:
        if p.perfil not in massas:
            massas[p.perfil] = _perfil(con, p.perfil)["massa_kg_m"]
        kg[p.perfil] = kg.get(p.perfil, 0.0) + p.comp * massas[p.perfil]

    return EstruturaParede(parede_id, pecas, acess, alertas, juntas, n_paineis,
                           kg, conf)


def _aberturas(con, parede_id, comp, pd, R, alertas, conf):
    """Vãos com posição explícita (posicao_m NOT NULL): valida, clampa e converte
    para o formato interno do v7 (x0/larg/sill/head/janela). Vão inválido vira
    alerta e sai do desenho — nunca silêncio."""
    margem = _regra(R, "margem_abertura_m")
    entre = _regra(R, "folga_entre_aberturas_m")
    alt_min = _regra(R, "alt_min_porta_giro_m")
    ops = []
    ultimo_fim = -1.0
    for tipo, pos, larg, alt, peitoril, conf_vao in con.execute(
        "SELECT tipo, posicao_m, largura_m, altura_m, peitoril_m, confianca"
        "  FROM vao WHERE parede_id = ? ORDER BY posicao_m", (parede_id,)
    ).fetchall():
        conf = pior_confianca(conf, conf_vao)
        janela = tipo == "JANELA"
        sill = min(peitoril, max(0.0, pd - alt - 0.05)) if janela else 0.0
        head = min(sill + alt, pd - 0.05)
        if larg > comp - 2 * margem:
            alertas.append(
                f"Vão de {larg} m não cabe numa parede de {comp:.2f} m (com folgas de borda).")
            continue
        if head - sill < 0.1:
            alertas.append("Abertura com altura inválida — ignorada.")
            continue
        if not janela and alt < alt_min - 1e-6:
            alertas.append(
                f"Porta com {alt:.2f} m: abaixo do vão mínimo (giro ≥{alt_min} m) [Guia Smart].")
        x0 = max(margem, min(pos, comp - margem - larg))
        if x0 < ultimo_fim + entre - 1e-6:
            alertas.append(f"Abertura de {larg} m sobreposta a outra — removida do desenho.")
            continue
        ops.append({"x0": x0, "larg": larg, "sill": sill, "head": head, "janela": janela})
        ultimo_fim = x0 + larg
    return ops, conf


def _panelizar(comp, ops, R):
    """Juntas fora dos vãos [OBRA layout 1PV] — junta NUNCA a <30cm da lateral."""
    n_paineis = max(1, math.ceil(comp / _regra(R, "largura_painel_max_m")))
    juntas = []
    for j in range(1, n_paineis):
        xj = comp * j / n_paineis
        o = next((o for o in ops if o["x0"] - 0.1 < xj < o["x0"] + o["larg"] + 0.1), None)
        if o:
            xj = (max(0.3, o["x0"] - 0.15)
                  if xj - o["x0"] < o["x0"] + o["larg"] - xj
                  else min(comp - 0.3, o["x0"] + o["larg"] + 0.15))
        juntas.append(_round_js(xj, 3))
    return sorted(set(juntas)), n_paineis


def _dentro_de_vao(ops, x):
    return any(o["x0"] + 0.02 < x < o["x0"] + o["larg"] - 0.02 for o in ops)


def _montantes_de_campo(ops, xs, juntas, comp, pd, perfil_m, alma_m, pecas, mk):
    kings_x = [p.x0 for p in pecas if p.tipo == "king"]
    for x in xs:
        if _dentro_de_vao(ops, x):
            continue
        if any(abs(kx - x) < alma_m * 1.2 for kx in kings_x):
            continue
        ext = x < 1e-3 or abs(x - comp) < 1e-3
        mk("E" if ext else "S", "montante_ext" if ext else "montante",
           perfil_m, x, 0, x, pd)
    for xj in juntas:
        # junta: cada painel traz seu montante de borda [OBRA layout]
        mk("E", "montante_ext", perfil_m, xj - alma_m / 2, 0, xj - alma_m / 2, pd)
        mk("E", "montante_ext", perfil_m, xj + alma_m / 2, 0, xj + alma_m / 2, pd)


# implementadas nas Tasks 4 e 5 — por ora, paredes sem vãos e sem HB/contraventamento:

def _enquadrar_vaos(con, ops, xs, pd, perfil_m, alma_m, R, mk):
    if ops:
        raise NotImplementedError("Task 4")


def _bloqueadores(ops, comp, pd, perfil_m, R, pecas, mk):
    return


def _contraventamento_e_ancoragem(contrav, externa, vaos_contrav, ops, juntas,
                                  comp, pd, perfil_m, alma_m, R, pecas, mk):
    return []
```

**Nota de fidelidade:** no v7 os montantes de campo são gerados DEPOIS do enquadramento (kings já existem quando a proximidade é checada) — a ordem das chamadas em `gerar_parede` preserva isso. Os stubs de Task 4/5 mantêm a parede lisa funcional e a suíte verde neste commit.

- [ ] **Step 5: Rodar os testes, depois a suíte, commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_gerador_estrutura.py -v
.venv/bin/python -m pytest tests/
git add src/lsf/geradores tests/test_gerador_estrutura.py tests/conftest.py
git commit -m "feat(gerador): esqueleto do gerador de paredes — guias por painel, montantes, juntas (porta fiel v7)"
```

Esperado antes do commit: 7 passed no arquivo novo; suíte inteira verde.

---

### Task 4: Enquadramento de vãos — kings/jacks, verga escalonada, cripples, diagonais, peitoril

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (substituir o stub `_enquadrar_vaos`)
- Test: `tests/test_gerador_estrutura.py` (acrescentar)

**Interfaces:**
- Consumes: `_perfil_verga`, `_perfil`, `mk`, regras da Task 1.
- Produces: peças `king`, `jack`, `verga_mont`, `verga_guia` (2+2 = caixa), `peitoril`, `cripple`, `diagonal` — tipos que a fixture da Task 2 conta por nome.

- [ ] **Step 1: Testes que falham**

Acrescentar a `tests/test_gerador_estrutura.py`:

```python
def _tipos(r):
    t = {}
    for p in r.pecas:
        t[p.tipo] = t.get(p.tipo, 0) + 1
    return t


def test_porta_estreita_king_e_jack_simples(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=4.0, vaos=[{"tipo": "PORTA", "posicao_m": 1.5,
                                  "largura_m": 0.9, "altura_m": 2.1}])
    t = _tipos(gerar_parede(con, pid))
    assert t["king"] == 2 and t["jack"] == 2          # 1 por lado (0.9m <= 2.0m)
    assert t["verga_mont"] == 2 and t["verga_guia"] == 2   # caixa da verga


def test_vao_largo_king_e_jack_duplos_e_verga_escalonada(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=8.0, vaos=[{"tipo": "PORTA", "posicao_m": 2.0,
                                  "largura_m": 2.5, "altura_m": 2.1}])
    r = gerar_parede(con, pid)
    t = _tipos(r)
    assert t["king"] == 4 and t["jack"] == 4          # 2 por lado (2.5m > 2.0m)
    vergas = [p for p in r.pecas if p.tipo == "verga_mont"]
    assert all(p.perfil == "Ue250#2.00" for p in vergas)   # faixa >2.0m


def test_janela_tem_peitoril_e_cripples_dos_dois_lados(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=4.0, vaos=[{"tipo": "JANELA", "posicao_m": 1.2,
                                  "largura_m": 1.6, "altura_m": 1.2,
                                  "peitoril_m": 1.0}])
    r = gerar_parede(con, pid)
    t = _tipos(r)
    assert t["peitoril"] == 1
    # modulação 0.40 dentro do vão [1.2, 2.8]: x=1.6, 2.0, 2.4 → 3 cripples
    # em cima (sobre a verga) e 3 embaixo (sob o peitoril)
    assert t["cripple"] == 6
    # vão 1.6m >= diag_sobre_verga_min 1.0m → diagonais entre os nós dos cripples
    assert t["diagonal"] == 4                          # 3 cripples → 4 segmentos


def test_vao_pequeno_nao_ganha_diagonal_sobre_verga(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=4.0, vaos=[{"tipo": "PORTA", "posicao_m": 1.5,
                                  "largura_m": 0.9, "altura_m": 2.1}])
    assert "diagonal" not in _tipos(gerar_parede(con, pid))


def test_vao_que_nao_cabe_vira_alerta_e_sai_do_desenho(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    pid = planta(comp=2.0, vaos=[{"tipo": "PORTA", "posicao_m": 0.1,
                                  "largura_m": 1.9, "altura_m": 2.1}])
    r = gerar_parede(con, pid)
    assert any("não cabe" in a for a in r.alertas)
    assert "king" not in _tipos(r)


def test_junta_de_painel_desvia_do_vao(con, planta):
    """A regra que custou caro: junta NUNCA a menos de 30cm da lateral de um vão."""
    from lsf.geradores.estrutura import gerar_parede

    # comp=7.2 → 2 painéis, junta natural em 3.6 — bem no meio de um vão [3.0, 4.2]
    pid = planta(comp=7.2, vaos=[{"tipo": "PORTA", "posicao_m": 3.0,
                                  "largura_m": 1.2, "altura_m": 2.1}])
    r = gerar_parede(con, pid)
    assert len(r.juntas) == 1
    xj = r.juntas[0]
    assert not (3.0 - 0.14 < xj < 4.2 + 0.14)          # fora do vão + folga
    # junta natural em 3.6 está EQUIDISTANTE das laterais (0.6 de cada); o v7
    # usa `<` estrito e empata para a DIREITA: min(comp-0.3, 4.2+0.15)
    assert xj == pytest.approx(4.35, abs=0.01)
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_gerador_estrutura.py -v
```

Esperado: os novos FAIL com `NotImplementedError: Task 4`; os antigos seguem verdes.

- [ ] **Step 3: Implementar `_enquadrar_vaos`**

Substituir o stub em `src/lsf/geradores/estrutura.py`:

```python
def _enquadrar_vaos(con, ops, xs, pd, perfil_m, alma_m, R, mk):
    """Porta fiel do enquadramento LSF do v7: kings/jacks (duplos acima do limite),
    verga em caixa (2 montantes + 2 guias), peitoril de janela, cripples na
    modulação e diagonais sobre a verga em vão largo."""
    king_lim = _regra(R, "king_duplo_lim_m")
    jack_lim = _regra(R, "jack_duplo_lim_m")
    apoio = _regra(R, "apoio_verga_m")
    diag_min = _regra(R, "diag_sobre_verga_min_m")
    guia_parede = _guia_correspondente(con, perfil_m)

    for o in ops:
        pv_mont, pv_guia = _perfil_verga(con, o["larg"], perfil_m)
        h_v = _perfil(con, pv_mont)["alma_mm"] / 1000
        vy0 = o["head"]
        vy1 = min(o["head"] + h_v, pd - 0.01)
        king_n = 2 if o["larg"] > king_lim else 1
        jack_n = 2 if o["larg"] > jack_lim else 1
        for lado in (-1, 1):
            xk = o["x0"] if lado < 0 else o["x0"] + o["larg"]
            for k in range(king_n):
                mk("K", "king", perfil_m,
                   xk + lado * (k + 1) * alma_m, 0, xk + lado * (k + 1) * alma_m, pd,
                   origem="king; duplo acima de 2m [GATE2 1P4]")
            for j in range(jack_n):
                x = xk - lado * (j * alma_m + alma_m / 2)
                mk("J", "jack", perfil_m, x, 0, x, vy0,
                   origem="jack sob a verga; duplo acima de 2m [CBCA/AISI pendente]")
        vx0 = o["x0"] - apoio
        vx1 = o["x0"] + o["larg"] + apoio
        mk("HTW", "verga_mont", pv_mont, vx0, vy0, vx1, vy0,
           origem="verga escalonada por vão [OBRA DX-11]")
        mk("HTW", "verga_mont", pv_mont, vx0, vy1, vx1, vy1,
           origem="verga escalonada por vão [OBRA DX-11]")
        # caixa: DUAS guias no eixo da verga (assim está no v7 — não é bug de cópia)
        mk("HTW", "verga_guia", pv_guia, vx0, (vy0 + vy1) / 2, vx1, (vy0 + vy1) / 2,
           origem="caixa da verga [OBRA DX-11]")
        mk("HTW", "verga_guia", pv_guia, vx0, (vy0 + vy1) / 2, vx1, (vy0 + vy1) / 2,
           origem="caixa da verga [OBRA DX-11]")
        if o["janela"]:
            mk("SBW", "peitoril", guia_parede,
               o["x0"], o["sill"], o["x0"] + o["larg"], o["sill"],
               origem="peitoril de janela")
        crip_x = []
        for x in xs:
            if not (o["x0"] + 0.02 < x < o["x0"] + o["larg"] - 0.02):
                continue
            if vy1 < pd - 0.02:
                mk("C", "cripple", perfil_m, x, vy1, x, pd,
                   origem="cripple sobre a verga, mantém a modulação")
                crip_x.append(x)
            if o["janela"] and o["sill"] > 0.02:
                mk("C", "cripple", perfil_m, x, 0, x, o["sill"],
                   origem="cripple sob o peitoril, mantém a modulação")
        if o["larg"] >= diag_min and vy1 < pd - 0.05:
            nos = [o["x0"], *crip_x, o["x0"] + o["larg"]]
            for i in range(len(nos) - 1):
                inv = i % 2 == 1
                mk("BRB", "diagonal", perfil_m,
                   nos[i], pd if inv else vy1, nos[i + 1], vy1 if inv else pd,
                   origem="diagonais sobre a verga em vão largo [GATE2 1P4 BRR1-3]")
```

- [ ] **Step 4: Rodar tudo e commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_gerador_estrutura.py -v
.venv/bin/python -m pytest tests/
git add src/lsf/geradores/estrutura.py tests/test_gerador_estrutura.py
git commit -m "feat(gerador): enquadramento de vãos — kings/jacks, verga escalonada, cripples, diagonais"
```

---

### Task 5: Bloqueadores HB, contraventamento e acessórios de ancoragem

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (substituir os stubs `_bloqueadores` e `_contraventamento_e_ancoragem`)
- Test: `tests/test_gerador_estrutura.py` (acrescentar)

**Interfaces:**
- Consumes: peças verticais já geradas (a treliça usa as posições delas), `ops`, `juntas`.
- Produces: peças `bloqueador`, `diagonal` (treliça), `montante_curto`; `Acessorio` de fita/OSB/ancoragem/parafusos de junta.

- [ ] **Step 1: Testes que falham**

Acrescentar a `tests/test_gerador_estrutura.py`:

```python
def test_bloqueadores_em_linhas_cortadas_pelos_vaos(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    # pd=3.10, passo_hb=0.70 → round_js(4.43)-1 = 3 linhas (y = 0.775, 1.55, 2.325)
    pid = planta(comp=4.0, vaos=[{"tipo": "PORTA", "posicao_m": 1.5,
                                  "largura_m": 0.9, "altura_m": 2.1}])
    r = gerar_parede(con, pid)
    hb = [p for p in r.pecas if p.tipo == "bloqueador"]
    # porta: sill=0, head=2.1. Linhas em y=0.775 e 1.55 cruzam o vão (2 trechos
    # cada); a de y=2.325 passa ACIMA da porta e segue inteira → 2+2+1 = 5
    assert len(hb) == 5
    cortados = [p for p in hb if p.y0 < 2.1]
    assert len(cortados) == 4
    assert all(not (p.x0 < 1.6 and p.x1 > 2.3) for p in cortados)


def test_parede_externa_deriva_fita_de_contraventamento(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=4.0, externa=1))
    fita = [a for a in r.acessorios if "Fita" in a.item]
    assert len(fita) == 1
    import math
    assert fita[0].qtd == pytest.approx(round(2 * math.hypot(3.10, 3.6), 1))


def test_parede_interna_nao_tem_contraventamento(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=4.0, externa=0))
    assert not any("Fita" in a.item or "OSB" in a.item for a in r.acessorios)
    assert "montante_curto" not in {p.tipo for p in r.pecas}


def test_trelica_gera_zigzag_numa_coluna(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=2.0), contrav="trelica")
    t = _tipos(r)
    # baias entre montantes adjacentes têm 0.40m <= 0.45 → coluna ÚNICA na última
    # baia livre; n_passos = round_js(3.10/0.28) = 11 diagonais em zigzag
    assert "montante_curto" not in t
    assert t["diagonal"] == 11


def test_ancoragem_por_comprimento(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=4.0))
    anc = next(a for a in r.acessorios if "Ancorador" in a.item)
    assert anc.qtd == 4                                # max(2, floor(4/1.2)+1)
    paraf = next(a for a in r.acessorios if "ancoradores" in a.item)
    assert paraf.qtd == 32


def test_parafusos_de_conexao_entre_paineis(con, planta):
    from lsf.geradores.estrutura import gerar_parede

    r = gerar_parede(con, planta(comp=7.0))            # 1 junta
    pf = next(a for a in r.acessorios if "conexão entre painéis" in a.item)
    assert pf.qtd == 16                                # 1 junta × ceil(3.10/0.20)
```

- [ ] **Step 2: Rodar e ver falhar; Step 3: implementar**

Substituir os stubs:

```python
def _bloqueadores(ops, comp, pd, perfil_m, R, pecas, mk):
    """Bloqueadores HB em linhas horizontais, cortados pelos vãos que a linha cruza."""
    n_lin = max(1, int(_round_js(pd / _regra(R, "passo_hb_m"))) - 1)
    for lin in range(1, n_lin + 1):
        y = _round_js(pd * lin / (n_lin + 1), 4)
        cortes = [[0.0, comp]]
        for o in ops:
            if not (o["sill"] < y < o["head"]):
                continue
            for i in range(len(cortes) - 1, -1, -1):
                a, b = cortes[i]
                va, vb = o["x0"], o["x0"] + o["larg"]
                if va > a and vb < b:
                    cortes[i:i + 1] = [[a, va], [vb, b]]
                elif va <= a and vb >= b:
                    del cortes[i]
                elif a < va < b:
                    cortes[i] = [a, va]
                elif a < vb < b:
                    cortes[i] = [vb, b]
        for a, b in cortes:
            if b - a < 0.15:
                continue
            mk("HB", "bloqueador", perfil_m, a, y, b, y,
               origem="bloqueador ~700mm [OBRA-1P4 pendente]")


def _contraventamento_e_ancoragem(contrav, externa, vaos_contrav, ops, juntas,
                                  comp, pd, perfil_m, alma_m, R, pecas, mk):
    """Contraventamento (derivado de `externa` quando não vem explícito, como o
    wallToP do v7) + acessórios de ancoragem [OBRA-484125]."""
    if contrav is None:
        contrav = "fita" if externa else "nenhum"
    acess: list[Acessorio] = []

    if contrav == "trelica":
        n_b = max(1, vaos_contrav)
        vx = sorted({_round_js(p.x0, 3) for p in pecas
                     if p.tipo in ("montante", "montante_ext", "king", "jack")})
        livres = []
        for i in range(len(vx) - 1):
            a, b = vx[i], vx[i + 1]
            if b - a < 0.15:
                continue
            if any(a >= o["x0"] - 0.03 and b <= o["x0"] + o["larg"] + 0.03 for o in ops):
                continue
            livres.append((a, b))
        for a, b in livres[-n_b:]:
            cols = ([(a, (a + b) / 2), ((a + b) / 2, b)]
                    if (b - a) > _regra(R, "colunas_trelica_se_m") else [(a, b)])
            if len(cols) == 2:
                mk("S", "montante_curto", perfil_m, (a + b) / 2, 0, (a + b) / 2, pd,
                   origem="montante intermediário da treliça")
            for ca, cb in cols:
                n_passos = max(2, int(_round_js(pd / _regra(R, "passo_trelica_m"))))
                flip = False
                for i in range(n_passos):
                    y0 = pd * i / n_passos
                    y1 = pd * (i + 1) / n_passos
                    x_a, x_b = (cb, ca) if flip else (ca, cb)
                    mk("BRB", "diagonal", perfil_m,
                       x_a + (-1 if flip else 1) * alma_m / 2, y0,
                       x_b + (1 if flip else -1) * alma_m / 2, y1,
                       origem="treliça zigzag [GATE2 1P4]")
                    flip = not flip
    elif contrav == "fita":
        diag = math.hypot(pd, min(comp, 3.6))
        acess.append(Acessorio("Fita de contraventamento em X",
                               _round_js(vaos_contrav * 2 * diag, 1), "m"))
    elif contrav == "osb":
        acess.append(Acessorio("OSB estrutural (diafragma)",
                               math.ceil(comp * pd / 2.88), "placa"))

    if juntas:
        pf = len(juntas) * math.ceil(pd / _regra(R, "passo_conex_painel_m"))
        acess.append(Acessorio(
            "Parafuso sext. 4,8x19 — conexão entre painéis (ziguezague 200mm)", pf, "un"))
    n_anc = max(2, math.floor(comp / _regra(R, "ancor_esp_padrao_m")) + 1)
    acess.append(Acessorio("Ancorador chapa #3,00 190x50x50", n_anc, "un"))
    acess.append(Acessorio('Chumbador Parabolt 5/16"x4-1/4"', n_anc, "un"))
    acess.append(Acessorio("Parafuso sextavado 4,8x19 (ancoradores)", n_anc * 8, "un"))
    return acess
```

- [ ] **Step 4: Rodar tudo e commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_gerador_estrutura.py -v
.venv/bin/python -m pytest tests/
git add src/lsf/geradores/estrutura.py tests/test_gerador_estrutura.py
git commit -m "feat(gerador): bloqueadores HB, contraventamento (treliça/fita/OSB) e ancoragem"
```

---

### Task 6: Plano de corte (barras 6 m) e `gerar_estrutura`

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (acrescentar)
- Test: `tests/test_gerador_estrutura.py` (acrescentar)

**Interfaces:**
- Consumes: `gerar_parede`, `_perfil`, `_regras`.
- Produces (Task 7 e 8 dependem):
  - `PlanoCortePerfil(perfil, n_pecas, ml, kg, barras, perda_pct)` (frozen)
  - `EstruturaProjeto(projeto_id, paredes, plano_corte, kg_liquido, kg_comprado, confianca, alertas)` (frozen)
  - `plano_de_corte(con, pecas, barra_m) -> list[PlanoCortePerfil]` — first-fit decrescente com emenda para peça > barra (porta do `nestingCorte`)
  - `gerar_estrutura(con, projeto_id) -> EstruturaProjeto` — `DadoIndisponivel` se o projeto não tem parede

- [ ] **Step 1: Testes que falham**

```python
def test_plano_de_corte_first_fit_com_emenda(con):
    from lsf.geradores.estrutura import Peca, plano_de_corte

    def peca(comp):
        return Peca("X1", "guia", "U92#0.95", 0, 0, comp, 0, comp)

    plano = plano_de_corte(con, [peca(4.0), peca(4.0), peca(2.0), peca(1.9)], 6.0)
    assert len(plano) == 1
    p = plano[0]
    # FFD: [4.0]+[2.0]→b1, [4.0]+[1.9]→b2 = 2 barras
    assert p.barras == 2
    assert p.ml == pytest.approx(11.9)
    assert p.kg == pytest.approx(14.9)      # 11.9 × 1.25 kg/m (U92#0.95), _round_js(·,1)


def test_peca_maior_que_a_barra_vira_emendas(con):
    from lsf.geradores.estrutura import Peca, plano_de_corte

    plano = plano_de_corte(
        con, [Peca("X1", "guia", "U92#0.95", 0, 0, 8.5, 0, 8.5)], 6.0)
    assert plano[0].barras == 2                              # 6.0 + 2.5


def test_gerar_estrutura_agrega_e_propaga_pior_confianca(con, planta):
    from lsf.geradores.estrutura import gerar_estrutura

    planta(comp=4.0, confianca="real")
    planta(comp=3.0, confianca="parametrico")
    est = gerar_estrutura(con, planta.projeto_id)
    assert len(est.paredes) == 2
    assert est.kg_liquido > 0
    assert est.kg_comprado > est.kg_liquido                  # sobras de barra
    assert est.confianca == "parametrico"                    # pior dos inputs


def test_gerar_estrutura_com_geometria_real_nao_melhora_estimado(con, planta):
    """Coeficientes das regras são `estimado` (sem calibração de obra): o resultado
    nunca é melhor que estimado, mesmo com geometria `real`."""
    from lsf.geradores.estrutura import gerar_estrutura

    planta(comp=4.0, confianca="real")
    assert gerar_estrutura(con, planta.projeto_id).confianca == "estimado"


def test_projeto_sem_parede_e_erro(con, planta):
    from lsf.geradores.estrutura import DadoIndisponivel, gerar_estrutura
    import pytest as _pytest

    with _pytest.raises(DadoIndisponivel):
        gerar_estrutura(con, 999999)
```

**Atenção:** os dois testes de confiança acima se contradizem se lidos errado. A regra final (spec §5 + convenção "coeficiente novo = estimado"): `confianca(EstruturaProjeto) = pior_confianca(pior_das_paredes, "estimado")`. Geometria `real` → resultado `estimado`; geometria `parametrico` → resultado `parametrico`. O primeiro teste usa uma parede `parametrico` e espera `parametrico`; o segundo usa tudo `real` e espera `estimado`. Consistentes.

- [ ] **Step 2: Rodar e ver falhar; Step 3: implementar**

Acrescentar a `src/lsf/geradores/estrutura.py`:

```python
@dataclass(frozen=True)
class PlanoCortePerfil:
    perfil: str
    n_pecas: int
    ml: float
    kg: float
    barras: int
    perda_pct: float


@dataclass(frozen=True)
class EstruturaProjeto:
    projeto_id: int
    paredes: list[EstruturaParede]
    plano_corte: list[PlanoCortePerfil]
    kg_liquido: float
    kg_comprado: float
    confianca: str
    alertas: list[str]


def plano_de_corte(con, pecas: list[Peca], barra_m: float) -> list[PlanoCortePerfil]:
    """Porta do nestingCorte do v7: first-fit decrescente por perfil; peça maior
    que a barra vira emendas de até barra_m."""
    por_perfil: dict[str, list[Peca]] = {}
    for p in pecas:
        por_perfil.setdefault(p.perfil, []).append(p)
    plano = []
    for perfil, lista in sorted(por_perfil.items()):
        massa = _perfil(con, perfil)["massa_kg_m"]
        ml = sum(p.comp for p in lista)
        sobras: list[float] = []

        def alocar(c):
            for i, s in enumerate(sobras):
                if s >= c - 1e-9:
                    sobras[i] = _round_js(s - c, 4)
                    return
            sobras.append(_round_js(barra_m - c, 4))

        for p in sorted(lista, key=lambda p: -p.comp):
            if p.comp > barra_m + 1e-6:
                rest = p.comp
                while rest > 1e-6:
                    c = min(rest, barra_m)
                    alocar(c)
                    rest -= c
            else:
                alocar(p.comp)
        sobra_total = sum(sobras)
        plano.append(PlanoCortePerfil(
            perfil, len(lista), _round_js(ml, 2), _round_js(ml * massa, 1),
            len(sobras),
            _round_js(100 * sobra_total / (len(sobras) * barra_m), 1) if sobras else 0.0))
    return plano


def gerar_estrutura(con, projeto_id: int) -> EstruturaProjeto:
    ids = [r[0] for r in con.execute(
        "SELECT p.id FROM parede p JOIN nivel n ON n.id = p.nivel_id"
        " WHERE n.projeto_id = ? ORDER BY p.id", (projeto_id,))]
    if not ids:
        raise DadoIndisponivel(
            f"projeto {projeto_id} sem paredes na planta_normalizada")
    paredes = [gerar_parede(con, i) for i in ids]
    todas = [p for ep in paredes for p in ep.pecas]
    barra = _regra(_regras(con), "barra_m")
    plano = plano_de_corte(con, todas, barra)
    kg_liquido = sum(pl.kg for pl in plano)
    kg_comprado = sum(
        pl.barras * barra * _perfil(con, pl.perfil)["massa_kg_m"] for pl in plano)
    # coeficientes das regras são `estimado` (sem calibração de obra): o resultado
    # nunca é melhor que estimado, por pior que seja a geometria (D4)
    confianca = pior_confianca(*(ep.confianca for ep in paredes), "estimado")
    alertas = [a for ep in paredes for a in ep.alertas]
    return EstruturaProjeto(projeto_id, paredes, plano,
                            _round_js(kg_liquido), _round_js(kg_comprado),
                            confianca, alertas)
```

- [ ] **Step 4: Rodar tudo e commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_gerador_estrutura.py -v
.venv/bin/python -m pytest tests/
git add src/lsf/geradores/estrutura.py tests/test_gerador_estrutura.py
git commit -m "feat(gerador): plano de corte em barras 6m e agregação do projeto (kg líquido/comprado)"
```

---

### Task 7: Aceite — paredes da 109.1506 vs oráculo do v7

**Files:**
- Test: `tests/test_aceite_estrutura_v7.py` (criar)

**Interfaces:**
- Consumes: fixture da Task 2; `gerar_parede`/`gerar_estrutura` (Tasks 3–6); tabelas da migração 004.
- Produces: o gate parcial do estágio — por parede, contagem por tipo idêntica e kg ≤1%; total ≤10%.

- [ ] **Step 1: Escrever o teste de aceite**

Criar `tests/test_aceite_estrutura_v7.py`:

```python
"""ACEITE PARCIAL F2.1 (paredes): porta fiel vs v7 headless, parede a parede.

Carrega as 53 paredes da 109.1506 (fixture extraída do v7) na planta_normalizada
e compara o gerador com a referência. O aceite da FASE (23.673 kg do edifício,
desvio <= 10%) só fecha quando lajes/escadas/cobertura/forro forem portados.
"""
import json
import pathlib

import pytest

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "estrutura_v7_109_1506.json"


@pytest.fixture(scope="module")
def oraculo():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def projeto_109(con, oraculo):
    """Projeto com a planta da 109.1506 carregada na planta_normalizada."""
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf, desonerado)"
        " VALUES ('109.1506-EST', 'Máximo Tintas', '2026-06', 'SP', 0)")
    pid = con.execute(
        "SELECT id FROM projeto WHERE codigo='109.1506-EST'").fetchone()[0]
    niveis = {}
    for i, cota in enumerate(oraculo["niveis"]):
        cur = con.execute(
            "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m, cota_m)"
            " VALUES (?,?,?,?,?)",
            (pid, i, f"pav-{i}", oraculo["pe_direito_m"], cota))
        niveis[i] = cur.lastrowid
    mapa = {}          # id da fixture -> parede_id no banco
    for w in oraculo["paredes"]:
        nivel_id = niveis[w["pav"]]
        no_a = con.execute(
            "INSERT INTO no_planta (nivel_id, x, y, confianca) VALUES (?,?,?,?)",
            (nivel_id, w["a"][0], w["a"][1], "real")).lastrowid
        no_b = con.execute(
            "INSERT INTO no_planta (nivel_id, x, y, confianca) VALUES (?,?,?,?)",
            (nivel_id, w["b"][0], w["b"][1], "real")).lastrowid
        parede_id = con.execute(
            "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, portante,"
            " externa, perfil_codigo, origem, confianca)"
            " VALUES (?,?,?,0.14,1,?,?,'MANUAL',?)",
            (nivel_id, no_a, no_b, w["externa"], w["perfil"],
             "estimado" if w["est"] else "real")).lastrowid
        for a in w["aberturas"]:
            con.execute(
                "INSERT INTO vao (parede_id, tipo, posicao_m, largura_m, altura_m,"
                " peitoril_m, confianca) VALUES (?,?,?,?,?,?,'real')",
                (parede_id, a["tipo"], a["posicao_m"], a["largura_m"],
                 a["altura_m"], a["peitoril_m"]))
        mapa[w["id"]] = parede_id
    con.commit()
    return {"projeto_id": pid, "mapa": mapa}


def test_cada_parede_bate_com_o_v7_em_pecas_e_kg(con, oraculo, projeto_109):
    from lsf.geradores.estrutura import gerar_parede

    divergentes = []
    for w in oraculo["paredes"]:
        r = gerar_parede(con, projeto_109["mapa"][w["id"]])
        tipos = {}
        for p in r.pecas:
            tipos[p.tipo] = tipos.get(p.tipo, 0) + 1
        kg = sum(r.kg_por_perfil.values())
        ref = w["ref"]
        if tipos != ref["pecas_por_tipo"]:
            divergentes.append(f"{w['id']}: tipos {tipos} != {ref['pecas_por_tipo']}")
        elif abs(kg - ref["kg"]) > 0.01 * ref["kg"]:
            divergentes.append(f"{w['id']}: kg {kg:.2f} != {ref['kg']:.2f}")
    assert not divergentes, "\n".join(divergentes)


def test_total_das_paredes_dentro_do_gate_de_10pct(con, oraculo, projeto_109):
    from lsf.geradores.estrutura import gerar_estrutura

    est = gerar_estrutura(con, projeto_109["projeto_id"])
    ref = oraculo["total_paredes"]
    assert est.kg_liquido == pytest.approx(ref["kg_liquido"], rel=0.10)
    assert est.kg_comprado == pytest.approx(ref["kg_comprado"], rel=0.10)


def test_paredes_estimadas_rebaixam_a_confianca(con, oraculo, projeto_109):
    from lsf.geradores.estrutura import gerar_estrutura

    est = gerar_estrutura(con, projeto_109["projeto_id"])
    assert est.confianca == "estimado"      # há paredes est=1 e regras estimado
```

- [ ] **Step 2: Rodar e depurar até o verde**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_aceite_estrutura_v7.py -v
```

Se `test_cada_parede_bate...` falhar, a mensagem lista as paredes divergentes. Depurar UMA divergência por vez comparando o desenho: gere as peças da parede no Python e no node (chame `gerarPecas(wallToP(w, fi))` num script de scratch) e faça diff dos `(tipo, x0, y0, x1, y1)` ordenados. As causas prováveis, na ordem: epsilon trocado, `_round_js` faltando em algum ponto, ordem de geração diferente (kings antes dos montantes de campo), sill/head de janela.

**Não afrouxe a tolerância para passar** — 1% por parede é a definição de "porta fiel". Se uma divergência for um BUG do v7 (comportamento indefensável), registrar no commit e abrir exceção pontual comentada no teste, nunca silenciosa.

- [ ] **Step 3: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add tests/test_aceite_estrutura_v7.py
git commit -m "test(gerador): aceite parcial F2.1 — 53 paredes da 109.1506 batem com o v7 (peças idênticas, kg <=1%)"
```

---

### Task 8: `derivar_quantitativos` + documentação

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (acrescentar `derivar_quantitativos`)
- Modify: `CLAUDE.md` (estado atual)
- Test: `tests/test_gerador_estrutura.py` (acrescentar)

**Interfaces:**
- Consumes: `gerar_estrutura` (Task 6); `eap_item` folha `03.01` (seed); UNIQUE de `quantitativo` (migração 001).
- Produces: `derivar_quantitativos(con, projeto_id) -> dict` com `{"kg_comprado", "confianca"}`; grava `quantitativo` `origem='PARAMETRICO'` na folha 03.01 — o orçamento paramétrico aparece na casca web sem tocar em `app/`.

- [ ] **Step 1: Testes que falham**

```python
def test_derivar_quantitativos_grava_parametrico_na_folha_03_01(con, planta):
    from lsf.geradores.estrutura import derivar_quantitativos, gerar_estrutura

    planta(comp=4.0)
    resultado = derivar_quantitativos(con, planta.projeto_id)
    linha = con.execute(
        "SELECT q.quantidade, q.origem, q.confianca, e.codigo"
        "  FROM quantitativo q JOIN eap_item e ON e.id = q.eap_item_id"
        " WHERE q.projeto_id = ?", (planta.projeto_id,)).fetchone()
    assert linha[3] == "03.01"
    assert linha[1] == "PARAMETRICO"
    assert linha[2] == "estimado"
    est = gerar_estrutura(con, planta.projeto_id)
    assert linha[0] == pytest.approx(est.kg_comprado)
    assert resultado["kg_comprado"] == pytest.approx(est.kg_comprado)


def test_derivar_de_novo_substitui_a_linha_em_vez_de_duplicar(con, planta):
    from lsf.geradores.estrutura import derivar_quantitativos

    planta(comp=4.0)
    derivar_quantitativos(con, planta.projeto_id)
    planta(comp=3.0)                                    # a planta cresceu
    derivar_quantitativos(con, planta.projeto_id)
    linhas = con.execute(
        "SELECT COUNT(*) FROM quantitativo WHERE projeto_id = ?",
        (planta.projeto_id,)).fetchone()[0]
    assert linhas == 1                                  # D2: uma linha ativa por item
```

- [ ] **Step 2: Rodar e ver falhar; Step 3: implementar**

Acrescentar a `src/lsf/geradores/estrutura.py`:

```python
def derivar_quantitativos(con, projeto_id: int) -> dict:
    """Escreve o kg comprado do gerador na folha 03.01 da EAP como quantitativo
    PARAMETRICO (D2: re-derivar substitui a linha; a UNIQUE garante)."""
    est = gerar_estrutura(con, projeto_id)
    folha = con.execute(
        "SELECT id FROM eap_item WHERE codigo = '03.01'").fetchone()
    if folha is None:
        raise DadoIndisponivel("EAP sem a folha 03.01 (estrutura LSF, kg)")
    con.execute(
        "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem,"
        " confianca, origem_regra) VALUES (?,?,?,'PARAMETRICO',?,?)"
        " ON CONFLICT (projeto_id, eap_item_id) DO UPDATE SET"
        "   quantidade=excluded.quantidade, origem=excluded.origem,"
        "   confianca=excluded.confianca, origem_regra=excluded.origem_regra",
        (projeto_id, folha[0], est.kg_comprado, est.confianca,
         "gerador de estrutura F2.1 (porta fiel v7) — kg comprado em barras 6m"))
    con.commit()
    return {"kg_comprado": est.kg_comprado, "confianca": est.confianca}
```

- [ ] **Step 4: Atualizar `CLAUDE.md`**

Na seção "Estado atual", acrescentar:

```markdown
- **`src/lsf/geradores/estrutura.py` — F2.1 parcial (paredes)**: porta fiel do `gerarPecas` do v7 lendo `planta_normalizada` + `perfil_lsf`/`regra_lsf`/`guia_de`/`verga_escalonamento` (migração 006 corrigiu os perfis pós-override). Aceite parcial: 53 paredes da 109.1506 batem com o v7 headless (peças por tipo idênticas, kg ≤1%; total ≤10%) — oráculo em `tests/fixtures/estrutura_v7_109_1506.json`, gerado por `tools/extrair_estrutura_v7.mjs`. `derivar_quantitativos` grava kg comprado na folha 03.01 como PARAMETRICO (confiança nunca melhor que `estimado`: regras sem calibração de obra). Falta para fechar o aceite da fase: lajes, escadas, cobertura, forro.
```

E na seção "Fase atual", marcar o item 1 como parcialmente feito:

```markdown
1. ~~Portar o gerador de estrutura do v7~~ **PAREDES FEITAS** (aceite parcial ✓); faltam lajes/escadas/cobertura/forro para o kg total do edifício.
```

- [ ] **Step 5: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add src/lsf/geradores/estrutura.py tests/test_gerador_estrutura.py CLAUDE.md
git commit -m "feat(gerador): derivar_quantitativos — kg comprado vira quantitativo PARAMETRICO na 03.01"
```

---

## Critério de aceite do plano

1. Suíte inteira verde (spikes inclusos).
2. `tests/test_aceite_estrutura_v7.py` verde: 53 paredes com peças por tipo idênticas ao v7 e kg ≤1% por parede; total das paredes ≤10%.
3. Num banco com a planta da 109.1506 carregada, `derivar_quantitativos` faz o orçamento da casca web exibir a linha 03.01 com origem PARAMETRICO e confiança `estimado` — sem nenhuma mudança em `app/`.
4. Nenhuma linha do asset v7 editada; nenhum hardcode de perfil/regra no gerador.

**O que este plano NÃO fecha:** o aceite da Fase 2 (kg total do edifício ≤10%) — lajes, escadas, cobertura e forro são os próximos sub-projetos, cada um com sua spec/plano. O gate é humano e continua de pé.
