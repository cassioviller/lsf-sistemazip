# Gerador de estrutura — lajes, escadas, cobertura e forro — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portar do v7 os quatro sistemas de estrutura que faltam (laje, escada, cobertura, forro) para fechar o aceite da Fase 2: kg de aço do edifício com desvio ≤ 10% vs v7.

**Architecture:** Helpers de geometria puros (novo módulo) derivam o footprint por pavimento do contorno das paredes externas de `planta_normalizada` (cadeia D3). Inputs que o arquitetônico não dá (esp de laje, inclinação de cobertura, vãos de escada, áreas descobertas) viram tabelas de projeto (migração 008), seedadas para a 109.1506 a partir do oráculo estendido. Quatro geradores portados fielmente do v7 emitem peças 3D com `origem_regra` + confiança; a agregação soma tudo na folha 03.01 como PARAMETRICO. O aceite compara peça-a-peça e kg total contra o oráculo regenerado.

**Tech Stack:** Python 3 + SQLite (`.venv/bin/python`), Node 20 headless (extrator do v7), pytest.

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origem_regra`).

**Convenções deste plano:**
- **TESTE_CMD** = `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest`. A suíte inteira (`$TESTE_CMD tests/`) roda verde antes de **cada** commit — inclusive fixes de subagente (override do projeto sobre a SDD).
- **NODE** = `/nix/store/0akvkk9k1a7z5vjp34yz6dr91j776jhv-nodejs-20.11.1/bin/node`.
- **Port fiel**: onde a task manda "portar de v7:LINHAS", o alvo é reproduzir o algoritmo peça-a-peça — mesmos epsilons, mesma ordem de operações, `Math.round`/`toFixed` via `_round_js` (já existe em `estrutura.py`). O oráculo é o juiz. `mkP`→`Peca`, `mkAc`→`Acessorio`, `scan`/`cortarSpan`/`polyArea`→ funções da Task 1. Perfis/regras vêm do banco (Task 2/3), nunca constantes JS.
- **Assets READ-ONLY**: `assets/calc-edificio-109_1506-v7-steel.html` é consulta, nunca edição.

---

### Task 1: Helpers de geometria (módulo puro)

**Files:**
- Create: `src/lsf/geradores/geometria.py`
- Test: `tests/test_geometria.py`

**Interfaces:**
- Consumes: nada (funções puras, sem SQL).
- Produces:
  - `encadear_contorno(segmentos: list[tuple[tuple[float,float], tuple[float,float]]]) -> list[tuple[float,float]]` — recebe segmentos externos `((ax,az),(bx,bz))`, devolve polígono (lista de vértices) fechado sem repetir o primeiro.
  - `poly_area(poligono: list[tuple[float,float]]) -> float`
  - `poly_perim(poligono: list[tuple[float,float]]) -> float`
  - `scan(poligono, valor: float, eixo: str) -> list[tuple[float,float]]` — `eixo` ∈ {'z','x'}; intervalos internos filtrados >0,05.
  - `cortar_span(a: float, b: float, vaos: list[tuple[float,float]]) -> list[tuple[float,float]]`
  - `bbox(poligono) -> dict` com chaves `x0,x1,z0,z1`.

- [ ] **Step 1: Escrever os testes que falham** — `tests/test_geometria.py`

```python
import math
from lsf.geradores.geometria import (
    encadear_contorno, poly_area, poly_perim, scan, cortar_span, bbox,
)

RET = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]  # 4x3

def test_poly_area_retangulo():
    assert poly_area(RET) == 12.0

def test_poly_perim_retangulo():
    assert poly_perim(RET) == 14.0

def test_bbox_retangulo():
    assert bbox(RET) == {"x0": 0.0, "x1": 4.0, "z0": 0.0, "z1": 3.0}

def test_encadear_contorno_fecha_o_poligono():
    # segmentos fora de ordem, devem encadear no retângulo (tolerância 0,02)
    segs = [((4.0, 0.0), (4.0, 3.0)), ((0.0, 0.0), (4.0, 0.0)),
            ((0.0, 3.0), (0.0, 0.0)), ((4.0, 3.0), (0.0, 3.0))]
    poly = encadear_contorno(segs)
    assert len(poly) == 4
    assert poly_area(poly) == 12.0

def test_scan_linha_horizontal_atravessa_retangulo():
    # z=1,5 corta o retângulo em [0,4]
    assert scan(RET, 1.5, "z") == [(0.0, 4.0)]

def test_scan_vertical_atravessa_retangulo():
    assert scan(RET, 2.0, "x") == [(0.0, 3.0)]

def test_scan_forma_em_L_devolve_dois_intervalos():
    # L: recorte no canto superior direito → linha alta corta 1 vão; linha baixa corta cheio
    L = [(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (2.0, 1.0), (2.0, 3.0), (0.0, 3.0)]
    assert scan(L, 0.5, "z") == [(0.0, 4.0)]
    assert scan(L, 2.0, "z") == [(0.0, 2.0)]

def test_cortar_span_remove_vao_interno():
    assert cortar_span(0.0, 4.0, [(1.0, 2.0)]) == [(0.0, 1.0), (2.0, 4.0)]

def test_cortar_span_vao_cobre_tudo():
    assert cortar_span(0.0, 4.0, [(0.0, 4.0)]) == []

def test_cortar_span_sem_vaos_mantem():
    assert cortar_span(1.0, 3.0, []) == [(1.0, 3.0)]

def test_cortar_span_descarta_fragmento_menor_que_0_1():
    # v7:797 filtra segmentos <0,1m — o toco de 0,05m à esquerda do vão some
    assert cortar_span(0.0, 4.0, [(0.05, 2.0)]) == [(2.0, 4.0)]
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_geometria.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'lsf.geradores.geometria'`.

- [ ] **Step 3: Implementar `src/lsf/geradores/geometria.py`**

Porta fiel de v7:684–794 (`chainPolygon`, `polyArea`, `polyPerim`, `scan`, `cortarSpan`; `bbox` de v7:731). Funções puras, sem SQL. Código completo:

```python
"""Helpers de geometria — porta fiel de v7:684-794 (chainPolygon/scan/polyArea/
cortarSpan). Funções puras: recebem polígonos (lista de vértices (x,z)) e devolvem
áreas, intervalos e recortes. Sem SQL, sem estado. O footprint por pavimento é o
contorno das paredes externas encadeado por `encadear_contorno` (cadeia D3)."""
from __future__ import annotations

import math

_EPS_NO = 0.02    # tolerância de coincidência de nós (v7: 0.02)
_EPS_IV = 0.05    # intervalo mínimo internamente válido em scan (v7: 0.05)
_EPS_SPAN = 0.1   # fragmento mínimo em cortar_span (v7:797)


def encadear_contorno(segmentos):
    """chainPolygon: encadeia segmentos externos num polígono fechado."""
    segs = [{"a": tuple(a), "b": tuple(b)} for a, b in segmentos]
    if not segs:
        return []
    pts = [segs[0]["a"], segs[0]["b"]]
    segs.pop(0)
    eq = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1]) < _EPS_NO
    guard = 0
    while segs and guard < 200:
        guard += 1
        tail = pts[-1]
        i = next((k for k, s in enumerate(segs)
                  if eq(s["a"], tail) or eq(s["b"], tail)), -1)
        if i < 0:
            break
        s = segs.pop(i)
        pts.append(s["b"] if eq(s["a"], tail) else s["a"])
    if eq(pts[0], pts[-1]):
        pts.pop()
    return pts


def poly_area(poligono):
    a = 0.0
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a / 2)


def poly_perim(poligono):
    p = 0.0
    n = len(poligono)
    for i in range(n):
        a = poligono[i]
        b = poligono[(i + 1) % n]
        p += math.hypot(b[0] - a[0], b[1] - a[1])
    return p


def scan(poligono, valor, eixo):
    """Interseções do polígono com a linha eixo=valor → intervalos internos."""
    xs = []
    n = len(poligono)
    for i in range(n):
        a = poligono[i]
        b = poligono[(i + 1) % n]
        a1, b1 = (a[1], b[1]) if eixo == "z" else (a[0], b[0])
        a0, b0 = (a[0], b[0]) if eixo == "z" else (a[1], b[1])
        if (a1 <= valor < b1) or (b1 <= valor < a1):
            t = (valor - a1) / (b1 - a1)
            xs.append(a0 + t * (b0 - a0))
    xs.sort()
    iv = []
    i = 0
    while i + 1 < len(xs):
        if xs[i + 1] - xs[i] > _EPS_IV:
            iv.append((xs[i], xs[i + 1]))
        i += 2
    return iv


def cortar_span(a, b, vaos):
    """Recorta o intervalo [a,b] pelos vãos (aberturas). Porta de v7:788-798 —
    inclui o filtro final que descarta fragmentos < 0,1 m (v7:797)."""
    segs = [[a, b]]
    for va, vb in vaos:
        for i in range(len(segs) - 1, -1, -1):
            s, e = segs[i]
            if va <= s and vb >= e:
                segs.pop(i)
            elif va > s and vb < e:
                segs[i:i + 1] = [[s, va], [vb, e]]
            elif s < va < e:
                segs[i] = [s, va]
            elif s < vb < e:
                segs[i] = [vb, e]
    return [(s, e) for s, e in segs if e - s > _EPS_SPAN]  # v7:797 descarta <0,1m


def bbox(poligono):
    xs = [p[0] for p in poligono]
    zs = [p[1] for p in poligono]
    return {"x0": min(xs), "x1": max(xs), "z0": min(zs), "z1": max(zs)}
```

> **Atenção ao port de `cortarSpan`** (v7:788-796): confira as 4 cláusulas contra a fonte antes de fechar — a ordem `elif s < va < e` vs `elif s < vb < e` importa. O test `test_cortar_span_remove_vao_interno` (vão interno) fixa o caso de split.

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_geometria.py -q`
Expected: PASS (10 testes).

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS (todos).
```bash
git add src/lsf/geradores/geometria.py tests/test_geometria.py
git commit -m "feat(geometria): helpers puros scan/encadear_contorno/cortar_span/poly_area (porta v7)"
```

---

### Task 2: Migração 008 — tabelas de projeto da estrutura

**Files:**
- Create: `db/migrations/008_estrutura_projeto.sql`
- Test: `tests/test_migracao_008.py`

**Interfaces:**
- Consumes: `projeto(id)`, `perfil_lsf(codigo)` (existentes).
- Produces (schema): tabelas `laje`, `laje_abertura`, `laje_extensao`, `escada`, `cobertura`, `area_descoberta`, `forro` — colunas conforme o SQL abaixo. Referências de perfil como colunas TEXT (FK conceitual `perfil_lsf.codigo`).

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_migracao_008.py`

```python
import sqlite3
from db.build_db import construir  # padrão dos outros test_migracao_*

def _cols(con, tabela):
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}

def test_tabelas_de_projeto_existem(tmp_path):
    dbp = tmp_path / "t.db"
    construir(dbp)  # construir(db_path: pathlib.Path, recriar=False) -> dict
    con = sqlite3.connect(dbp)
    tabelas = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"laje", "laje_abertura", "laje_extensao", "escada",
            "cobertura", "area_descoberta", "forro"} <= tabelas

def test_laje_tem_colunas_esperadas(tmp_path):
    dbp = tmp_path / "t.db"
    construir(dbp)  # construir(db_path: pathlib.Path, recriar=False) -> dict
    con = sqlite3.connect(dbp)
    assert {"projeto_id", "id_laje", "grupo", "pav_base", "nivel", "esp_m",
            "perfil_viga", "perfil_enrijecedor", "bloqueador_max_m",
            "confianca"} <= _cols(con, "laje")

def test_cobertura_referencia_perfis_por_texto(tmp_path):
    dbp = tmp_path / "t.db"
    construir(dbp)  # construir(db_path: pathlib.Path, recriar=False) -> dict
    con = sqlite3.connect(dbp)
    assert {"banzo_perfil", "alma_perfil", "guia_banzo_perfil",
            "inclinacao", "beiral_m", "confianca"} <= _cols(con, "cobertura")

def test_area_descoberta_check_tipo(tmp_path):
    dbp = tmp_path / "t.db"
    construir(dbp)  # construir(db_path: pathlib.Path, recriar=False) -> dict
    con = sqlite3.connect(dbp)
    pid = con.execute(
        "INSERT INTO projeto (codigo,nome,referencia,uf,desonerado)"
        " VALUES ('X','x','2024-01','SP',1)").lastrowid
    con.execute("INSERT INTO area_descoberta (projeto_id,nome,x,z,w,d,tipo,confianca)"
                " VALUES (?,?,?,?,?,?,?,?)", (pid, "v", 0, 0, 1, 1, "faixa", "estimado"))
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO area_descoberta (projeto_id,nome,x,z,w,d,tipo,confianca)"
                    " VALUES (?,?,?,?,?,?,?,?)", (pid, "q", 0, 0, 1, 1, "porao", "estimado"))
```

> Confirmar a assinatura real do builder em `db/build_db.py` (função e parâmetro do caminho do db) e alinhar o import/uso — os testes `test_migracao_00X.py` existentes já mostram o padrão exato; seguir o deles.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_migracao_008.py -q`
Expected: FAIL — tabelas inexistentes.

- [ ] **Step 3: Escrever `db/migrations/008_estrutura_projeto.sql`**

Tudo em português. Confiança em cada tabela. Referências de perfil como TEXT (FK conceitual — SQLite não força; documentar).

```sql
-- Migração 008 — inputs de projeto da estrutura (o que o arquitetônico não dá,
-- como o solo): esp de laje, inclinação de cobertura, vãos de escada, áreas
-- descobertas. O footprint NÃO é gravado — deriva das paredes externas (D3).
-- Instância da obra (109.1506) é seedada pelo teste a partir do oráculo, não aqui.

CREATE TABLE laje (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  id_laje TEXT NOT NULL,
  grupo TEXT NOT NULL,
  pav_base INTEGER NOT NULL,
  nivel REAL NOT NULL,
  esp_m REAL NOT NULL,
  perfil_viga TEXT NOT NULL DEFAULT 'auto',
  perfil_enrijecedor TEXT NOT NULL,
  bloqueador_max_m REAL NOT NULL,
  chapa_piso_tipo TEXT,
  chapa_piso_larg REAL,
  chapa_piso_alt REAL,
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id, id_laje)
);

CREATE TABLE laje_abertura (
  id INTEGER PRIMARY KEY,
  laje_id INTEGER NOT NULL REFERENCES laje(id),
  tipo TEXT NOT NULL,
  x REAL NOT NULL, z REAL NOT NULL, w REAL NOT NULL, d REAL NOT NULL
);

CREATE TABLE laje_extensao (
  id INTEGER PRIMARY KEY,
  laje_id INTEGER NOT NULL REFERENCES laje(id),
  x REAL NOT NULL, z REAL NOT NULL, w REAL NOT NULL, d REAL NOT NULL
);

CREATE TABLE escada (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  id_escada TEXT NOT NULL,
  grupo TEXT NOT NULL,
  vao_x REAL NOT NULL, vao_z REAL NOT NULL, vao_w REAL NOT NULL, vao_d REAL NOT NULL,
  altura REAL NOT NULL,
  nivel_inicial REAL NOT NULL,
  formato TEXT NOT NULL,
  longarina_perfil_a TEXT NOT NULL,
  longarina_perfil_b TEXT NOT NULL,
  degrau_perfil TEXT NOT NULL,
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id, id_escada)
);

CREATE TABLE cobertura (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  id_cobertura TEXT NOT NULL,
  grupo TEXT NOT NULL,
  grupo_tesouras TEXT NOT NULL,
  nivel_base REAL NOT NULL,
  beiral_m REAL NOT NULL,
  inclinacao REAL NOT NULL,
  banzo_perfil TEXT NOT NULL,
  guia_banzo_perfil TEXT NOT NULL,
  alma_perfil TEXT NOT NULL,
  telha_tipo TEXT NOT NULL,
  telha_perda_pct REAL NOT NULL,
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id, id_cobertura)
);

CREATE TABLE area_descoberta (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  nome TEXT NOT NULL,
  x REAL NOT NULL, z REAL NOT NULL, w REAL NOT NULL, d REAL NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('faixa','patio')),
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico'))
);

CREATE TABLE forro (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  perfil TEXT NOT NULL,
  perfil_borda TEXT NOT NULL,
  esp_m REAL NOT NULL,
  grupo TEXT NOT NULL,
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id)
);
```

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_migracao_008.py -q`
Expected: PASS (4 testes).

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS. (`db/build_db.py` é não-destrutivo — a migração nova aplica uma vez.)
```bash
git add db/migrations/008_estrutura_projeto.sql tests/test_migracao_008.py
git commit -m "feat(db): migração 008 — tabelas de projeto laje/escada/cobertura/area_descoberta/forro"
```

---

### Task 3: Seed de conhecimento — regras estruturais, cargas e perfis

**Files:**
- Modify: `db/seed.sql` (append de linhas idempotentes)
- Test: `tests/test_seed_estrutura.py`

**Interfaces:**
- Consumes: tabelas `regra_lsf(chave,valor,unidade,referencia)`, `perfil_lsf(codigo,familia,tipo,drywall,alma_mm,aba_mm,enrijecedor_mm,espessura_mm,massa_kg_m)`.
- Produces (dados): chaves de regra `laje_esp_m`, `laje_bloqueador_max_m`, `laje_vao_ue200`, `laje_enrij_c_f200`, `laje_enrij_c_f250`, `laje_fix_mesa_paraf`, `laje_fix_alma_paraf`, `escada_espelho_max`, `escada_piso_min`, `escada_fix_lateral_mm`, `cobertura_esp_tesoura`, `cobertura_passo_mont`, `cobertura_beiral_m`, `cobertura_gusset_paraf`, `cobertura_box_paraf_mm`, `cobertura_cb_passo`, `carga_sc`, `carga_g`, `aco_fy`, `aco_E`, `coef_gm`, `flecha_lim`, `sec_ue250_a`, `sec_ue250_wx`, `sec_ue250_ix`. Perfis novos em `perfil_lsf`.

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_seed_estrutura.py`

```python
def _regra(con, chave):
    r = con.execute("SELECT valor FROM regra_lsf WHERE chave=?", (chave,)).fetchone()
    return r[0] if r else None

def test_regras_de_laje_seedadas(con):
    assert _regra(con, "laje_esp_m") == 0.40
    assert _regra(con, "laje_bloqueador_max_m") == 2.40
    assert _regra(con, "laje_vao_ue200") == 4.0

def test_cargas_estruturais_seedadas_com_referencia(con):
    for chave in ("carga_sc", "carga_g", "aco_fy", "aco_E", "coef_gm", "flecha_lim"):
        row = con.execute(
            "SELECT valor, referencia FROM regra_lsf WHERE chave=?", (chave,)).fetchone()
        assert row is not None, chave
        assert row[1] and ("NBR" in row[1]), f"{chave} sem referência normativa"

def test_perfis_novos_com_massa(con):
    for cod, massa in [("U202#0.95", 2.10), ("U252#1.25", 3.26),
                       ("W310x32.7", 32.7), ("HSS100x100x4.8", 14.2)]:
        m = con.execute("SELECT massa_kg_m FROM perfil_lsf WHERE codigo=?",
                        (cod,)).fetchone()
        assert m is not None and m[0] == massa, cod
```

> A fixture `con` (conexão em memória construída de schema+migrações+seed, na ordem do
> `build_db.py`) já existe em `tests/conftest.py:14`. **Não usar `base`** — essa é o dict de
> referência travada `{referencia,uf,desonerado}`, não uma conexão.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_seed_estrutura.py -q`
Expected: FAIL — chaves/perfis ausentes.

- [ ] **Step 3: Acrescentar as linhas em `db/seed.sql`**

Seguir o padrão idempotente já usado no arquivo: `ON CONFLICT (chave)/(codigo) DO UPDATE SET ... = excluded....` — nunca INSERT OR REPLACE/IGNORE. Valores e referências de v7:645-681 e v7:635-642 (`dimensionaViga`/`CARGAS`/`SEC_Ue250`). Cargas/aço com `referencia` = NBR 6120 / NBR 14762.

```sql
-- ============ Estrutura: regras de laje/escada/cobertura (v7:656-681) ============
INSERT INTO regra_lsf (chave,valor,unidade,referencia) VALUES
  ('laje_esp_m',0.40,'m','v7 REGRAS_SIS.laje.esp'),
  ('laje_bloqueador_max_m',2.40,'m','A4 [p.27 LAJE-005] bloqueador por vão'),
  ('laje_vao_ue200',4.0,'m','v7: vão ef >4m → Ue250'),
  ('laje_enrij_c_f200',0.176,'m','REGRA LAJE-009: C=176mm (laje 200) [p.27-38]'),
  ('laje_enrij_c_f250',0.226,'m','REGRA LAJE-010: C=226mm (laje 250) [p.39]'),
  ('laje_fix_mesa_paraf',4,'un','DP-01A: 2 paraf/ligação × 2 extremidades'),
  ('laje_fix_alma_paraf',5,'un','REGRA LAJE-007 [DL-01 p.21-39]'),
  ('escada_espelho_max',0.175,'m','v7 REGRAS_SIS.escada.espelhoMax'),
  ('escada_piso_min',0.28,'m','v7 REGRAS_SIS.escada.pisoMin'),
  ('escada_fix_lateral_mm',150,'mm','1ES1: reforço 140 @150mm'),
  ('cobertura_esp_tesoura',1.20,'m','v7 REGRAS_SIS.cobertura.espTesoura'),
  ('cobertura_passo_mont',0.40,'m','1TS41-46: ~10 montantes/3,77m [p.44-49]'),
  ('cobertura_beiral_m',0.30,'m','v7 PROJECT.cobertura.beiral'),
  ('cobertura_gusset_paraf',4,'un','1TS41/42: gusset por nó'),
  ('cobertura_box_paraf_mm',200,'mm','DX-09: box @200mm'),
  ('cobertura_cb_passo',0.60,'m','1CB p.56-77: travessas 140#0.80 @0,60')
ON CONFLICT (chave) DO UPDATE SET
  valor=excluded.valor, unidade=excluded.unidade, referencia=excluded.referencia;

-- ============ Cargas e seção p/ dimensionar_viga (v7:633-642) — NBR ============
-- Valores e unidades EXATOS do v7 (CARGAS v7:633, SEC_Ue250 v7:634). A aritmética
-- de dimensionar_viga (Task 4) reproduz o v7 com os fatores de conversão (1e6/1e9/1e12),
-- então o seed guarda os números na unidade v7 — NÃO converter aqui.
INSERT INTO regra_lsf (chave,valor,unidade,referencia) VALUES
  ('carga_sc',4.0,'kN/m²','NBR 6120: sobrecarga (v7 CARGAS.sc=4.0)'),
  ('carga_g',1.3,'kN/m²','NBR 6120: permanente (v7 CARGAS.g=1.3)'),
  ('aco_fy',230,'MPa','NBR 14762: ZAR230 fy (v7 CARGAS.fy=230)'),
  ('aco_E',200000,'MPa','NBR 14762: módulo E (v7 CARGAS.E=2.0e5)'),
  ('coef_gm',1.10,'-','NBR 14762: γM (v7 CARGAS.gM=1.10)'),
  ('flecha_lim',350,'-','NBR 14762: L/350 (v7 CARGAS.flecha=350)'),
  ('sec_ue250_a',708,'mm²','SEC_Ue250.A (v7:634)'),
  ('sec_ue250_wx',46300,'mm³','SEC_Ue250.Wx=46.3e3 (v7:634)'),
  ('sec_ue250_ix',5780000,'mm⁴','SEC_Ue250.Ix=5.78e6 (v7:634)')
ON CONFLICT (chave) DO UPDATE SET
  valor=excluded.valor, unidade=excluded.unidade, referencia=excluded.referencia;

-- ============ Perfis novos (v7:645-654) — todos 'estimado' (sem calibração R6) =====
INSERT INTO perfil_lsf (codigo,familia,tipo,drywall,alma_mm,aba_mm,enrijecedor_mm,espessura_mm,massa_kg_m) VALUES
  ('U202#0.95','U202','guia',0,202,40,NULL,0.95,2.10),
  ('U252#1.25','U252','guia',0,252,40,NULL,1.25,3.26),
  ('Ue140#0.80','Ue140','montante',0,140,40,12,0.80,1.53),
  ('U142#0.80','U142','guia',0,142,40,NULL,0.80,1.39),
  ('W310x32.7','W310','laminado',0,310,102,NULL,6.6,32.7),
  ('HSS100x100x4.8','HSS100','laminado',0,100,100,NULL,4.8,14.2)
ON CONFLICT (codigo) DO UPDATE SET
  familia=excluded.familia, tipo=excluded.tipo, alma_mm=excluded.alma_mm,
  aba_mm=excluded.aba_mm, enrijecedor_mm=excluded.enrijecedor_mm,
  espessura_mm=excluded.espessura_mm, massa_kg_m=excluded.massa_kg_m;
```

> **PENDÊNCIA DO IMPLEMENTADOR — valores exatos:** os `0.000?` de `SEC_Ue250` (A/Wx/Ix) e as unidades de `aco_fy`/`aco_E` devem ser lidos direto de v7:635-642 e das constantes `SEC_Ue250`/`CARGAS` no asset (grep `SEC_Ue250` e `CARGAS` no HTML). O v7 usa SI misto (N, mm, MPa) — reproduzir a MESMA aritmética que `dimensionaViga` faz (Task 4 valida os 3 modos). Se a unidade escolhida no seed diferir do que a Task 4 espera, o teste de `dimensionar_viga` acusa. Confirmar antes de commitar. Perfis: conferir se `Ue90#0.95`/`Ue90#1.25`/`Ue90#0.80` e `U92#1.25` já existem no seed/migração 006; adicionar só os ausentes (a UNIQUE/ON CONFLICT protege duplicata).

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_seed_estrutura.py -q`
Expected: PASS (3 testes).

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS. (Seed reaplica idempotente — conhecimento novo chega a banco existente.)
```bash
git add db/seed.sql tests/test_seed_estrutura.py
git commit -m "feat(db): seed de regras/cargas NBR e perfis de laje/escada/cobertura (estimado)"
```

---

### Task 4: `dimensionar_viga` — verificação estrutural (regra de engenharia)

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (nova função + helper `_cargas`)
- Test: `tests/test_dimensiona_viga.py`

**Interfaces:**
- Consumes: `regra_lsf` (chaves `carga_sc`, `carga_g`, `aco_fy`, `aco_E`, `coef_gm`, `flecha_lim`, `sec_ue250_*` — Task 3).
- Produces:
  - `_cargas(con) -> dict` — lê as chaves de carga/seção do banco (dado ausente = `DadoIndisponivel`).
  - `dimensionar_viga(con, vao_m: float, trib_m: float) -> dict` com chaves `modo` ∈ {'simples','dupla','laminada'}, `M`, `MRd`, `delta`, `dLim`, `V`, `VRd` (floats arredondados como o v7).

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_dimensiona_viga.py`

```python
import pytest
from lsf.geradores.estrutura import dimensionar_viga, DadoIndisponivel

# Limiares JÁ VERIFICADOS reproduzindo a aritmética exata de v7:636-642 com as
# constantes do seed (SEC_Ue250 A=708/Wx=46300/Ix=5.78e6; CARGAS sc=4.0/g=1.3/
# fy=230/gM=1.10/E=2.0e5/flecha=350) a trib=0,40 m:
#   simples até 4,88 m · dupla 4,89–6,15 m · laminada ≥ 6,16 m.
# Por isso vao 2.0 → simples, 5.0 → dupla, 8.0 → laminada. Se a implementação
# der outro modo nesses vãos, a aritmética/unidade do port divergiu do v7.

def test_vao_curto_viga_simples(con):
    r = dimensionar_viga(con, vao_m=2.0, trib_m=0.40)
    assert r["modo"] == "simples"
    assert r["M"] <= r["MRd"] and r["delta"] <= r["dLim"]

def test_vao_medio_exige_viga_dupla(con):
    r = dimensionar_viga(con, vao_m=5.0, trib_m=0.40)
    assert r["modo"] == "dupla"

def test_vao_grande_exige_laminada(con):
    r = dimensionar_viga(con, vao_m=8.0, trib_m=0.40)
    assert r["modo"] == "laminada"

def test_carga_ausente_e_erro(con):
    con.execute("DELETE FROM regra_lsf WHERE chave='carga_sc'")
    with pytest.raises(DadoIndisponivel):
        dimensionar_viga(con, vao_m=2.0, trib_m=0.40)
```

> Fixture `con` (conexão), não `base`. Ver nota na Task 3.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_dimensiona_viga.py -q`
Expected: FAIL — `dimensionar_viga` inexistente.

- [ ] **Step 3: Implementar em `src/lsf/geradores/estrutura.py`**

Porta fiel de v7:635-642. `origem_regra` embutido nas mensagens de warning já existe nos geradores; aqui a função devolve o dict e o CHAMADOR (Task 6) anota `origem_regra`. **Regra de engenharia**: docstring cita NBR 6120 (SC/G) e NBR 14762 (M/MRd, δ=L/350, flambagem de alma V). Ajustar unidades ao que o seed gravou (Task 3). Esqueleto (preencher a aritmética idêntica ao v7):

```python
def _cargas(con) -> dict:
    chaves = ("carga_sc", "carga_g", "aco_fy", "aco_E", "coef_gm", "flecha_lim",
              "sec_ue250_a", "sec_ue250_wx", "sec_ue250_ix")
    regras = _regras(con)
    faltando = [c for c in chaves if c not in regras]
    if faltando:
        raise DadoIndisponivel(f"regra_lsf sem cargas/seção: {faltando}")
    return {c: regras[c] for c in chaves}


def dimensionar_viga(con, vao_m: float, trib_m: float) -> dict:
    """Verifica viga de laje: ELS (flecha L/flecha_lim), ELU (M<=MRd, V<=VRd).
    Devolve modo simples|dupla|laminada. origem_regra: NBR 6120 (SC=carga_sc,
    G=carga_g) + NBR 14762 (M/MRd/W; δ; flambagem de alma h/t)."""
    C = _cargas(con)
    # ... aritmética IDÊNTICA a v7:636-642, nas unidades do seed.
    #     pp = A*7850e-9*9.81 ; wS = (sc+g)*trib+pp ; wU = 1.4*g*trib+1.5*sc*trib+1.4*pp
    #     M = wU*L²/8 ; MRd = Wx*fy/gM ; delta = 5*wS*L⁴/(384*E*Ix) ; dLim = L*1000/flecha
    #     V = wU*L/2 ; VRd = 0.905*E*5.34*2.0³/250/gM/1000
    #     okS = M<=MRd and delta<=dLim and V<=VRd
    #     okD = M<=2*MRd and delta/2<=dLim and V<=2*VRd
    #     modo = 'simples' if okS else ('dupla' if okD else 'laminada')
    ...
    return {"modo": modo, "M": _round_js(M, 1), "MRd": _round_js(MRd, 1),
            "delta": _round_js(delta, 1), "dLim": _round_js(dLim, 0),
            "V": _round_js(V, 1), "VRd": _round_js(VRd, 1)}
```

> **Fidelidade das unidades**: o seed (Task 3) guarda os valores nas unidades do v7 (A/Wx/Ix em mm; fy/E em MPa; sc/g em kN/m²). Reproduza a sequência EXATA de v7:636-642 com os mesmos fatores (`1e6`, `1e12`, e `7850e-9` no peso próprio) — não "arrume" para SI. Os limiares já verificados (simples até 4,88 m · dupla até 6,15 m · laminada ≥6,16 m a trib 0,40) são o juiz; se os vãos 2.0/5.0/8.0 não caírem em simples/dupla/laminada, a unidade divergiu. `VRd = 0.905*E*5.34*2.0³/250/gM/1000` usa `E` em MPa direto.

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_dimensiona_viga.py -q`
Expected: PASS (4 testes).

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS.
```bash
git add src/lsf/geradores/estrutura.py tests/test_dimensiona_viga.py
git commit -m "feat(estrutura): dimensionar_viga (NBR 6120/14762) — modos simples/dupla/laminada"
```

---

### Task 5: Estender o extrator do v7 e regenerar o oráculo (4 sistemas)

**Files:**
- Modify: `tools/extrair_estrutura_v7.mjs`
- Modify (regenerar, não à mão): `tests/fixtures/estrutura_v7_109_1506.json`
- Test: `tests/test_fixture_estrutura.py` (estender)

**Interfaces:**
- Consumes: v7 globals `buildBuilding`, `PROJECT`, `gerarPecasLaje`, `gerarPecasEscada`, `gerarPecasCobertura`, `gerarPecasForro` (todos nos blocos `<script>` já eval'd pelo extrator).
- Produces: fixture JSON com, além de `paredes`, as chaves:
  - `projeto`: `{niveis, footprint: [poly_pav0, poly_pav1, poly_pav2], lajes, escadas, cobertura, descobertas, forro}` (os inputs de projeto que a Task 6-9 vão inserir nas tabelas da migração 008).
  - `sistemas`: `{laje: {pecas, acess, kg_liquido, kg_comprado}, escada: {...}, cobertura: {...}, forro: {...}}`.
  - `total_edificio`: `{kg_liquido, kg_comprado}` (paredes + 4 sistemas).

- [ ] **Step 1: Estender `tools/extrair_estrutura_v7.mjs`**

Depois de expor os globals atuais, acrescentar `buildBuilding`, `PROJECT` e as 4 funções à desestruturação; chamar `buildBuilding()` para preencher `BUILDING`; iterar `PROJECT.lajes`/`escadas`, chamar `gerarPecasCobertura(PROJECT.cobertura)` e `gerarPecasForro()`. Somar kg por sistema com o `massaKgM` já usado para paredes. Adicionar `projeto` (com `BUILDING.footprint`/`niveis` + os arrays de `PROJECT`) e `sistemas`/`total_edificio` ao `JSON.stringify` final. Não alterar a extração de paredes existente.

> Ler v7:729-774 para os nomes exatos dos campos de `PROJECT.lajes/escadas/cobertura/descobertas/forro` e `buildBuilding()`. O extrator já faz `transformCode`/`Proxy noop` — só estender `requiredNames` e a desestruturação.

- [ ] **Step 2: Regenerar o oráculo**

Run:
```bash
/nix/store/0akvkk9k1a7z5vjp34yz6dr91j776jhv-nodejs-20.11.1/bin/node \
  tools/extrair_estrutura_v7.mjs > tests/fixtures/estrutura_v7_109_1506.json
```
Expected: JSON válido com as novas chaves. Conferir à mão:
```bash
.venv/bin/python -c "import json;d=json.load(open('tests/fixtures/estrutura_v7_109_1506.json'));print(list(d),list(d['sistemas']),d['total_edificio'])"
```
Expected: mostra `paredes`, `projeto`, `sistemas`, `total_edificio`; os 4 sistemas presentes; `total_edificio` na ordem de 23-31 mil kg.

- [ ] **Step 3: Estender `tests/test_fixture_estrutura.py`**

```python
def test_fixture_tem_os_quatro_sistemas():
    import json, pathlib
    d = json.loads((pathlib.Path("tests/fixtures/estrutura_v7_109_1506.json")).read_text())
    assert {"laje", "escada", "cobertura", "forro"} <= set(d["sistemas"])
    for s in d["sistemas"].values():
        assert s["pecas"] and s["kg_comprado"] > 0

def test_fixture_tem_inputs_de_projeto():
    import json, pathlib
    d = json.loads((pathlib.Path("tests/fixtures/estrutura_v7_109_1506.json")).read_text())
    assert len(d["projeto"]["footprint"]) == 3
    assert d["projeto"]["lajes"] and d["projeto"]["escadas"]
    assert d["projeto"]["cobertura"] and d["projeto"]["forro"]

def test_total_edificio_na_ordem_esperada():
    import json, pathlib
    d = json.loads((pathlib.Path("tests/fixtures/estrutura_v7_109_1506.json")).read_text())
    assert 20000 < d["total_edificio"]["kg_liquido"] < 27000
    assert 27000 < d["total_edificio"]["kg_comprado"] < 35000
```

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_fixture_estrutura.py -q`
Expected: PASS. (O teste de paredes existente deve continuar verde — não mexer nele.)

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS.
```bash
git add tools/extrair_estrutura_v7.mjs tests/fixtures/estrutura_v7_109_1506.json tests/test_fixture_estrutura.py
git commit -m "feat(oráculo): extrator do v7 emite laje/escada/cobertura/forro + inputs de projeto"
```

---

### Task 6: `gerar_laje` + `Peca` 3D + loader de projeto no teste

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (`Peca` ganha `sistema`,`grupo`,`z0`,`z1`; nova `gerar_laje`)
- Modify: `tests/conftest.py` (fixture `projeto_109_estrutura` que carrega paredes + tabelas da migração 008 a partir do oráculo)
- Test: `tests/test_gerador_laje.py`

**Interfaces:**
- Consumes: `geometria.scan/cortar_span/poly_area/bbox/encadear_contorno` (Task 1); `dimensionar_viga` (Task 4); tabelas `laje`/`laje_abertura`/`laje_extensao` (Task 2); perfis/regras (Task 3); oráculo (Task 5).
- Produces:
  - `Peca` com campos novos `sistema: str`, `grupo: str`, `z0: float=0.0`, `z1: float=0.0`; `comp` passa a `hypot(Δx,Δy,Δz)` (parede fica z=0, comp inalterado).
  - `contorno_pavimento(con, projeto_id, nivel) -> list[tuple[float,float]]` (footprint derivado das paredes externas).
  - `gerar_laje(con, laje_id) -> tuple[list[Peca], list[Acessorio], list[str]]` (peças, acessórios, alertas).
  - fixture `projeto_109_estrutura` (conftest) devolvendo `(con, projeto_id)` com paredes + laje/escada/cobertura/forro carregados.

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_gerador_laje.py`

```python
def test_laje_peças_por_tipo_batem_com_o_oraculo(projeto_109_estrutura, oraculo):
    con, projeto_id = projeto_109_estrutura
    laje_id = con.execute("SELECT id FROM laje ORDER BY id LIMIT 1").fetchone()[0]
    pecas, acess, alertas = gerar_laje(con, laje_id)
    ref = oraculo["sistemas"]["laje"]
    from collections import Counter
    tipos = Counter(p.tipo for p in pecas)
    ref_tipos = Counter(p["tipo"] for p in ref["pecas"] if p["grupo"] == "1LJ")
    assert tipos == ref_tipos  # mesma contagem por tipo

def test_laje_kg_comprado_dentro_de_10pct(projeto_109_estrutura, oraculo):
    con, projeto_id = projeto_109_estrutura
    # somar kg de todas as lajes vs kg de laje do oráculo (dentro de 10%)
    ...

def test_laje_confianca_nunca_melhor_que_estimado(projeto_109_estrutura):
    con, projeto_id = projeto_109_estrutura
    laje_id = con.execute("SELECT id FROM laje ORDER BY id LIMIT 1").fetchone()[0]
    pecas, _, _ = gerar_laje(con, laje_id)
    assert all(p for p in pecas)  # peças emitidas
    # nenhuma peça de regra carrega confiança melhor que 'estimado'
```

> `oraculo` já é fixture em `tests/test_aceite_estrutura_v7.py`; mover para `conftest.py` (scope module) para reuso, ou replicar. `projeto_109_estrutura` estende o `projeto_109` existente (paredes) inserindo as linhas de `d["projeto"]["lajes"/"escadas"/"cobertura"/"forro"/"descobertas"]` nas tabelas da migração 008.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_gerador_laje.py -q`
Expected: FAIL — `gerar_laje` inexistente / fixture ausente.

- [ ] **Step 3: Implementar**

(a) Estender `Peca` (dataclass) com `sistema: str = ""`, `grupo: str = ""`, `z0: float = 0.0`, `z1: float = 0.0`; garantir que `comp` das peças de parede continue idêntico (z=0 ⇒ hypot 3D = hypot 2D). Ajustar o `mk` das paredes se necessário para passar `sistema='parede'`.
(b) `contorno_pavimento`: ler paredes externas do nível (`SELECT ... FROM parede JOIN no_planta ... WHERE externa=1`), montar segmentos `((ax,az),(bx,bz))`, chamar `encadear_contorno`.
(c) `gerar_laje`: **porta fiel de v7:801-889**. Ler a linha de `laje` + `laje_abertura`/`laje_extensao`; footprint via `contorno_pavimento(con, projeto_id, pav_base)`; `bbox`, `scan`, `cortar_span` da Task 1; `dimensionar_viga` para o modo (viga simples/dupla/laminada); perfis `perfV`/`perfB` conforme regra `laje_vao_ue200`; bordas, vigas, bloqueadores alternados, enrijecedores, reforço de abertura, chapa de piso. Cada `Peca` com `sistema='laje'`, `grupo=laje.grupo`, `origem_regra` das mensagens do v7, `confianca` = pior(`laje.confianca`, `'estimado'`).

> Não reescrever o algoritmo — traduzir v7:801-889 linha a linha. O teste `test_laje_peças_por_tipo_batem_com_o_oraculo` fixa a contagem por tipo; se divergir, o port errou num `scan`/`cortar_span`/passo. `LAMINADO` (v7:816) é flag do projeto — no v7 é global; tratar como `False` salvo se o oráculo indicar viga laminada (a 109.1506 não usa laminada por padrão — confirmar no oráculo).

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_gerador_laje.py -q`
Expected: PASS.

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS. (Testes de parede seguem verdes — `Peca` retrocompatível.)
```bash
git add src/lsf/geradores/estrutura.py tests/conftest.py tests/test_gerador_laje.py
git commit -m "feat(estrutura): gerar_laje (porta v7) + Peca 3D + footprint derivado das paredes"
```

---

### Task 7: `gerar_escada`

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (`gerar_escada`)
- Test: `tests/test_gerador_escada.py`

**Interfaces:**
- Consumes: `Peca` 3D (Task 6); tabela `escada` (Task 2); regras `escada_*` (Task 3); oráculo (Task 5); `projeto_109_estrutura` (Task 6).
- Produces: `gerar_escada(con, escada_id) -> tuple[list[Peca], list[Acessorio], list[str]]`.

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_gerador_escada.py`

```python
from collections import Counter

def test_escada_peças_por_tipo_batem(projeto_109_estrutura, oraculo):
    con, _ = projeto_109_estrutura
    eid = con.execute("SELECT id FROM escada ORDER BY id LIMIT 1").fetchone()[0]
    pecas, acess, alertas = gerar_escada(con, eid)
    tipos = Counter(p.tipo for p in pecas)
    assert tipos.get("travessa_degrau", 0) > 0 and tipos.get("longarina", 0) > 0

def test_escada_kg_dentro_de_10pct(projeto_109_estrutura, oraculo):
    con, _ = projeto_109_estrutura
    ...  # soma kg de escada vs oráculo, ≤10%
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_gerador_escada.py -q`
Expected: FAIL — `gerar_escada` inexistente.

- [ ] **Step 3: Implementar** — porta fiel de v7:893-946.

Ler a linha `escada` (vão x/z/w/d, altura, nivel_inicial, perfis longarina_a/_b/degrau). Reproduzir o U com 2 lances + patamar: `nDeg`, `espelho`, `piso`, helper de coordenadas `P(u,w,y)`/`seg(...)`, lances 1 e 2, patamar, reforço lateral, acessórios (chapa L, gousset, parafusos, chapa de piso). `sistema='escada'`, `grupo=escada.grupo`, `origem_regra` das mensagens do v7, `confianca`=pior(`escada.confianca`,`'estimado'`). Alertas de piso mínimo / lance excede poço como no v7.

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_gerador_escada.py -q`
Expected: PASS.

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS.
```bash
git add src/lsf/geradores/estrutura.py tests/test_gerador_escada.py
git commit -m "feat(estrutura): gerar_escada (porta v7) — U com patamar, 2 lances"
```

---

### Task 8: `gerar_cobertura`

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (`gerar_cobertura`)
- Test: `tests/test_gerador_cobertura.py`

**Interfaces:**
- Consumes: `Peca` 3D (Task 6); `geometria.scan/bbox` (Task 1); tabelas `cobertura`/`area_descoberta` (Task 2); regras `cobertura_*` (Task 3); oráculo (Task 5); `projeto_109_estrutura`.
- Produces: `gerar_cobertura(con, cobertura_id) -> tuple[list[Peca], list[Acessorio], list[str]]`.

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_gerador_cobertura.py`

```python
from collections import Counter

def test_cobertura_tem_tesouras_e_paineis(projeto_109_estrutura, oraculo):
    con, _ = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura ORDER BY id LIMIT 1").fetchone()[0]
    pecas, acess, alertas = gerar_cobertura(con, cid)
    tipos = Counter(p.tipo for p in pecas)
    assert tipos.get("banzo_inferior", 0) > 0 and tipos.get("montante_tesoura", 0) > 0

def test_cobertura_kg_dentro_de_10pct(projeto_109_estrutura, oraculo):
    con, _ = projeto_109_estrutura
    ...  # soma kg de cobertura vs oráculo, ≤10%

def test_cobertura_area_descoberta_gera_alerta(projeto_109_estrutura):
    con, _ = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura ORDER BY id LIMIT 1").fetchone()[0]
    _, _, alertas = gerar_cobertura(con, cid)
    assert any("descoberta" in a.lower() or "varanda" in a.lower() for a in alertas)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_gerador_cobertura.py -q`
Expected: FAIL — `gerar_cobertura` inexistente.

- [ ] **Step 3: Implementar** — porta fiel de v7:949-1041.

Footprint do 3º pav via `contorno_pavimento`; `area_descoberta` tipo `faixa` recua o `bb.x0` e tipo `patio` abre vão + gera alerta. Tesoura Pratt real: `nT`, por tesoura `scan` da largura, banzos inferior/superior + guia (box), montantes @`cobertura_passo_mont`, diagonais Pratt alternadas, gussets por nó, diagonais de canto, painéis 1CB (perímetro + travessas + diagonais), acessórios (gusset, box parafuso, telha por trapézio × √(1+i²) × perda, cumeeira, calha). `sistema='cobertura'`, grupos `cobertura.grupo`/`grupo_tesouras`, `origem_regra`, `confianca`=pior(...,`'estimado'`).

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_gerador_cobertura.py -q`
Expected: PASS.

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS.
```bash
git add src/lsf/geradores/estrutura.py tests/test_gerador_cobertura.py
git commit -m "feat(estrutura): gerar_cobertura (porta v7) — tesoura Pratt + painéis 1CB"
```

---

### Task 9: `gerar_forro`

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (`gerar_forro`)
- Test: `tests/test_gerador_forro.py`

**Interfaces:**
- Consumes: `Peca` 3D (Task 6); `geometria.scan/bbox/contorno_pavimento`; tabela `forro` (Task 2); oráculo (Task 5); `projeto_109_estrutura`.
- Produces: `gerar_forro(con, projeto_id) -> tuple[list[Peca], list[Acessorio], list[str]]` (3 pavimentos).

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_gerador_forro.py`

```python
from collections import Counter

def test_forro_cobre_tres_pavimentos(projeto_109_estrutura, oraculo):
    con, projeto_id = projeto_109_estrutura
    pecas, acess, alertas = gerar_forro(con, projeto_id)
    tipos = Counter(p.tipo for p in pecas)
    assert tipos.get("borda_forro", 0) > 0 and tipos.get("perfil_forro", 0) > 0

def test_forro_kg_dentro_de_10pct(projeto_109_estrutura, oraculo):
    con, projeto_id = projeto_109_estrutura
    pecas, _, _ = gerar_forro(con, projeto_id)
    ...  # kg vs oráculo forro, ≤10%
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_gerador_forro.py -q`
Expected: FAIL — `gerar_forro` inexistente.

- [ ] **Step 3: Implementar** — porta fiel de v7:1045-1057.

Ler `forro` (perfil, perfil_borda, esp_m, grupo). Para cada pavimento (0,1,2): footprint via `contorno_pavimento`, `bbox`; borda no perímetro + perfis ao longo de z @`esp_m` via `scan`. `y = niveis[pav] + pe_direito - 0.05`. `sistema='forro'`, `grupo=forro.grupo`, `confianca`=pior(`forro.confianca`,`'estimado'`).

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_gerador_forro.py -q`
Expected: PASS.

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS.
```bash
git add src/lsf/geradores/estrutura.py tests/test_gerador_forro.py
git commit -m "feat(estrutura): gerar_forro (porta v7) — borda + perfis por pavimento"
```

---

### Task 10: Agregação total + aceite de kg do edifício (fecho da Fase 2)

**Files:**
- Modify: `src/lsf/geradores/estrutura.py` (`gerar_estrutura` soma os 4 sistemas + paredes; `derivar_quantitativos` inclui tudo)
- Test: `tests/test_aceite_estrutura_completa.py`

**Interfaces:**
- Consumes: `gerar_laje`/`gerar_escada`/`gerar_cobertura`/`gerar_forro` (Tasks 6-9); `plano_de_corte` (existente); oráculo (Task 5).
- Produces: `EstruturaProjeto` com `kg_liquido`/`kg_comprado` do edifício inteiro; `derivar_quantitativos` grava o total na 03.01.

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_aceite_estrutura_completa.py`

```python
def test_kg_total_do_edificio_dentro_de_10pct(projeto_109_estrutura, oraculo):
    con, projeto_id = projeto_109_estrutura
    est = gerar_estrutura(con, projeto_id)
    ref = oraculo["total_edificio"]
    assert abs(est.kg_liquido - ref["kg_liquido"]) / ref["kg_liquido"] <= 0.10
    assert abs(est.kg_comprado - ref["kg_comprado"]) / ref["kg_comprado"] <= 0.10

def test_derivar_quantitativos_grava_total_na_0301(projeto_109_estrutura):
    con, projeto_id = projeto_109_estrutura
    r = derivar_quantitativos(con, projeto_id)
    assert r["gravado"] is True
    q = con.execute(
        "SELECT quantidade, origem, confianca FROM quantitativo q"
        " JOIN eap_item e ON e.id=q.eap_item_id WHERE e.codigo='03.01'"
        " AND q.projeto_id=?", (projeto_id,)).fetchone()
    assert q[1] == "PARAMETRICO" and q[2] == "estimado"
    assert q[0] > 27000  # kg comprado do edifício (paredes + 4 sistemas)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `$TESTE_CMD tests/test_aceite_estrutura_completa.py -q`
Expected: FAIL — `gerar_estrutura` ainda só soma paredes.

- [ ] **Step 3: Implementar**

Em `gerar_estrutura`: depois das paredes, chamar `gerar_laje` (para cada `laje` do projeto), `gerar_escada` (cada `escada`), `gerar_cobertura` (cada `cobertura`), `gerar_forro`. Juntar todas as `Peca` em `todas`; `plano_de_corte(con, todas, barra)` já agrega por perfil; kg líquido/comprado somam o edifício inteiro. `confianca` = pior de todos os sistemas + `'estimado'`. `alertas` acumula os dos 4 sistemas. `derivar_quantitativos` continua gravando `est.kg_comprado` na 03.01 (agora o total) — atualizar a mensagem `origem_regra` para "gerador de estrutura F2 (paredes+laje+escada+cobertura+forro)".

> Se `test_kg_total_do_edificio_dentro_de_10pct` estourar 10%, é o Risco 1 do spec (footprint derivado ≠ v7). Diagnosticar por sistema (comparar kg de cada sistema vs oráculo) antes de qualquer fallback; **não** relaxar o 10% para passar. Se for o footprint, aplicar o fallback do spec (gravar footprint) num commit à parte, documentado.

- [ ] **Step 4: Rodar e confirmar verde**

Run: `$TESTE_CMD tests/test_aceite_estrutura_completa.py -q`
Expected: PASS — kg do edifício ≤10% vs v7 (líquido ~23.673 / comprado ~31.345).

- [ ] **Step 5: Suíte inteira + commit**

Run: `$TESTE_CMD tests/`
Expected: PASS (toda a suíte, spikes inclusos).
```bash
git add src/lsf/geradores/estrutura.py tests/test_aceite_estrutura_completa.py
git commit -m "feat(estrutura): gerar_estrutura soma paredes+4 sistemas — aceite kg edifício <=10% vs v7"
```

---

## Self-Review (writing-plans)

**Cobertura do spec:**
- Geometria (§1) → Task 1. Footprint derivado (§2) → Task 6 (`contorno_pavimento`). Migração 008 (§3) → Task 2. Seed regras/cargas/perfis (§4) → Task 3. `dimensionar_viga` (§5) → Task 4. 4 geradores (§6) → Tasks 6-9. Agregação (§7) → Task 10. Oráculo/aceite → Task 5 + Task 10. Testes (todos) → cada task. Riscos → Task 3 (unidades), Task 6/10 (footprint).
- **Fora de escopo** (junta 0,15m; calibração R6) → não há task que os toque. ✓

**Placeholders conscientes (não são hand-waving):** os `<A>`/`<B>` (vãos-limite de `dimensionar_viga`) e os `0.000?`/`0.000?` (seção `SEC_Ue250`) são valores que **só existem no asset v7** e devem ser lidos de lá pelo implementador — cada um traz a instrução exata de onde ler e qual teste os fixa. Não são "TODO": são o único ponto onde o número mora fora deste plano (o asset é READ-ONLY e não pode ser colado por licença/tamanho). O port dos geradores (Tasks 6-9) aponta linhas exatas do v7 e é validado peça-a-peça pelo oráculo — padrão idêntico ao que fechou o aceite das paredes.

**Consistência de tipos:** `Peca` (sistema/grupo/z0/z1) definida na Task 6, consumida por 7-9. `contorno_pavimento`/`dimensionar_viga`/`_cargas` assinaturas casam entre definição e uso. Fixture `projeto_109_estrutura` definida na Task 6, consumida por 7-10. `oraculo` (fixture) usada de 6 a 10.

## Execution Handoff

Ordem obrigatória: 1 → 2 → 3 → 4 → 5 → 6 → (7,8,9 podem paralelizar sobre a mesma árvore, arquivos de teste disjuntos, mas todas tocam `estrutura.py` — se paralelizar, o orquestrador serializa os commits) → 10. O aceite da Fase 2 é declarado pelo humano quando a Task 10 fecha verde (gate de fase — não a SDD).
