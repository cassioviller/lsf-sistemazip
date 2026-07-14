# Casca web do aplicativo LSF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao orçamentista um aplicativo web operável sobre os motores da Fase 1 — cadastrar projeto, lançar quantitativos MANUAL, rodar orçamento com BDI, e publicar uma proposta congelada que o cliente abre por link.

**Architecture:** FastAPI + Jinja + htmx numa pasta `app/`, chamando os motores puros existentes (`src/lsf/motores/orcamento.py`, `src/lsf/relatorios.py`) sem tocá-los. `app/` não contém regra de engenharia: um número na UI que não veio de um motor é bug de arquitetura. A publicação congela um snapshot (JSON + HTML) na tabela `proposta`; a rota pública serve o HTML congelado e nunca recalcula.

**Tech Stack:** Python 3.11 (`.venv/bin/python`), SQLite, FastAPI 0.139, Uvicorn, Jinja2, itsdangerous, python-multipart, htmx (vendored), pytest + `starlette.testclient`.

**Spec:** `docs/superpowers/specs/2026-07-14-aplicativo-casca-web-design.md`

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origemRegra`).

**Constraints adicionais desta feature:**

- **`app/` não contém regra de engenharia.** Nenhum cálculo de custo, BDI, carga ou confiança nasce em `app/`. `app/servicos/` chama os motores e traduz o resultado para a tela.
- **O app escreve apenas dado de instância** (`usuario`, `projeto`, `quantitativo`, `proposta`). Base de conhecimento (insumos, preços, composições, EAP, perfis, regras) continua em `db/seed.sql` + migrações versionadas no git.
- **Gates bloqueiam, não avisam.** Publicação com pendência de custo ou macroetapa zerada é recusada com HTTP 409.
- **Branch:** `fase-app-casca-web`, base `main`. Nunca implementar direto na `main`.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `db/build_db.py` (modificar) | Build não-destrutivo: ledger `schema_migrations`, seed idempotente, flag `--recriar` |
| `db/seed.sql` (modificar) | Todos os INSERT ganham `ON CONFLICT ... DO UPDATE` (reaplicável) |
| `db/migrations/005_usuario_proposta.sql` (criar) | Tabelas `usuario` e `proposta` |
| `app/db.py` (criar) | Conexão SQLite por request, `PRAGMA foreign_keys = ON` |
| `app/auth.py` (criar) | Hash scrypt, verificação, sessão, dependência `usuario_logado` |
| `app/servicos/orcamento.py` (criar) | Chama motor → view-model da tela de orçamento |
| `app/servicos/publicacao.py` (criar) | Pré-flight dos gates, congelamento do snapshot, revogação |
| `app/rotas/auth.py` (criar) | `/login`, `/logout` |
| `app/rotas/projetos.py` (criar) | `/projetos`, `/projetos/novo`, `/projetos/{id}` |
| `app/rotas/quantitativos.py` (criar) | Árvore da EAP + POST htmx |
| `app/rotas/orcamento.py` (criar) | `/projetos/{id}/orcamento` |
| `app/rotas/proposta.py` (criar) | `/projetos/{id}/publicar`, `/projetos/{id}/propostas`, revogar |
| `app/rotas/publico.py` (criar) | `/p/{token}` — read-only, sem sessão |
| `app/main.py` (criar) | `criar_app(db_path)` — fábrica; monta rotas, sessão, estáticos |
| `app/templates/*.html` (criar) | Jinja, herdando identidade de `docs/previews/` |
| `app/static/` (criar) | `veks.css`, `htmx.min.js` (vendored, BSD-2) |
| `tools/criar_usuario.py` (criar) | CLI para criar usuário (não há cadastro aberto) |
| `tests/test_build_db.py` (criar) | Build preserva dados; seed reaplicável |
| `tests/test_auth.py` (criar) | Login, sessão, proteção de rota |
| `tests/test_app_projetos.py` (criar) | CRUD de projeto |
| `tests/test_app_quantitativos.py` (criar) | Lançamento MANUAL; agrupador recusado |
| `tests/test_app_orcamento.py` (criar) | Tela de orçamento |
| `tests/test_app_proposta.py` (criar) | Gates recusam; snapshot congela |
| `tests/conftest.py` (modificar) | Fixtures `app_db` (arquivo temp) e `cliente` (TestClient) |

---

### Task 1: Build não-destrutivo do banco

**Por que primeiro:** `db/build_db.py:5` faz `db_path.unlink()`. Enquanto isso existir, qualquer projeto ou proposta gravada é apagada no próximo build da base de conhecimento. Nada mais pode ser construído com segurança antes disso.

**Files:**
- Modify: `db/build_db.py` (reescrita completa — hoje tem 16 linhas)
- Modify: `db/seed.sql` (27 comandos `INSERT` → forma idempotente)
- Test: `tests/test_build_db.py` (criar)

**Interfaces:**
- Consumes: `db/schema.sql`, `db/seed.sql`, `db/migrations/*.sql` (já existem)
- Produces: `db/build_db.py` expõe `construir(db_path: pathlib.Path, recriar: bool = False) -> dict` retornando `{"migracoes_aplicadas": list[str], "criado": bool}`. A tabela `schema_migrations(arquivo TEXT PRIMARY KEY, aplicada_em TEXT)` passa a existir em todo banco.

**Modelo mental:** `schema.sql` e as migrações são **estruturais** — aplicadas uma vez, registradas no ledger. `seed.sql` é **conhecimento declarativo** — reaplicado a **todo** build, de forma idempotente, porque a trilha de dados paralela (composições dos 8 grupos) vai adicionar e corrigir linhas nele. Um seed que só rodasse na criação deixaria bancos existentes sem o conhecimento novo.

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_build_db.py`:

```python
"""O build da base de conhecimento não pode destruir dado de instância."""
import sqlite3
import subprocess
import sys
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "db"))

from build_db import construir  # noqa: E402


def test_build_cria_banco_do_zero(tmp_path):
    db = tmp_path / "lsf.db"
    resultado = construir(db)
    assert resultado["criado"] is True
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM eap_item").fetchone()[0] > 0
    assert con.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] > 0
    con.close()


def test_build_repetido_preserva_dado_de_instancia(tmp_path):
    """O gesto sancionado (atualizar conhecimento) NÃO pode apagar projeto."""
    db = tmp_path / "lsf.db"
    construir(db)

    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO projeto (codigo, nome, cliente, referencia, uf, desonerado)"
        " VALUES ('109.1506', 'Edifício', 'Cliente X', '2026-06', 'SP', 0)"
    )
    con.commit()
    con.close()

    construir(db)  # segundo build — não pode apagar nada

    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM projeto").fetchone()[0] == 1
    assert con.execute("SELECT codigo FROM projeto").fetchone()[0] == "109.1506"
    con.close()


def test_build_repetido_nao_duplica_conhecimento(tmp_path):
    db = tmp_path / "lsf.db"
    construir(db)
    con = sqlite3.connect(db)
    antes = con.execute("SELECT COUNT(*) FROM insumo").fetchone()[0]
    con.close()

    construir(db)

    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM insumo").fetchone()[0] == antes
    con.close()


def test_migracao_aplicada_uma_vez_so(tmp_path):
    db = tmp_path / "lsf.db"
    primeira = construir(db)
    segunda = construir(db)
    assert len(primeira["migracoes_aplicadas"]) > 0
    assert segunda["migracoes_aplicadas"] == []  # nada pendente


def test_recriar_apaga_tudo_explicitamente(tmp_path):
    """A destruição continua disponível — mas só quando pedida em voz alta."""
    db = tmp_path / "lsf.db"
    construir(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, desonerado)"
        " VALUES ('X', 'X', '2026-06', 0)"
    )
    con.commit()
    con.close()

    construir(db, recriar=True)

    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM projeto").fetchone()[0] == 0
    con.close()


def test_cli_roda_sem_erro(tmp_path):
    db = tmp_path / "cli.db"
    proc = subprocess.run(
        [sys.executable, str(RAIZ / "db" / "build_db.py"), "--db", str(db)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert db.exists()
```

- [ ] **Step 2: Rodar e ver falhar pelo motivo certo**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_build_db.py -v
```

Esperado: FAIL — `ImportError: cannot import name 'construir' from 'build_db'` (hoje o arquivo é script solto, sem função).

- [ ] **Step 3: Reescrever `db/build_db.py`**

```python
"""Constrói/atualiza lsf_base.db a partir de schema.sql + seed.sql + migrations/.

NÃO destrutivo: dado de instância (projeto, quantitativo, proposta, usuario) sobrevive
a todo build. Estrutura (schema + migrações) é aplicada uma vez, registrada em
`schema_migrations`. O seed é conhecimento declarativo e é REAPLICADO a cada build,
de forma idempotente — é assim que composições novas chegam a um banco existente.

Uso:
    python3 db/build_db.py                 # cria ou atualiza db/lsf_base.db
    python3 db/build_db.py --db /tmp/x.db  # outro caminho
    python3 db/build_db.py --recriar       # APAGA e reconstrói (dev/teste)
"""
from __future__ import annotations

import argparse
import pathlib
import sqlite3

AQUI = pathlib.Path(__file__).parent
DB_PADRAO = AQUI / "lsf_base.db"

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  arquivo TEXT PRIMARY KEY,
  aplicada_em TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _ja_aplicadas(con) -> set[str]:
    return {linha[0] for linha in con.execute("SELECT arquivo FROM schema_migrations")}


def _aplicar(con, caminho: pathlib.Path) -> None:
    con.executescript(caminho.read_text())
    con.execute("INSERT INTO schema_migrations (arquivo) VALUES (?)", (caminho.name,))


def construir(db_path: pathlib.Path = DB_PADRAO, recriar: bool = False) -> dict:
    db_path = pathlib.Path(db_path)
    if recriar and db_path.exists():
        db_path.unlink()

    criado = not db_path.exists()
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(LEDGER)

    aplicadas = _ja_aplicadas(con)
    novas: list[str] = []

    if "schema.sql" not in aplicadas:
        _aplicar(con, AQUI / "schema.sql")
        novas.append("schema.sql")

    for migracao in sorted((AQUI / "migrations").glob("*.sql")):
        if migracao.name not in aplicadas:
            _aplicar(con, migracao)
            novas.append(migracao.name)

    # Seed: conhecimento declarativo, reaplicado sempre (idempotente por ON CONFLICT).
    con.executescript((AQUI / "seed.sql").read_text())

    con.commit()
    con.close()
    return {"migracoes_aplicadas": novas, "criado": criado}


def main() -> None:
    p = argparse.ArgumentParser(description="Constrói/atualiza a base LSF")
    p.add_argument("--db", default=str(DB_PADRAO))
    p.add_argument("--recriar", action="store_true", help="APAGA o banco antes (dev/teste)")
    args = p.parse_args()

    r = construir(pathlib.Path(args.db), recriar=args.recriar)
    con = sqlite3.connect(args.db)
    comp = con.execute("SELECT COUNT(*) FROM composicao").fetchone()[0]
    eap = con.execute("SELECT COUNT(*) FROM eap_item").fetchone()[0]
    proj = con.execute("SELECT COUNT(*) FROM projeto").fetchone()[0]
    con.close()
    verbo = "criado" if r["criado"] else "atualizado"
    print(
        f"{args.db} {verbo} ✓  ({len(r['migracoes_aplicadas'])} migração(ões) nova(s), "
        f"{comp} composições, {eap} itens de EAP, {proj} projeto(s) preservado(s))"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Tornar `db/seed.sql` idempotente**

Cada `INSERT INTO <tabela> (...) VALUES (...)` ganha uma cláusula `ON CONFLICT ... DO UPDATE` sobre a chave natural única da tabela. **Não** use `INSERT OR REPLACE` (apaga e reinsere, trocando o `rowid` e quebrando as FKs que apontam para a linha) nem `INSERT OR IGNORE` (engole violação de `CHECK`/`NOT NULL`, escondendo erro real de dado).

Chaves naturais já declaradas no `schema.sql`: `fonte(sigla)`, `data_base(fonte_id,referencia,uf,desonerado)`, `insumo(fonte_id,codigo_fonte)`, `insumo_preco(insumo_id,data_base_id)`, `composicao(fonte_id,codigo_fonte)`, `peso_camada(material)`, `classe_solo(classe)`, `mapeamento_item(item_derivado)`, `composicao_item(composicao_id,item_tipo,item_id)` (UNIQUE da migração 003), `perfil_lsf(codigo)`, `regra_lsf(chave)`.

Padrão a aplicar (exemplo real, para `fonte`):

```sql
INSERT INTO fonte (sigla,nome,tipo,papel,abrangencia,url) VALUES
 ('SINAPI','Sistema Nacional de Pesquisa de Custos','oficial','referencia','nacional','https://www.caixa.gov.br')
 -- ... demais linhas ...
ON CONFLICT (sigla) DO UPDATE SET
  nome=excluded.nome, tipo=excluded.tipo, papel=excluded.papel,
  abrangencia=excluded.abrangencia, url=excluded.url;
```

E para preço (o caso que mais importa — corrigir um preço no seed precisa realmente corrigir):

```sql
INSERT INTO insumo_preco (insumo_id,data_base_id,preco,confianca)
 SELECT ... -- SELECT existente, inalterado
ON CONFLICT (insumo_id,data_base_id) DO UPDATE SET
  preco=excluded.preco, confianca=excluded.confianca;
```

Aplicar a mesma transformação aos 27 comandos `INSERT` do arquivo, cada um com a sua chave natural. Se algum `INSERT` alimentar tabela **sem** chave única (verificar com `grep -n "CREATE TABLE\|UNIQUE" db/schema.sql`), adicionar a UNIQUE faltante numa migração `006_unique_seed.sql` em vez de usar `OR IGNORE` — sem chave natural não existe idempotência, só duplicação silenciosa.

- [ ] **Step 5: Rodar os testes do build**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_build_db.py -v
```

Esperado: 6 passed.

- [ ] **Step 6: Rodar a suíte inteira (os 67 existentes não podem quebrar)**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
```

Esperado: todos verdes. Atenção: `tests/conftest.py` monta o banco em memória aplicando `schema` + `seed` + migrações diretamente (não usa `build_db`), então o seed idempotente precisa continuar funcionando numa aplicação única — se algum `ON CONFLICT` estiver mal formado, é aqui que aparece.

- [ ] **Step 7: Commit**

```bash
git add db/build_db.py db/seed.sql tests/test_build_db.py
git commit -m "fix(db): build não-destrutivo — dado de instância sobrevive ao rebuild

build_db.py apagava o banco (unlink) antes de reconstruir. Inofensivo enquanto o
banco era descartável; destrutivo no minuto em que existirem projetos e propostas.
Agora: schema e migrações aplicados uma vez via ledger schema_migrations; seed
reaplicado a cada build de forma idempotente (ON CONFLICT DO UPDATE), que é como
conhecimento novo chega a um banco existente. --recriar preserva o rebuild do zero."
```

---

### Task 2: Migração 005 — `usuario` e `proposta`

**Files:**
- Create: `db/migrations/005_usuario_proposta.sql`
- Test: `tests/test_migracao_005.py`

**Interfaces:**
- Consumes: `projeto(id)` da migração 001.
- Produces: tabelas `usuario(id, email, senha_hash, nome, ativo, criado_em)` e `proposta(id, projeto_id, versao, token, publicada_em, publicada_por, snapshot_json, html, total_venda, bdi_pct, status)`. Task 3 usa `usuario`; Tasks 7 e 8 usam `proposta`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_migracao_005.py`:

```python
"""Migração 005: tabelas de instância do app (usuario, proposta)."""
import sqlite3

import pytest


def test_usuario_email_unico(con):
    con.execute(
        "INSERT INTO usuario (email, senha_hash, nome) VALUES ('a@veks.com', 'x', 'A')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO usuario (email, senha_hash, nome) VALUES ('a@veks.com', 'y', 'B')"
        )


def _projeto(con):
    cur = con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf, desonerado)"
        " VALUES ('109.1506', 'Edifício', '2026-06', 'SP', 0)"
    )
    return cur.lastrowid


def _usuario(con):
    cur = con.execute(
        "INSERT INTO usuario (email, senha_hash, nome) VALUES ('c@veks.com', 'x', 'C')"
    )
    return cur.lastrowid


def test_versao_unica_por_projeto(con):
    p, u = _projeto(con), _usuario(con)
    con.execute(
        "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
        " html, total_venda, bdi_pct) VALUES (?,1,'tok1',?,'{}','<h1/>',100.0,0.2779)",
        (p, u),
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
            " html, total_venda, bdi_pct) VALUES (?,1,'tok2',?,'{}','<h1/>',100.0,0.2779)",
            (p, u),
        )


def test_token_unico_entre_projetos(con):
    p, u = _projeto(con), _usuario(con)
    con.execute(
        "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
        " html, total_venda, bdi_pct) VALUES (?,1,'mesmo',?,'{}','<h1/>',100.0,0.2779)",
        (p, u),
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
            " html, total_venda, bdi_pct) VALUES (?,2,'mesmo',?,'{}','<h1/>',100.0,0.2779)",
            (p, u),
        )


def test_status_so_aceita_ativa_ou_revogada(con):
    p, u = _projeto(con), _usuario(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
            " html, total_venda, bdi_pct, status)"
            " VALUES (?,1,'t',?,'{}','<h1/>',100.0,0.2779,'rascunho')",
            (p, u),
        )


def test_proposta_exige_total_de_venda(con):
    """D4.1 na fronteira do banco: proposta sem preço não existe."""
    p, u = _projeto(con), _usuario(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
            " html, bdi_pct) VALUES (?,1,'t',?,'{}','<h1/>',0.2779)",
            (p, u),
        )
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_migracao_005.py -v
```

Esperado: FAIL com `sqlite3.OperationalError: no such table: usuario`.

- [ ] **Step 3: Escrever a migração**

Criar `db/migrations/005_usuario_proposta.sql`:

```sql
-- ============================================================
-- 005 — Instância do aplicativo: usuário e proposta publicada
-- Spec: docs/superpowers/specs/2026-07-14-aplicativo-casca-web-design.md
-- D5 levado ao limite: a proposta publicada CONGELA um snapshot. A rota pública
-- serve o HTML gravado e nunca recalcula — preço que mude amanhã não reescreve o
-- que o cliente recebeu.
-- ============================================================
PRAGMA foreign_keys = ON;

CREATE TABLE usuario (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  senha_hash TEXT NOT NULL,          -- scrypt$n$r$p$salt_hex$hash_hex
  nome TEXT NOT NULL,
  ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
  criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE proposta (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  versao INTEGER NOT NULL CHECK (versao >= 1),
  token TEXT NOT NULL UNIQUE,        -- secrets.token_urlsafe(32); não enumerável
  publicada_em TEXT NOT NULL DEFAULT (datetime('now')),
  publicada_por INTEGER NOT NULL REFERENCES usuario(id),
  snapshot_json TEXT NOT NULL,       -- OrcamentoVenda serializado (auditoria)
  html TEXT NOT NULL,                -- página congelada servida em /p/<token>
  -- D4.1: proposta sem preço não existe. O gate recusa antes de chegar aqui;
  -- o NOT NULL é a última linha de defesa.
  total_venda REAL NOT NULL,
  bdi_pct REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa','revogada')),
  UNIQUE (projeto_id, versao)
);
CREATE INDEX ix_proposta_projeto ON proposta (projeto_id);
```

- [ ] **Step 4: Rodar os testes**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_migracao_005.py -v
```

Esperado: 5 passed.

- [ ] **Step 5: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add db/migrations/005_usuario_proposta.sql tests/test_migracao_005.py
git commit -m "feat(db): migração 005 — usuario e proposta (snapshot congelado)"
```

---

### Task 3: Casca FastAPI + autenticação

**Files:**
- Create: `app/__init__.py`, `app/db.py`, `app/auth.py`, `app/main.py`
- Create: `app/rotas/__init__.py`, `app/rotas/auth.py`
- Create: `app/templates/base.html`, `app/templates/login.html`
- Create: `app/static/veks.css`, `app/static/htmx.min.js`
- Create: `tools/criar_usuario.py`
- Modify: `tests/conftest.py` (fixtures `app_db`, `cliente`, `usuario`)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: tabela `usuario` (Task 2); `construir()` de `db/build_db.py` (Task 1).
- Produces:
  - `app.main.criar_app(db_path: str | pathlib.Path, secret: str = "dev") -> FastAPI`
  - `app.auth.hash_senha(senha: str) -> str` · `app.auth.senha_confere(senha: str, hash_armazenado: str) -> bool`
  - `app.auth.usuario_logado` — dependência FastAPI que devolve `dict` com `id`, `email`, `nome`, ou redireciona a `/login` (HTTP 303) se não houver sessão.
  - `app.db.conexao` — dependência FastAPI que devolve `sqlite3.Connection` com `PRAGMA foreign_keys = ON` e `row_factory = sqlite3.Row`.
  - Tasks 4–8 consomem essas três.

- [ ] **Step 1: Registrar as dependências e a licença de cada uma**

```bash
.venv/bin/pip install fastapi uvicorn jinja2 itsdangerous python-multipart httpx
curl -sL https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js -o app/static/htmx.min.js
```

Acrescentar a `docs/04-referencias-colheita.md` a tabela de licenças (política obrigatória do CLAUDE.md — dependência nova exige licença verificada e registrada):

```markdown
## Dependências da casca web (verificadas em 2026-07-14)

| Pacote | Licença | Pode embutir? | Uso |
|---|---|---|---|
| FastAPI | MIT | sim | rotas |
| Uvicorn | BSD-3-Clause | sim | servidor ASGI |
| Jinja2 | BSD-3-Clause | sim | templates |
| itsdangerous | BSD-3-Clause | sim | assinatura do cookie de sessão |
| python-multipart | Apache-2.0 | sim | formulários |
| httpx | BSD-3-Clause | sim | só teste (TestClient) |
| htmx 2.0.4 | BSD-2-Clause | sim (vendored em `app/static/`) | interatividade sem build step |

Nenhuma GPL. Nenhuma sem licença. Todas permissivas → embutir é permitido.
```

- [ ] **Step 2: Escrever o teste que falha**

Primeiro, acrescentar as fixtures a `tests/conftest.py` (mantendo tudo que já existe no arquivo):

```python
# --- acrescentar ao final de tests/conftest.py ---
import pytest

sys.path.insert(0, str(RAIZ))       # para importar `app` e `db.build_db`
sys.path.insert(0, str(RAIZ / "db"))


@pytest.fixture
def app_db(tmp_path):
    """Banco de arquivo real (o app precisa de arquivo, não de :memory:)."""
    from build_db import construir

    caminho = tmp_path / "app.db"
    construir(caminho)
    return caminho


@pytest.fixture
def con_app(app_db):
    """Conexão ao banco do app, para arranjar dados nos testes."""
    c = sqlite3.connect(app_db)
    c.execute("PRAGMA foreign_keys = ON")
    c.row_factory = sqlite3.Row
    yield c
    c.commit()
    c.close()


@pytest.fixture
def usuario(con_app):
    """Usuário de teste: veks@veks.com / segredo123."""
    from app.auth import hash_senha

    cur = con_app.execute(
        "INSERT INTO usuario (email, senha_hash, nome) VALUES (?,?,?)",
        ("veks@veks.com", hash_senha("segredo123"), "Orçamentista"),
    )
    con_app.commit()
    return {"id": cur.lastrowid, "email": "veks@veks.com", "senha": "segredo123"}


@pytest.fixture
def cliente(app_db):
    """TestClient sem sessão."""
    from starlette.testclient import TestClient

    from app.main import criar_app

    return TestClient(criar_app(app_db, secret="teste"), follow_redirects=False)


@pytest.fixture
def logado(cliente, usuario):
    """TestClient já autenticado."""
    resposta = cliente.post(
        "/login", data={"email": usuario["email"], "senha": usuario["senha"]}
    )
    assert resposta.status_code == 303, resposta.text
    return cliente
```

Criar `tests/test_auth.py`:

```python
"""Autenticação da área interna. O app está exposto na internet para servir o link
do cliente — área interna sem login seria porta aberta."""


def test_hash_de_senha_nao_guarda_a_senha():
    from app.auth import hash_senha, senha_confere

    h = hash_senha("segredo123")
    assert "segredo123" not in h
    assert h.startswith("scrypt$")
    assert senha_confere("segredo123", h) is True
    assert senha_confere("errada", h) is False


def test_hash_tem_sal_diferente_a_cada_chamada():
    from app.auth import hash_senha

    assert hash_senha("igual") != hash_senha("igual")


def test_rota_interna_sem_sessao_redireciona_ao_login(cliente):
    resposta = cliente.get("/projetos")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_login_com_senha_certa_abre_sessao(cliente, usuario):
    resposta = cliente.post(
        "/login", data={"email": usuario["email"], "senha": usuario["senha"]}
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/projetos"


def test_login_com_senha_errada_recusa(cliente, usuario):
    resposta = cliente.post(
        "/login", data={"email": usuario["email"], "senha": "nao-e-essa"}
    )
    assert resposta.status_code == 401
    assert "senha" in resposta.text.lower() or "inválid" in resposta.text.lower()


def test_usuario_inativo_nao_entra(cliente, usuario, con_app):
    con_app.execute("UPDATE usuario SET ativo = 0 WHERE id = ?", (usuario["id"],))
    con_app.commit()
    resposta = cliente.post(
        "/login", data={"email": usuario["email"], "senha": usuario["senha"]}
    )
    assert resposta.status_code == 401


def test_logout_limpa_a_sessao(logado):
    """Não usa /projetos (que só existe na Task 4): checa a sessão pela rota protegida
    mais simples que já existe — se ainda houvesse sessão, /login redirecionaria."""
    logado.post("/logout")
    assert logado.get("/login").status_code == 200
```

O teste de logout **completo** (entrar → ver `/projetos` → sair → ser barrado) nasce na Task 4, quando `/projetos` existir. Aqui ele passaria a depender de rota inexistente e o commit sairia vermelho, contra a constraint.

- [ ] **Step 3: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_auth.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 4: Implementar `app/db.py`**

```python
"""Conexão SQLite por request. Uma conexão por request; sem pool, sem ORM."""
from __future__ import annotations

import sqlite3

from fastapi import Request


def abrir(db_path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")   # D4.1 começa aqui: FK é lei, não sugestão
    con.row_factory = sqlite3.Row
    return con


def conexao(request: Request):
    """Dependência FastAPI: conexão viva durante o request, fechada ao final."""
    con = abrir(request.app.state.db_path)
    try:
        yield con
        con.commit()
    finally:
        con.close()
```

- [ ] **Step 5: Implementar `app/auth.py`**

```python
"""Senha (scrypt, stdlib) e sessão (cookie assinado por SessionMiddleware).

Sem dependência de criptografia externa: hashlib.scrypt é padrão da linguagem.
Formato armazenado: scrypt$n$r$p$salt_hex$hash_hex
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

from app.db import conexao

N, R, P, DKLEN = 2**14, 8, 1, 32


class NaoAutenticado(Exception):
    """Levantada quando não há sessão; o handler do app redireciona a /login."""


def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.scrypt(senha.encode(), salt=sal, n=N, r=R, p=P, dklen=DKLEN)
    return f"scrypt${N}${R}${P}${sal.hex()}${dk.hex()}"


def senha_confere(senha: str, hash_armazenado: str) -> bool:
    try:
        marca, n, r, p, sal_hex, esperado_hex = hash_armazenado.split("$")
        if marca != "scrypt":
            return False
        dk = hashlib.scrypt(
            senha.encode(), salt=bytes.fromhex(sal_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(esperado_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), esperado_hex)


def autenticar(con: sqlite3.Connection, email: str, senha: str) -> sqlite3.Row | None:
    linha = con.execute(
        "SELECT id, email, nome, senha_hash, ativo FROM usuario WHERE email = ?", (email,)
    ).fetchone()
    if linha is None or not linha["ativo"]:
        return None
    if not senha_confere(senha, linha["senha_hash"]):
        return None
    return linha


def usuario_logado(request: Request, con: sqlite3.Connection = Depends(conexao)) -> dict:
    """Dependência: devolve o usuário da sessão ou levanta NaoAutenticado."""
    usuario_id = request.session.get("usuario_id")
    if usuario_id is None:
        raise NaoAutenticado()
    linha = con.execute(
        "SELECT id, email, nome FROM usuario WHERE id = ? AND ativo = 1", (usuario_id,)
    ).fetchone()
    if linha is None:
        request.session.clear()
        raise NaoAutenticado()
    return dict(linha)


def redirecionar_ao_login(request: Request, exc: NaoAutenticado) -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)
```

- [ ] **Step 6: Implementar `app/rotas/auth.py`**

```python
"""Login e logout. Sem cadastro aberto: usuário nasce por tools/criar_usuario.py."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import autenticar
from app.db import conexao

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def form_login(request: Request):
    return request.app.state.templates.TemplateResponse(
        request, "login.html", {"erro": None}
    )


@router.post("/login")
def entrar(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    con: sqlite3.Connection = Depends(conexao),
):
    usuario = autenticar(con, email, senha)
    if usuario is None:
        return request.app.state.templates.TemplateResponse(
            request, "login.html", {"erro": "E-mail ou senha inválidos."}, status_code=401
        )
    request.session["usuario_id"] = usuario["id"]
    return RedirectResponse("/projetos", status_code=303)


@router.post("/logout")
def sair(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
```

- [ ] **Step 7: Implementar `app/main.py` (fábrica)**

```python
"""Fábrica do app. O db_path é injetado — é o que permite o TestClient rodar
contra um banco temporário sem variável de ambiente global."""
from __future__ import annotations

import os
import pathlib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NaoAutenticado, redirecionar_ao_login
from app.rotas import auth as rotas_auth

AQUI = pathlib.Path(__file__).parent
RAIZ = AQUI.parent


def criar_app(db_path=None, secret: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("LSF_DB", RAIZ / "db" / "lsf_base.db")
    secret = secret or os.environ.get("LSF_SECRET")
    if not secret:
        raise RuntimeError("LSF_SECRET não definido — a sessão seria assinável por qualquer um")

    app = FastAPI(title="Orçamento LSF — Veks")
    app.state.db_path = pathlib.Path(db_path)
    app.state.templates = Jinja2Templates(directory=str(AQUI / "templates"))

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="lsf_sessao",
        https_only=os.environ.get("LSF_HTTPS_ONLY", "0") == "1",
        same_site="lax",
    )
    app.add_exception_handler(NaoAutenticado, redirecionar_ao_login)
    app.mount("/static", StaticFiles(directory=str(AQUI / "static")), name="static")
    app.include_router(rotas_auth.router)
    return app
```

Nota: `criar_app(app_db, secret="teste")` na fixture satisfaz a exigência do `secret`; em produção ele vem de `LSF_SECRET`. Um app que aceita sessão assinada com segredo default é um app com login decorativo — por isso a exceção, não um fallback silencioso.

- [ ] **Step 8: Templates e estáticos**

`app/templates/base.html` — herdar a identidade dos previews (`docs/previews/orcamento_analitico.html`: mesmas variáveis CSS, tema claro/escuro, fonte). Copiar o bloco `:root { --... }` de lá para `app/static/veks.css` em vez de reinventar cores.

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titulo %}Orçamento LSF — Veks{% endblock %}</title>
  <link rel="stylesheet" href="/static/veks.css">
  <script src="/static/htmx.min.js" defer></script>
</head>
<body>
  <header class="topo">
    <a class="marca" href="/projetos">Veks · Orçamento LSF</a>
    {% if usuario %}
    <form method="post" action="/logout"><button class="link">Sair ({{ usuario.nome }})</button></form>
    {% endif %}
  </header>
  <main>{% block conteudo %}{% endblock %}</main>
</body>
</html>
```

`app/templates/login.html`:

```html
{% extends "base.html" %}
{% block titulo %}Entrar{% endblock %}
{% block conteudo %}
<h1>Entrar</h1>
{% if erro %}<p class="erro" role="alert">{{ erro }}</p>{% endif %}
<form method="post" action="/login" class="cartao">
  <label>E-mail <input type="email" name="email" required autofocus></label>
  <label>Senha <input type="password" name="senha" required></label>
  <button type="submit">Entrar</button>
</form>
{% endblock %}
```

- [ ] **Step 9: CLI de criação de usuário**

Criar `tools/criar_usuario.py`:

```python
"""Cria usuário da área interna. Não há cadastro aberto — o app é interno.

Uso: .venv/bin/python tools/criar_usuario.py email@veks.com "Nome" --db db/lsf_base.db
A senha é lida do stdin (getpass), nunca do argv (argv vaza no histórico do shell).
"""
from __future__ import annotations

import argparse
import getpass
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.auth import hash_senha  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("email")
    p.add_argument("nome")
    p.add_argument("--db", default="db/lsf_base.db")
    args = p.parse_args()

    senha = getpass.getpass("Senha: ")
    if len(senha) < 8:
        raise SystemExit("senha curta demais (mínimo 8 caracteres)")
    if senha != getpass.getpass("Confirme: "):
        raise SystemExit("as senhas não conferem")

    con = sqlite3.connect(args.db)
    con.execute(
        "INSERT INTO usuario (email, senha_hash, nome) VALUES (?,?,?)",
        (args.email, hash_senha(senha), args.nome),
    )
    con.commit()
    con.close()
    print(f"usuário {args.email} criado ✓")


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: Rodar os testes de auth**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_auth.py -v
```

Esperado: 7 passed. Nenhum teste desta tarefa depende de rota de tarefa futura — a suíte fica verde e o commit é legítimo.

- [ ] **Step 11: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add app tools/criar_usuario.py tests/test_auth.py tests/conftest.py docs/04-referencias-colheita.md
git commit -m "feat(app): casca FastAPI + autenticação (scrypt, sessão assinada)"
```

---

### Task 4: Projetos — lista, cadastro, detalhe

**Files:**
- Create: `app/rotas/projetos.py`
- Create: `app/templates/projetos.html`, `app/templates/projeto_novo.html`, `app/templates/projeto.html`
- Modify: `app/main.py` (incluir o router)
- Test: `tests/test_app_projetos.py`

**Interfaces:**
- Consumes: `usuario_logado`, `conexao` (Task 3); tabelas `projeto` e `classe_solo`.
- Produces: rotas `GET /projetos`, `GET /projetos/novo`, `POST /projetos`, `GET /projetos/{id}`. Tasks 5–7 penduram links nesta tela.

**Desvio consciente da spec §7:** a spec previa uma rota separada `/projetos/{id}/propostas` para o histórico de versões. Ele cabe no próprio detalhe do projeto (são poucas linhas por obra), então a rota extra não existe — uma tela a menos para manter, zero função perdida. Se o histórico crescer a ponto de poluir o detalhe, ela volta.

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_app_projetos.py`:

```python
"""Cadastro de projeto: trava referência+UF+desonerado (D5) e a classe de solo (R3)."""


def test_lista_vazia(logado):
    resposta = logado.get("/projetos")
    assert resposta.status_code == 200
    assert "nenhum projeto" in resposta.text.lower()


def test_cadastrar_projeto(logado, con_app):
    resposta = logado.post(
        "/projetos",
        data={
            "codigo": "109.1506",
            "nome": "Edifício 109.1506",
            "cliente": "Cliente X",
            "referencia": "2026-06",
            "uf": "SP",
            "desonerado": "0",
            "sondagem_pendente": "1",
        },
    )
    assert resposta.status_code == 303

    linha = con_app.execute(
        "SELECT codigo, referencia, uf, desonerado, sondagem_pendente FROM projeto"
    ).fetchone()
    assert linha["codigo"] == "109.1506"
    assert linha["referencia"] == "2026-06"
    assert linha["uf"] == "SP"
    assert linha["desonerado"] == 0
    assert linha["sondagem_pendente"] == 1


def test_codigo_duplicado_recusado_com_mensagem(logado):
    dados = {
        "codigo": "109.1506", "nome": "A", "referencia": "2026-06",
        "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
    }
    assert logado.post("/projetos", data=dados).status_code == 303
    repetido = logado.post("/projetos", data=dados)
    assert repetido.status_code == 400
    assert "já existe" in repetido.text.lower()


def test_referencia_em_formato_errado_recusada(logado):
    resposta = logado.post(
        "/projetos",
        data={
            "codigo": "X", "nome": "X", "referencia": "junho/2026",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    assert resposta.status_code == 400
    assert "aaaa-mm" in resposta.text.lower()


def test_detalhe_mostra_sondagem_pendente(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "109.1506", "nome": "Edifício", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto").fetchone()["id"]
    resposta = logado.get(f"/projetos/{pid}")
    assert resposta.status_code == 200
    assert "sondagem" in resposta.text.lower()


def test_projeto_inexistente_404(logado):
    assert logado.get("/projetos/999").status_code == 404


def test_logout_barra_o_acesso_a_projetos(logado):
    """Fecha o par que a Task 3 não podia fechar: /projetos só existe agora."""
    assert logado.get("/projetos").status_code == 200
    logado.post("/logout")
    assert logado.get("/projetos").status_code == 303
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_projetos.py -v
```

Esperado: FAIL com 404 em todas (rotas não existem).

- [ ] **Step 3: Implementar `app/rotas/projetos.py`**

```python
"""Projetos. O projeto trava a REFERÊNCIA (D5.1): YYYY-MM + UF + desonerado."""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import usuario_logado
from app.db import conexao

router = APIRouter()

RE_REFERENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/projetos", response_class=HTMLResponse)
def listar(
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projetos = con.execute(
        "SELECT id, codigo, nome, cliente, referencia, uf FROM projeto ORDER BY criado_em DESC"
    ).fetchall()
    return request.app.state.templates.TemplateResponse(
        request, "projetos.html", {"projetos": projetos, "usuario": usuario}
    )


@router.get("/projetos/novo", response_class=HTMLResponse)
def form_novo(
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    solos = con.execute(
        "SELECT id, classe, descricao FROM classe_solo ORDER BY classe"
    ).fetchall()
    return request.app.state.templates.TemplateResponse(
        request, "projeto_novo.html", {"solos": solos, "usuario": usuario, "erro": None}
    )


def _erro_form(request, con, usuario, mensagem):
    solos = con.execute(
        "SELECT id, classe, descricao FROM classe_solo ORDER BY classe"
    ).fetchall()
    return request.app.state.templates.TemplateResponse(
        request, "projeto_novo.html",
        {"solos": solos, "usuario": usuario, "erro": mensagem},
        status_code=400,
    )


@router.post("/projetos")
def criar(
    request: Request,
    codigo: str = Form(...),
    nome: str = Form(...),
    referencia: str = Form(...),
    desonerado: int = Form(0),
    sondagem_pendente: int = Form(1),
    cliente: str = Form(""),
    uf: str = Form(""),
    classe_solo_id: int | None = Form(None),
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    if not RE_REFERENCIA.match(referencia):
        return _erro_form(
            request, con, usuario,
            "Referência deve estar no formato AAAA-MM (ex.: 2026-06)."
        )
    try:
        cur = con.execute(
            "INSERT INTO projeto (codigo, nome, cliente, referencia, uf, desonerado,"
            " classe_solo_id, sondagem_pendente) VALUES (?,?,?,?,?,?,?,?)",
            (codigo, nome, cliente or None, referencia, uf or None,
             desonerado, classe_solo_id, sondagem_pendente),
        )
    except sqlite3.IntegrityError:
        return _erro_form(request, con, usuario, f"O código {codigo} já existe.")
    con.commit()
    return RedirectResponse(f"/projetos/{cur.lastrowid}", status_code=303)


@router.get("/projetos/{projeto_id}", response_class=HTMLResponse)
def detalhe(
    projeto_id: int,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projeto = con.execute(
        "SELECT p.*, s.classe AS solo_classe FROM projeto p"
        " LEFT JOIN classe_solo s ON s.id = p.classe_solo_id WHERE p.id = ?",
        (projeto_id,),
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")
    propostas = con.execute(
        "SELECT versao, token, status, total_venda, publicada_em FROM proposta"
        " WHERE projeto_id = ? ORDER BY versao DESC",
        (projeto_id,),
    ).fetchall()
    return request.app.state.templates.TemplateResponse(
        request, "projeto.html",
        {"projeto": projeto, "propostas": propostas, "usuario": usuario},
    )
```

- [ ] **Step 4: Templates**

`app/templates/projetos.html`:

```html
{% extends "base.html" %}
{% block titulo %}Projetos{% endblock %}
{% block conteudo %}
<h1>Projetos</h1>
<a class="botao" href="/projetos/novo">Novo projeto</a>
{% if not projetos %}
  <p class="vazio">Nenhum projeto cadastrado ainda.</p>
{% else %}
<table>
  <thead><tr><th>Código</th><th>Nome</th><th>Cliente</th><th>Referência</th><th>UF</th></tr></thead>
  <tbody>
    {% for p in projetos %}
    <tr>
      <td><a href="/projetos/{{ p.id }}">{{ p.codigo }}</a></td>
      <td>{{ p.nome }}</td><td>{{ p.cliente or "—" }}</td>
      <td>{{ p.referencia }}</td><td>{{ p.uf or "—" }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}
{% endblock %}
```

`app/templates/projeto_novo.html`:

```html
{% extends "base.html" %}
{% block titulo %}Novo projeto{% endblock %}
{% block conteudo %}
<h1>Novo projeto</h1>
{% if erro %}<p class="erro" role="alert">{{ erro }}</p>{% endif %}
<form method="post" action="/projetos" class="cartao">
  <label>Código <input name="codigo" required placeholder="109.1506"></label>
  <label>Nome <input name="nome" required></label>
  <label>Cliente <input name="cliente"></label>
  <label>Referência (AAAA-MM) <input name="referencia" required placeholder="2026-06"></label>
  <label>UF <input name="uf" maxlength="2" placeholder="SP"></label>
  <label>Desonerado
    <select name="desonerado"><option value="0">Não</option><option value="1">Sim</option></select>
  </label>
  <label>Classe de solo
    <select name="classe_solo_id">
      <option value="">Não informada</option>
      {% for s in solos %}<option value="{{ s.id }}">{{ s.classe }} — {{ s.descricao }}</option>{% endfor %}
    </select>
  </label>
  <label>Sondagem
    <select name="sondagem_pendente">
      <option value="1">Pendente (rebaixa a confiança da fundação)</option>
      <option value="0">Realizada</option>
    </select>
  </label>
  <button type="submit">Cadastrar</button>
</form>
{% endblock %}
```

`app/templates/projeto.html`:

```html
{% extends "base.html" %}
{% block titulo %}{{ projeto.codigo }}{% endblock %}
{% block conteudo %}
<h1>{{ projeto.codigo }} — {{ projeto.nome }}</h1>
<dl class="cartao">
  <dt>Cliente</dt><dd>{{ projeto.cliente or "—" }}</dd>
  <dt>Referência travada</dt><dd>{{ projeto.referencia }} · {{ projeto.uf or "—" }} ·
    {{ "desonerado" if projeto.desonerado else "não desonerado" }}</dd>
  <dt>Solo</dt><dd>{{ projeto.solo_classe or "não informado" }}</dd>
</dl>
{% if projeto.sondagem_pendente %}
<p class="alerta" role="alert">
  ⚠ Sondagem pendente — a fundação sai com confiança rebaixada e o gate aparece na proposta.
</p>
{% endif %}
<nav class="acoes">
  <a class="botao" href="/projetos/{{ projeto.id }}/quantitativos">Quantitativos</a>
  <a class="botao" href="/projetos/{{ projeto.id }}/orcamento">Orçamento</a>
</nav>
{% if propostas %}
<h2>Propostas publicadas</h2>
<table>
  <thead><tr><th>Versão</th><th>Publicada</th><th>Total</th><th>Status</th><th>Link</th></tr></thead>
  <tbody>
    {% for p in propostas %}
    <tr>
      <td>v{{ p.versao }}</td><td>{{ p.publicada_em }}</td>
      <td>R$ {{ "%.2f"|format(p.total_venda) }}</td><td>{{ p.status }}</td>
      <td><a href="/p/{{ p.token }}">/p/{{ p.token[:8] }}…</a></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Registrar o router em `app/main.py`**

```python
from app.rotas import projetos as rotas_projetos
# ...
    app.include_router(rotas_projetos.router)
```

- [ ] **Step 6: Rodar os testes**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_projetos.py tests/test_auth.py -v
```

Esperado: 7 + 7 passed (o `test_logout_barra_o_acesso_a_projetos` fecha o par aberto na Task 3).

- [ ] **Step 7: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add app tests/test_app_projetos.py
git commit -m "feat(app): projetos — lista, cadastro (D5: referência travada) e detalhe"
```

---

### Task 5: Quantitativos MANUAL na árvore da EAP

**Files:**
- Create: `app/rotas/quantitativos.py`
- Create: `app/templates/quantitativos.html`, `app/templates/_linha_quantitativo.html`
- Modify: `app/main.py` (incluir o router)
- Test: `tests/test_app_quantitativos.py`

**Interfaces:**
- Consumes: `usuario_logado`, `conexao`; tabelas `eap_item`, `quantitativo`; trigger `trg_quantitativo_so_em_folha` (migração 001).
- Produces: `GET /projetos/{id}/quantitativos`, `POST /projetos/{id}/quantitativos` (fragmento htmx). O `POST` grava com `origem='MANUAL'` e `confianca='real'` (quantidade digitada por humano a partir de projeto é dado real; a etiqueta não é decorativa).

**Nota de domínio:** o `UNIQUE (projeto_id, eap_item_id)` da migração 001 significa **uma linha ativa por item** — reenviar o mesmo item é UPDATE, não INSERT duplicado. É o mesmo mecanismo que a migração PARAMETRICO→TAKEOFF vai usar (D2).

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_app_quantitativos.py`:

```python
"""Lançamento MANUAL. A EAP hoje tem 5 folhas com composição — o resto é agrupador."""
import pytest


@pytest.fixture
def projeto(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "109.1506", "nome": "Edifício", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    return con_app.execute("SELECT id FROM projeto").fetchone()["id"]


def _folha(con_app, codigo="03.01"):
    return con_app.execute(
        "SELECT id FROM eap_item WHERE codigo = ?", (codigo,)
    ).fetchone()["id"]


def _agrupador(con_app, codigo="03"):
    return con_app.execute(
        "SELECT id FROM eap_item WHERE codigo = ?", (codigo,)
    ).fetchone()["id"]


def test_tela_lista_folhas_da_eap(logado, projeto):
    resposta = logado.get(f"/projetos/{projeto}/quantitativos")
    assert resposta.status_code == 200
    assert "03.01" in resposta.text          # folha com composição
    assert "Estrutura LSF" in resposta.text  # macroetapa agrupadora


def test_lancar_quantidade_grava_manual_e_real(logado, con_app, projeto):
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": _folha(con_app), "quantidade": "1500,5"},
    )
    assert resposta.status_code == 200

    linha = con_app.execute(
        "SELECT quantidade, origem, confianca FROM quantitativo WHERE projeto_id = ?",
        (projeto,),
    ).fetchone()
    assert linha["quantidade"] == pytest.approx(1500.5)   # vírgula decimal pt-BR aceita
    assert linha["origem"] == "MANUAL"
    assert linha["confianca"] == "real"


def test_relancar_o_mesmo_item_atualiza_em_vez_de_duplicar(logado, con_app, projeto):
    folha = _folha(con_app)
    logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": folha, "quantidade": "1000"},
    )
    logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": folha, "quantidade": "2000"},
    )
    linhas = con_app.execute(
        "SELECT quantidade FROM quantitativo WHERE projeto_id = ?", (projeto,)
    ).fetchall()
    assert len(linhas) == 1
    assert linhas[0]["quantidade"] == pytest.approx(2000.0)


def test_quantidade_em_agrupador_recusada_como_erro_de_formulario(logado, con_app, projeto):
    """O trigger do banco existe; a UI não pode deixá-lo virar 500."""
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": _agrupador(con_app), "quantidade": "10"},
    )
    assert resposta.status_code == 400
    assert "folha" in resposta.text.lower()


def test_quantidade_negativa_recusada(logado, con_app, projeto):
    resposta = logado.post(
        f"/projetos/{projeto}/quantitativos",
        data={"eap_item_id": _folha(con_app), "quantidade": "-5"},
    )
    assert resposta.status_code == 400


def test_sem_sessao_nao_lanca(cliente, con_app):
    assert cliente.get("/projetos/1/quantitativos").status_code == 303
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_quantitativos.py -v
```

Esperado: FAIL — rotas inexistentes (404).

- [ ] **Step 3: Implementar `app/rotas/quantitativos.py`**

```python
"""Quantitativos MANUAL (D2: paramétrico e executivo diferem só na `origem`)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth import usuario_logado
from app.db import conexao

router = APIRouter()


def _numero_ptbr(texto: str) -> float:
    """Aceita '1500,5' e '1500.5'. Erro vira 400, não 500."""
    try:
        return float(texto.strip().replace(".", "").replace(",", "."))
    except ValueError:
        raise HTTPException(status_code=400, detail="quantidade inválida")


def _arvore(con: sqlite3.Connection, projeto_id: int) -> list[dict]:
    """Macroetapas com suas folhas e o quantitativo já lançado (se houver)."""
    itens = con.execute(
        "SELECT e.id, e.codigo, e.descricao, e.unidade, e.pai_id, e.composicao_id,"
        "       q.quantidade, q.origem"
        "  FROM eap_item e"
        "  LEFT JOIN quantitativo q ON q.eap_item_id = e.id AND q.projeto_id = ?"
        " ORDER BY e.codigo",
        (projeto_id,),
    ).fetchall()
    macros = [dict(i, folhas=[]) for i in itens if i["pai_id"] is None]
    por_id = {m["id"]: m for m in macros}
    for item in itens:
        if item["pai_id"] is not None and item["pai_id"] in por_id:
            por_id[item["pai_id"]]["folhas"].append(dict(item))
    return macros


@router.get("/projetos/{projeto_id}/quantitativos", response_class=HTMLResponse)
def tela(
    projeto_id: int,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projeto = con.execute(
        "SELECT id, codigo, nome FROM projeto WHERE id = ?", (projeto_id,)
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")
    return request.app.state.templates.TemplateResponse(
        request, "quantitativos.html",
        {"projeto": projeto, "macroetapas": _arvore(con, projeto_id), "usuario": usuario},
    )


@router.post("/projetos/{projeto_id}/quantitativos", response_class=HTMLResponse)
def lancar(
    projeto_id: int,
    request: Request,
    eap_item_id: int = Form(...),
    quantidade: str = Form(...),
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    valor = _numero_ptbr(quantidade)
    if valor < 0:
        raise HTTPException(status_code=400, detail="quantidade não pode ser negativa")

    try:
        # UNIQUE (projeto_id, eap_item_id): uma linha ativa por item (D2).
        con.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem, confianca)"
            " VALUES (?,?,?,'MANUAL','real')"
            " ON CONFLICT (projeto_id, eap_item_id) DO UPDATE SET"
            "   quantidade=excluded.quantidade, origem=excluded.origem,"
            "   confianca=excluded.confianca",
            (projeto_id, eap_item_id, valor),
        )
    except sqlite3.IntegrityError as erro:
        # trg_quantitativo_so_em_folha: agrupador recebe soma, não quantidade.
        raise HTTPException(
            status_code=400,
            detail="Quantitativo só pode ser lançado em folha da EAP (item com composição).",
        ) from erro
    con.commit()

    item = con.execute(
        "SELECT e.id, e.codigo, e.descricao, e.unidade, e.composicao_id,"
        "       q.quantidade, q.origem"
        "  FROM eap_item e"
        "  LEFT JOIN quantitativo q ON q.eap_item_id = e.id AND q.projeto_id = ?"
        " WHERE e.id = ?",
        (projeto_id, eap_item_id),
    ).fetchone()
    return request.app.state.templates.TemplateResponse(
        request, "_linha_quantitativo.html",
        {"projeto": {"id": projeto_id}, "item": dict(item)},
    )
```

Para que `HTTPException(400)` chegue ao teste como HTML com a palavra "folha", acrescentar em `app/main.py` um handler que renderiza o `detail`:

```python
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

    @app.exception_handler(HTTPException)
    def erro_html(request, exc: HTTPException):
        if exc.status_code == 404:
            return HTMLResponse(f"<h1>404</h1><p>{exc.detail}</p>", status_code=404)
        return HTMLResponse(
            f'<p class="erro" role="alert">{exc.detail}</p>', status_code=exc.status_code
        )
```

- [ ] **Step 4: Templates**

`app/templates/_linha_quantitativo.html` (fragmento htmx — a linha que volta após o POST):

```html
<tr id="item-{{ item.id }}">
  <td>{{ item.codigo }}</td>
  <td>{{ item.descricao }}</td>
  <td>{{ item.unidade or "—" }}</td>
  <td>
    <form hx-post="/projetos/{{ projeto.id }}/quantitativos"
          hx-target="#item-{{ item.id }}" hx-swap="outerHTML">
      <input type="hidden" name="eap_item_id" value="{{ item.id }}">
      <input name="quantidade" value="{{ item.quantidade or '' }}" inputmode="decimal">
      <button type="submit">Salvar</button>
    </form>
  </td>
  <td>{{ item.origem or "—" }}</td>
</tr>
```

`app/templates/quantitativos.html`:

```html
{% extends "base.html" %}
{% block titulo %}Quantitativos — {{ projeto.codigo }}{% endblock %}
{% block conteudo %}
<h1>Quantitativos — {{ projeto.codigo }}</h1>
<p><a href="/projetos/{{ projeto.id }}">← voltar ao projeto</a></p>
{% for macro in macroetapas %}
<section class="macroetapa">
  <h2>{{ macro.codigo }} — {{ macro.descricao }}</h2>
  {% if not macro.folhas %}
    <p class="alerta">Nenhum item cadastrado nesta macroetapa (gate R7 vai bloquear a publicação).</p>
  {% else %}
  <table>
    <thead><tr><th>EAP</th><th>Descrição</th><th>Un.</th><th>Quantidade</th><th>Origem</th></tr></thead>
    <tbody>
      {% for item in macro.folhas %}
        {% include "_linha_quantitativo.html" %}
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</section>
{% endfor %}
<p><a class="botao" href="/projetos/{{ projeto.id }}/orcamento">Ver orçamento</a></p>
{% endblock %}
```

- [ ] **Step 5: Registrar o router, rodar os testes**

Em `app/main.py`: `from app.rotas import quantitativos as rotas_quantitativos` e `app.include_router(rotas_quantitativos.router)`.

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_quantitativos.py -v
```

Esperado: 7 passed.

- [ ] **Step 6: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add app tests/test_app_quantitativos.py
git commit -m "feat(app): quantitativos MANUAL na árvore da EAP (htmx; trigger de folha vira erro 400)"
```

---

### Task 6: Tela de orçamento

**Files:**
- Create: `app/servicos/__init__.py`, `app/servicos/orcamento.py`
- Create: `app/rotas/orcamento.py`
- Create: `app/templates/orcamento.html`
- Modify: `app/main.py`
- Test: `tests/test_app_orcamento.py`

**Interfaces:**
- Consumes: `lsf.motores.orcamento.custo_direto_projeto(con, projeto_id) -> OrcamentoDireto`, `carregar_parametros_bdi(con) -> ParametrosBDI`, `aplicar_bdi(orcamento, params) -> OrcamentoVenda`; `lsf.relatorios._faixa` **não** deve ser reusado (é privado) — a faixa vem do serviço.
- Produces:
  - `app.servicos.orcamento.montar(con, projeto_id, faixa_pct=0.15) -> VisaoOrcamento`
  - `VisaoOrcamento` (dataclass): `venda: OrcamentoVenda`, `linhas: list[dict]` (cada dict com `preco_min`/`preco_max` quando a confiança pede faixa), `macroetapas_zeradas: list[str]`, `pendencias: list[str]`, `pode_publicar: bool`.
  - Task 7 consome `montar()` e `pode_publicar`.

**Regra de fronteira:** este serviço **não calcula preço**. Ele chama o motor e formata. A única aritmética permitida aqui é a faixa ±% de exibição (D4), e ela é derivada de `confianca`, não inventada.

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_app_orcamento.py`:

```python
"""Tela de orçamento: KPIs, faixas ±% (D4), pendências (D4.1), gate R7 visível."""
import pytest


@pytest.fixture
def projeto_com_quantitativo(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "109.1506", "nome": "Edifício", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto").fetchone()["id"]
    folha = con_app.execute(
        "SELECT id FROM eap_item WHERE codigo = '03.01'"
    ).fetchone()["id"]
    logado.post(
        f"/projetos/{pid}/quantitativos",
        data={"eap_item_id": folha, "quantidade": "1500"},
    )
    return pid


def test_orcamento_mostra_total_com_bdi(logado, projeto_com_quantitativo):
    resposta = logado.get(f"/projetos/{projeto_com_quantitativo}/orcamento")
    assert resposta.status_code == 200
    assert "BDI" in resposta.text
    assert "27,79" in resposta.text or "27.79" in resposta.text


def test_orcamento_mostra_macroetapas_zeradas(logado, projeto_com_quantitativo):
    """Só a 03 tem quantitativo; as outras 7 estão vazias — o gate tem que aparecer."""
    resposta = logado.get(f"/projetos/{projeto_com_quantitativo}/orcamento")
    texto = resposta.text.lower()
    assert "zerada" in texto or "sem quantitativo" in texto
    assert "01" in resposta.text and "02" in resposta.text


def test_servico_marca_pode_publicar_falso_com_macroetapa_zerada(con_app, projeto_com_quantitativo):
    from app.servicos.orcamento import montar

    visao = montar(con_app, projeto_com_quantitativo)
    assert visao.pode_publicar is False
    assert len(visao.macroetapas_zeradas) == 7


def test_linha_estimada_ganha_faixa_e_real_nao(con_app, projeto_com_quantitativo):
    from app.servicos.orcamento import montar

    visao = montar(con_app, projeto_com_quantitativo, faixa_pct=0.10)
    linha = visao.linhas[0]
    if linha["confianca"] in ("estimado", "parametrico"):
        assert linha["preco_min"] == pytest.approx(linha["preco_venda"] * 0.90)
        assert linha["preco_max"] == pytest.approx(linha["preco_venda"] * 1.10)
    else:
        assert linha["preco_min"] is None


def test_projeto_sem_quantitativo_nao_fecha_o_total(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "VAZIO", "nome": "Vazio", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto WHERE codigo='VAZIO'").fetchone()["id"]

    from app.servicos.orcamento import montar

    visao = montar(con_app, pid)
    assert visao.venda.preco_total is None      # D4.1: não fecha com pendência
    assert visao.pode_publicar is False
    assert "sem nenhum quantitativo" in " ".join(visao.pendencias)
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_orcamento.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'app.servicos'`.

- [ ] **Step 3: Implementar `app/servicos/orcamento.py`**

```python
"""View-model da tela de orçamento.

FRONTEIRA (spec §5): este módulo NÃO calcula preço. Ele chama os motores puros e
formata o resultado. A única aritmética aqui é a faixa ±% de exibição (D4), derivada
da confiança que o motor propagou — nunca inventada.
"""
from __future__ import annotations

from dataclasses import dataclass

from lsf.motores.orcamento import (
    OrcamentoVenda,
    aplicar_bdi,
    carregar_parametros_bdi,
    custo_direto_projeto,
)

FAIXA_PCT_DEFAULT = 0.15
CONFIANCAS_COM_FAIXA = ("estimado", "parametrico")


@dataclass(frozen=True)
class VisaoOrcamento:
    venda: OrcamentoVenda
    linhas: list[dict]
    macroetapas_zeradas: list[str]
    pendencias: list[str]
    pode_publicar: bool


def montar(con, projeto_id: int, faixa_pct: float = FAIXA_PCT_DEFAULT) -> VisaoOrcamento:
    direto = custo_direto_projeto(con, projeto_id)
    venda = aplicar_bdi(direto, carregar_parametros_bdi(con))

    linhas = []
    for l in venda.linhas:
        com_faixa = l.preco_venda is not None and l.confianca in CONFIANCAS_COM_FAIXA
        linhas.append({
            "eap_codigo": l.eap_codigo,
            "descricao": l.descricao,
            "unidade": l.unidade,
            "quantidade": l.quantidade,
            "origem": l.origem,
            "custo_unitario": l.custo_unitario,
            "custo_direto": l.custo_direto,
            "preco_venda": l.preco_venda,
            "confianca": l.confianca,
            "pendencia": l.pendencia,
            "preco_min": l.preco_venda * (1 - faixa_pct) if com_faixa else None,
            "preco_max": l.preco_venda * (1 + faixa_pct) if com_faixa else None,
        })

    # Gate (spec §8): total pendente OU macroetapa zerada impede a publicação.
    pode_publicar = (
        venda.preco_total is not None
        and not direto.pendencias
        and not direto.macroetapas_zeradas
    )

    return VisaoOrcamento(
        venda=venda,
        linhas=linhas,
        macroetapas_zeradas=list(direto.macroetapas_zeradas),
        pendencias=list(direto.pendencias),
        pode_publicar=pode_publicar,
    )
```

- [ ] **Step 4: Implementar `app/rotas/orcamento.py`**

```python
"""Tela de orçamento analítico."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth import usuario_logado
from app.db import conexao
from app.servicos.orcamento import montar

router = APIRouter()


@router.get("/projetos/{projeto_id}/orcamento", response_class=HTMLResponse)
def tela(
    projeto_id: int,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projeto = con.execute(
        "SELECT id, codigo, nome FROM projeto WHERE id = ?", (projeto_id,)
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")

    visao = montar(con, projeto_id)
    subtotais = visao.venda.orcamento.subtotais
    completas = sum(1 for s in subtotais if not s.zerada)
    return request.app.state.templates.TemplateResponse(
        request, "orcamento.html",
        {
            "projeto": projeto, "visao": visao, "usuario": usuario,
            "subtotais": subtotais,
            "completude": f"{completas}/{len(subtotais)}",
            "bdi_pct": visao.venda.bdi * 100,
        },
    )
```

- [ ] **Step 5: Template `app/templates/orcamento.html`**

Herdar a estrutura do preview `docs/previews/orcamento_analitico.html` (KPIs no topo, medidor de completude, tabela com faixa). Conteúdo mínimo que os testes exigem:

```html
{% extends "base.html" %}
{% block titulo %}Orçamento — {{ projeto.codigo }}{% endblock %}
{% block conteudo %}
<h1>Orçamento — {{ projeto.codigo }}</h1>

<section class="kpis">
  <div class="kpi">
    <span class="rotulo">Custo direto</span>
    <strong>{% if visao.venda.orcamento.total is not none %}
      R$ {{ "%.2f"|format(visao.venda.orcamento.total) }}{% else %}—{% endif %}</strong>
  </div>
  <div class="kpi">
    <span class="rotulo">BDI</span>
    <strong>{{ "%.2f"|format(bdi_pct)|replace(".", ",") }}%</strong>
  </div>
  <div class="kpi">
    <span class="rotulo">Preço de venda</span>
    <strong>{% if visao.venda.preco_total is not none %}
      R$ {{ "%.2f"|format(visao.venda.preco_total) }}{% else %}não fecha{% endif %}</strong>
  </div>
  <div class="kpi">
    <span class="rotulo">Completude turn-key</span>
    <strong>{{ completude }} macroetapas</strong>
  </div>
</section>

{% if visao.pendencias %}
<section class="alerta" role="alert">
  <h2>Pendências — o orçamento não fecha (D4.1)</h2>
  <ul>{% for p in visao.pendencias %}<li>{{ p }}</li>{% endfor %}</ul>
</section>
{% endif %}

{% if visao.macroetapas_zeradas %}
<section class="alerta" role="alert">
  <h2>Macroetapas zeradas — escopo vazado (R7)</h2>
  <ul>
    {% for s in subtotais if s.zerada %}
      <li>{{ s.eap_codigo }} — {{ s.descricao }}: sem quantitativo</li>
    {% endfor %}
  </ul>
  <p>A publicação da proposta está <strong>bloqueada</strong> até o escopo fechar.</p>
</section>
{% endif %}

<table>
  <thead>
    <tr><th>EAP</th><th>Descrição</th><th>Un.</th><th>Qtd.</th><th>Custo unit.</th>
        <th>Preço (BDI)</th><th>Faixa</th><th>Confiança</th></tr>
  </thead>
  <tbody>
    {% for l in visao.linhas %}
    <tr class="{{ 'pendente' if l.pendencia else '' }}">
      <td>{{ l.eap_codigo }}</td><td>{{ l.descricao }}</td><td>{{ l.unidade }}</td>
      <td>{{ "%.2f"|format(l.quantidade)|replace(".", ",") }}</td>
      <td>{% if l.custo_unitario is not none %}R$ {{ "%.4f"|format(l.custo_unitario) }}{% else %}—{% endif %}</td>
      <td>{% if l.preco_venda is not none %}R$ {{ "%.2f"|format(l.preco_venda) }}{% else %}
          <span class="erro">{{ l.pendencia }}</span>{% endif %}</td>
      <td>{% if l.preco_min is not none %}
          R$ {{ "%.2f"|format(l.preco_min) }} – {{ "%.2f"|format(l.preco_max) }}{% else %}—{% endif %}</td>
      <td><span class="etiqueta {{ l.confianca }}">{{ l.confianca or "—" }}</span></td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<nav class="acoes">
  {% if visao.pode_publicar %}
    <form method="post" action="/projetos/{{ projeto.id }}/publicar">
      <button type="submit">Publicar proposta</button>
    </form>
  {% else %}
    <button disabled title="Gates abertos: resolva pendências e macroetapas zeradas">
      Publicar proposta (bloqueado)
    </button>
  {% endif %}
</nav>
{% endblock %}
```

- [ ] **Step 6: Registrar router, rodar testes**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_orcamento.py -v
```

Esperado: 5 passed.

- [ ] **Step 7: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add app tests/test_app_orcamento.py
git commit -m "feat(app): tela de orçamento — KPIs, faixas D4, pendências D4.1, gate R7 visível"
```

---

### Task 7: Publicação com gates + snapshot congelado

**Files:**
- Create: `app/servicos/publicacao.py`
- Create: `app/rotas/proposta.py`
- Create: `app/templates/publicacao_bloqueada.html`
- Modify: `app/main.py`
- Test: `tests/test_app_proposta.py`

**Interfaces:**
- Consumes: `app.servicos.orcamento.montar()` (Task 6); tabela `proposta` (Task 2); `lsf.relatorios.relatorio_html(venda, faixa_pct)`.
- Produces:
  - `app.servicos.publicacao.PublicacaoBloqueada(Exception)` com atributo `motivos: list[str]`
  - `app.servicos.publicacao.motivos_de_bloqueio(con, projeto_id) -> list[str]`
  - `app.servicos.publicacao.publicar(con, projeto_id, usuario_id, renderizar_pagina=None) -> dict` com `{"id", "versao", "token"}`; levanta `PublicacaoBloqueada` se houver gate aberto. **Esta assinatura é final** — a Task 8 apenas passa o `renderizar_pagina`, sem alterá-la.
  - `renderizar_pagina(snapshot: dict, tabela_html: str) -> str` é injetado pela rota. É assim que o serviço congela a página **sem importar FastAPI** (fronteira da spec §5).
  - Rotas `POST /projetos/{id}/publicar`, `POST /propostas/{id}/revogar`.
  - Task 8 lê a `proposta` gravada aqui e fornece o `renderizar_pagina`.

**Regra:** publicar **revoga** a versão ativa anterior do mesmo projeto (o link antigo passa a dizer "versão superada" em vez de exibir preço obsoleto como se fosse vigente).

- [ ] **Step 1: Escrever o teste que falha**

Primeiro, acrescentar a fixture do caminho feliz a `tests/conftest.py` — ela é usada tanto por esta tarefa quanto pela Task 8, e por isso mora no `conftest`, não num arquivo de teste (importar um teste de dentro de outro não funciona: `tests/` não é pacote):

```python
# --- acrescentar ao final de tests/conftest.py ---
@pytest.fixture
def projeto_completo(logado, con_app):
    """Projeto com quantitativo em TODAS as 8 macroetapas — único jeito de passar no R7.

    A EAP de fábrica tem 5 folhas em 3 macroetapas. Para exercitar o caminho feliz,
    criamos folhas nas macroetapas restantes apontando para uma composição existente.
    Isto é ARRANJO DE TESTE, não uso do app: a base de conhecimento continua vindo
    de seed/migração (spec §10). Devolve o id do projeto.
    """
    logado.post(
        "/projetos",
        data={
            "codigo": "109.1506", "nome": "Edifício", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "0",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto").fetchone()["id"]
    composicao = con_app.execute(
        "SELECT composicao_id FROM eap_item WHERE codigo = '03.01'"
    ).fetchone()["composicao_id"]

    macros = con_app.execute(
        "SELECT id, codigo, grupo_eap FROM eap_item WHERE pai_id IS NULL ORDER BY codigo"
    ).fetchall()
    for macro in macros:
        folha = con_app.execute(
            "SELECT id FROM eap_item WHERE pai_id = ? AND composicao_id IS NOT NULL LIMIT 1",
            (macro["id"],),
        ).fetchone()
        if folha is None:
            cur = con_app.execute(
                "INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap,"
                " composicao_id) VALUES (?,?,?,?,?,?)",
                (f"{macro['codigo']}.99", macro["id"], "Item de teste", "kg",
                 macro["grupo_eap"], composicao),
            )
            folha_id = cur.lastrowid
        else:
            folha_id = folha["id"]
        con_app.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem, confianca)"
            " VALUES (?,?,100,'MANUAL','real')",
            (pid, folha_id),
        )
    con_app.commit()
    return pid
```

Criar `tests/test_app_proposta.py`:

```python
"""Publicação: os gates recusam, e o que foi publicado NÃO muda mais."""
import pytest


def test_publicar_com_macroetapa_zerada_e_recusado(logado, con_app):
    """Gate R7: escopo vazado em preço fechado é prejuízo. Bloqueia, não avisa."""
    logado.post(
        "/projetos",
        data={
            "codigo": "PARCIAL", "nome": "Parcial", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto WHERE codigo='PARCIAL'").fetchone()["id"]
    folha = con_app.execute("SELECT id FROM eap_item WHERE codigo='03.01'").fetchone()["id"]
    logado.post(f"/projetos/{pid}/quantitativos",
                data={"eap_item_id": folha, "quantidade": "100"})

    resposta = logado.post(f"/projetos/{pid}/publicar")
    assert resposta.status_code == 409
    assert "macroetapa" in resposta.text.lower()
    assert con_app.execute("SELECT COUNT(*) FROM proposta").fetchone()[0] == 0


def test_publicar_sem_quantitativo_nenhum_e_recusado(logado, con_app):
    logado.post(
        "/projetos",
        data={
            "codigo": "VAZIO", "nome": "Vazio", "referencia": "2026-06",
            "uf": "SP", "desonerado": "0", "sondagem_pendente": "1",
        },
    )
    pid = con_app.execute("SELECT id FROM projeto WHERE codigo='VAZIO'").fetchone()["id"]
    resposta = logado.post(f"/projetos/{pid}/publicar")
    assert resposta.status_code == 409
    assert con_app.execute("SELECT COUNT(*) FROM proposta").fetchone()[0] == 0


def test_publicar_projeto_completo_cria_v1(logado, con_app, projeto_completo):
    pid = projeto_completo
    resposta = logado.post(f"/projetos/{pid}/publicar")
    assert resposta.status_code == 303

    proposta = con_app.execute(
        "SELECT versao, token, status, total_venda, html FROM proposta WHERE projeto_id = ?",
        (pid,),
    ).fetchone()
    assert proposta["versao"] == 1
    assert proposta["status"] == "ativa"
    assert proposta["total_venda"] > 0
    assert len(proposta["token"]) >= 32
    assert "<" in proposta["html"]          # HTML congelado, não vazio


def test_snapshot_gravado_nao_muda_quando_o_preco_muda(logado, con_app, projeto_completo):
    """D5 levado ao limite, verificado no BANCO (a rota /p/{token} chega na Task 8).

    O que importa aqui é que a publicação CONGELOU: mexer no preço depois não pode
    alterar nem o html nem o total já gravados.
    """
    pid = projeto_completo
    logado.post(f"/projetos/{pid}/publicar")
    antes = con_app.execute("SELECT html, total_venda FROM proposta").fetchone()

    con_app.execute("UPDATE insumo_preco SET preco = preco * 2")   # o mundo muda
    con_app.commit()

    depois = con_app.execute("SELECT html, total_venda FROM proposta").fetchone()
    assert depois["html"] == antes["html"]
    assert depois["total_venda"] == pytest.approx(antes["total_venda"])


def test_nova_versao_revoga_a_anterior(logado, con_app, projeto_completo):
    pid = projeto_completo
    logado.post(f"/projetos/{pid}/publicar")
    logado.post(f"/projetos/{pid}/publicar")

    linhas = con_app.execute(
        "SELECT versao, status FROM proposta WHERE projeto_id = ? ORDER BY versao", (pid,)
    ).fetchall()
    assert [(l["versao"], l["status"]) for l in linhas] == [(1, "revogada"), (2, "ativa")]


def test_publicar_sem_sessao_e_recusado(cliente):
    assert cliente.post("/projetos/1/publicar").status_code == 303
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_proposta.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'app.servicos.publicacao'` / 404 em `/publicar`.

- [ ] **Step 3: Implementar `app/servicos/publicacao.py`**

```python
"""Publicação da proposta: pré-flight dos gates + congelamento do snapshot.

Gates (spec §8) BLOQUEIAM, não avisam:
  - pendência de custo (total None) → recusa. Nunca publica custo parcial (D4.1).
  - macroetapa zerada → recusa. Escopo vazado em preço fechado é prejuízo (R7).
  - sondagem pendente → NÃO bloqueia; carimba a proposta e aparece como gate aberto.

Congelamento (D5): a proposta guarda o JSON do OrcamentoVenda e o HTML renderizado.
A rota pública serve o HTML gravado — nunca recalcula.
"""
from __future__ import annotations

import dataclasses
import json
import secrets

from lsf.relatorios import relatorio_html

from app.servicos.orcamento import montar

TAMANHO_TOKEN = 32


class PublicacaoBloqueada(Exception):
    def __init__(self, motivos: list[str]):
        self.motivos = motivos
        super().__init__("; ".join(motivos))


def motivos_de_bloqueio(con, projeto_id: int) -> list[str]:
    visao = montar(con, projeto_id)
    motivos: list[str] = []
    for pendencia in visao.pendencias:
        motivos.append(f"Pendência de custo: {pendencia}")
    for codigo in visao.macroetapas_zeradas:
        subtotal = next(
            s for s in visao.venda.orcamento.subtotais if s.eap_codigo == codigo
        )
        motivos.append(f"Macroetapa {codigo} ({subtotal.descricao}) sem quantitativo (R7)")
    if visao.venda.preco_total is None and not motivos:
        motivos.append("O orçamento não fecha um preço total")
    return motivos


def publicar(con, projeto_id: int, usuario_id: int, renderizar_pagina=None) -> dict:
    """`renderizar_pagina(snapshot, tabela_html) -> str` é injetado pela rota (Task 8).
    Sem ele, congela só a tabela analítica. O serviço nunca importa FastAPI."""
    motivos = motivos_de_bloqueio(con, projeto_id)
    if motivos:
        raise PublicacaoBloqueada(motivos)

    visao = montar(con, projeto_id)
    projeto = con.execute(
        "SELECT codigo, nome, cliente, sondagem_pendente FROM projeto WHERE id = ?",
        (projeto_id,),
    ).fetchone()

    snapshot_dict = {
        "venda": dataclasses.asdict(visao.venda),
        "projeto": {
            "codigo": projeto["codigo"],
            "nome": projeto["nome"],
            "cliente": projeto["cliente"],
            "sondagem_pendente": bool(projeto["sondagem_pendente"]),
        },
        # Sondagem pendente NÃO bloqueia — carimba e aparece como gate aberto (spec §8).
        "gates_abertos": (
            ["Sondagem pendente — a fundação sai com confiança rebaixada"]
            if projeto["sondagem_pendente"] else []
        ),
    }
    snapshot = json.dumps(snapshot_dict, ensure_ascii=False, default=str)

    tabela_html = relatorio_html(visao.venda)
    html = (
        renderizar_pagina(snapshot_dict, tabela_html)
        if renderizar_pagina else tabela_html
    )

    versao = (
        con.execute(
            "SELECT COALESCE(MAX(versao), 0) + 1 FROM proposta WHERE projeto_id = ?",
            (projeto_id,),
        ).fetchone()[0]
    )
    token = secrets.token_urlsafe(TAMANHO_TOKEN)

    # A versão anterior não some — passa a "superada" (spec §6).
    con.execute(
        "UPDATE proposta SET status = 'revogada' WHERE projeto_id = ? AND status = 'ativa'",
        (projeto_id,),
    )
    cur = con.execute(
        "INSERT INTO proposta (projeto_id, versao, token, publicada_por, snapshot_json,"
        " html, total_venda, bdi_pct) VALUES (?,?,?,?,?,?,?,?)",
        (projeto_id, versao, token, usuario_id, snapshot, html,
         visao.venda.preco_total, visao.venda.bdi),
    )
    con.commit()
    return {"id": cur.lastrowid, "versao": versao, "token": token}
```

- [ ] **Step 4: Implementar `app/rotas/proposta.py`**

```python
"""Publicação e revogação. O gate mora aqui, do lado do servidor: um botão
desabilitado no HTML é cosmético — a recusa é o 409."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth import usuario_logado
from app.db import conexao
from app.servicos.publicacao import PublicacaoBloqueada, publicar

router = APIRouter()


@router.post("/projetos/{projeto_id}/publicar")
def publicar_proposta(
    projeto_id: int,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    projeto = con.execute(
        "SELECT id, codigo FROM projeto WHERE id = ?", (projeto_id,)
    ).fetchone()
    if projeto is None:
        raise HTTPException(status_code=404, detail="projeto não existe")

    try:
        proposta = publicar(con, projeto_id, usuario["id"])
    except PublicacaoBloqueada as bloqueio:
        return request.app.state.templates.TemplateResponse(
            request, "publicacao_bloqueada.html",
            {"projeto": projeto, "motivos": bloqueio.motivos, "usuario": usuario},
            status_code=409,
        )
    return RedirectResponse(f"/projetos/{projeto_id}", status_code=303)


@router.post("/propostas/{proposta_id}/revogar")
def revogar(
    proposta_id: int,
    con: sqlite3.Connection = Depends(conexao),
    usuario: dict = Depends(usuario_logado),
):
    linha = con.execute(
        "SELECT projeto_id FROM proposta WHERE id = ?", (proposta_id,)
    ).fetchone()
    if linha is None:
        raise HTTPException(status_code=404, detail="proposta não existe")
    con.execute("UPDATE proposta SET status = 'revogada' WHERE id = ?", (proposta_id,))
    con.commit()
    return RedirectResponse(f"/projetos/{linha['projeto_id']}", status_code=303)
```

- [ ] **Step 5: Template `app/templates/publicacao_bloqueada.html`**

```html
{% extends "base.html" %}
{% block titulo %}Publicação bloqueada{% endblock %}
{% block conteudo %}
<h1>Publicação bloqueada — {{ projeto.codigo }}</h1>
<p class="alerta" role="alert">
  A proposta <strong>não foi publicada</strong>. Um orçamento turn-key com escopo
  incompleto ou custo parcial vira prejuízo em preço fechado.
</p>
<h2>Gates abertos</h2>
<ul>{% for m in motivos %}<li>{{ m }}</li>{% endfor %}</ul>
<a class="botao" href="/projetos/{{ projeto.id }}/quantitativos">Completar quantitativos</a>
{% endblock %}
```

- [ ] **Step 6: Registrar o router e rodar**

Em `app/main.py`: `from app.rotas import proposta as rotas_proposta` e `app.include_router(rotas_proposta.router)`.

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_proposta.py -v
```

Esperado: 6 passed. Nenhum teste desta tarefa toca `/p/{token}` — essa rota é da Task 8, e o congelamento é verificado aqui pelo banco.

- [ ] **Step 7: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add app tests/test_app_proposta.py tests/conftest.py
git commit -m "feat(app): publicação com gates (409) + snapshot congelado da proposta"
```

---

### Task 8: Página pública da proposta

**Files:**
- Create: `app/rotas/publico.py`
- Create: `app/templates/proposta_publica.html`, `app/templates/proposta_revogada.html`
- Modify: `app/main.py`
- Test: `tests/test_app_publico.py`

**Interfaces:**
- Consumes: tabela `proposta` (html congelado, status, token).
- Produces: `GET /p/{token}` — sem sessão, sem login. Serve o HTML congelado embrulhado no invólucro Veks, com disclaimers e gates. Nada aqui recalcula.

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_app_publico.py`:

Antes, acrescentar a `tests/conftest.py` um cliente **realmente anônimo** — a fixture `logado` devolve o mesmo objeto que `cliente` (ela faz login nele), então pedir `cliente` e `logado` no mesmo teste daria um cliente já autenticado, e o teste "abre sem login" passaria por engano:

```python
# --- acrescentar ao final de tests/conftest.py ---
@pytest.fixture
def anonimo(app_db):
    """TestClient separado, garantidamente SEM sessão — é o cliente final."""
    from starlette.testclient import TestClient

    from app.main import criar_app

    return TestClient(criar_app(app_db, secret="teste"), follow_redirects=False)
```

Criar `tests/test_app_publico.py`:

```python
"""A página do cliente: read-only, congelada, com os gates à vista."""


def test_token_invalido_da_404(anonimo):
    assert anonimo.get("/p/nao-existe-esse-token").status_code == 404


def test_pagina_publica_abre_sem_login(anonimo, logado, con_app, projeto_completo):
    """O cliente final não tem login. Se este teste exigir sessão, o produto não existe."""
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    resposta = anonimo.get(f"/p/{token}")
    assert resposta.status_code == 200
    assert "109.1506" in resposta.text


def test_pagina_publica_traz_o_disclaimer_de_pre_dimensionamento(
    anonimo, logado, con_app, projeto_completo
):
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    texto = anonimo.get(f"/p/{token}").text.lower()
    assert "pré-dimensionamento" in texto or "pre-dimensionamento" in texto
    assert "não substitui projeto" in texto or "nao substitui projeto" in texto


def test_pagina_publica_nao_e_indexavel(anonimo, logado, con_app, projeto_completo):
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    resposta = anonimo.get(f"/p/{token}")
    assert "noindex" in resposta.headers.get("x-robots-tag", "").lower()


def test_proposta_revogada_diz_que_foi_superada(anonimo, logado, con_app, projeto_completo):
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token_v1 = con_app.execute(
        "SELECT token FROM proposta WHERE versao = 1"
    ).fetchone()["token"]
    logado.post(f"/projetos/{projeto_completo}/publicar")   # v2 revoga a v1

    resposta = anonimo.get(f"/p/{token_v1}")
    assert resposta.status_code == 410
    assert "superada" in resposta.text.lower()
    # E não pode exibir o preço obsoleto como se fosse vigente:
    assert "R$" not in resposta.text


def test_sondagem_pendente_aparece_como_gate_aberto(
    anonimo, logado, con_app, projeto_completo
):
    con_app.execute(
        "UPDATE projeto SET sondagem_pendente = 1 WHERE id = ?", (projeto_completo,)
    )
    con_app.commit()
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    texto = anonimo.get(f"/p/{token}").text.lower()
    assert "sondagem" in texto


def test_o_que_o_cliente_ve_nao_muda_quando_o_preco_muda(
    anonimo, logado, con_app, projeto_completo
):
    """O teste que dá sentido a tudo (spec §12.7): a página que o cliente tem em mãos
    é a mesma depois que o mundo mudou. Se esta rota algum dia recalcular, ele quebra."""
    logado.post(f"/projetos/{projeto_completo}/publicar")
    token = con_app.execute("SELECT token FROM proposta").fetchone()["token"]

    antes = anonimo.get(f"/p/{token}").text

    con_app.execute("UPDATE insumo_preco SET preco = preco * 2")
    con_app.commit()

    assert anonimo.get(f"/p/{token}").text == antes
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_publico.py -v
```

Esperado: FAIL — 404 em `/p/{token}` (rota inexistente).

- [ ] **Step 3: Ligar o renderizador da página pública na rota de publicação**

O serviço da Task 7 já monta o `snapshot_dict` (com projeto, cliente e `gates_abertos`) e aceita `renderizar_pagina`. **Não altere `app/servicos/publicacao.py`.** O que muda é só a rota: a partir daqui, o HTML congelado passa a ser a página pública inteira, renderizada **no instante da publicação** — é isso que a torna imutável.

Em `app/rotas/proposta.py`, dentro de `publicar_proposta`, trocar a chamada:

```python
    from app.rotas.publico import render_proposta

    def renderizar(snapshot, tabela_html):
        return render_proposta(request.app.state.templates, snapshot, tabela_html)

    try:
        proposta = publicar(con, projeto_id, usuario["id"], renderizar)
    except PublicacaoBloqueada as bloqueio:
        ...  # inalterado
```

- [ ] **Step 4: Implementar `app/rotas/publico.py`**

```python
"""Página pública da proposta. Sem sessão. Serve o HTML CONGELADO — nunca recalcula.

Se esta rota algum dia chamar um motor, o congelamento morreu e o cliente passa a ver
um preço que muda sozinho. Ela lê `proposta.html` e nada mais.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.db import conexao

router = APIRouter()

CABECALHO_SEM_INDEXACAO = {"X-Robots-Tag": "noindex, nofollow"}


def render_proposta(templates, snapshot: dict, tabela_html: str) -> str:
    """Renderiza a página que será CONGELADA. Chamada uma única vez, na publicação."""
    return templates.get_template("proposta_publica.html").render(
        projeto=snapshot["projeto"],
        venda=snapshot["venda"],
        gates_abertos=snapshot["gates_abertos"],
        tabela_html=tabela_html,
    )


@router.get("/p/{token}", response_class=HTMLResponse)
def proposta_publica(
    token: str,
    request: Request,
    con: sqlite3.Connection = Depends(conexao),
):
    linha = con.execute(
        "SELECT p.html, p.status, p.versao, j.codigo FROM proposta p"
        " JOIN projeto j ON j.id = p.projeto_id WHERE p.token = ?",
        (token,),
    ).fetchone()
    if linha is None:
        return HTMLResponse(
            "<h1>404</h1><p>Proposta não encontrada.</p>",
            status_code=404, headers=CABECALHO_SEM_INDEXACAO,
        )
    if linha["status"] == "revogada":
        pagina = request.app.state.templates.get_template(
            "proposta_revogada.html"
        ).render(versao=linha["versao"], codigo=linha["codigo"])
        return HTMLResponse(pagina, status_code=410, headers=CABECALHO_SEM_INDEXACAO)

    return HTMLResponse(linha["html"], headers=CABECALHO_SEM_INDEXACAO)
```

- [ ] **Step 5: Templates públicos**

`app/templates/proposta_publica.html` — **não** estende `base.html` (a página do cliente não tem barra de navegação interna nem botão "Sair"), e é autocontida porque será congelada:

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>Proposta {{ projeto.codigo }} — Veks Engenharia</title>
  <link rel="stylesheet" href="/static/veks.css">
</head>
<body class="proposta">
  <header>
    <h1>Proposta — {{ projeto.codigo }}</h1>
    <p>{{ projeto.nome }}{% if projeto.cliente %} · {{ projeto.cliente }}{% endif %}</p>
  </header>

  <section class="valor">
    <span class="rotulo">Valor total (com BDI)</span>
    <strong>R$ {{ "%.2f"|format(venda.preco_total) }}</strong>
  </section>

  <section class="escopo">
    <h2>Escopo turn-key</h2>
    <ul>
      {% for s in venda.orcamento.subtotais %}
      <li>{{ s.eap_codigo }} — {{ s.descricao }}</li>
      {% endfor %}
    </ul>
  </section>

  <section class="gates" role="alert">
    <h2>Condições e gates abertos</h2>
    <ul>
      {% for g in gates_abertos %}<li>{{ g }}</li>{% endfor %}
      <li><strong>Pré-dimensionamento</strong>: este documento é um pré-dimensionamento
          para fins de orçamento e <strong>não substitui projeto</strong> estrutural,
          ART/RRT nem verificação estrutural.</li>
      <li>Itens de baixa confiança são apresentados como faixa (±), não como valor seco.</li>
    </ul>
  </section>

  <section class="analitico">
    <h2>Composição do valor</h2>
    {{ tabela_html|safe }}
  </section>

  <footer><p>Veks Engenharia · proposta congelada na publicação</p></footer>
</body>
</html>
```

`app/templates/proposta_revogada.html` — sem preço nenhum:

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="robots" content="noindex, nofollow">
  <title>Versão superada — Veks Engenharia</title>
  <link rel="stylesheet" href="/static/veks.css">
</head>
<body class="proposta">
  <h1>Esta versão da proposta foi superada</h1>
  <p>A versão {{ versao }} da proposta {{ codigo }} não está mais vigente.
     Solicite o link atualizado à Veks Engenharia.</p>
</body>
</html>
```

- [ ] **Step 6: Rodar os testes públicos e o de congelamento da Task 7**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_publico.py tests/test_app_proposta.py -v
```

Esperado: 7 + 6 passed — inclusive o teste fim-a-fim do congelamento, que só fecha agora.

- [ ] **Step 7: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add app tests/test_app_publico.py
git commit -m "feat(app): página pública /p/{token} — congelada, noindex, gates à vista"
```

---

### Task 9: Deploy no Replit e documentação

**Files:**
- Create: `.replit`, `run_app.py`
- Modify: `README.md`, `CLAUDE.md` (seção "Estrutura da pasta" e "Fase atual")
- Test: `tests/test_app_smoke.py`

**Interfaces:**
- Consumes: `app.main.criar_app` (Task 3).
- Produces: comando de execução `.venv/bin/python run_app.py`, servindo em `0.0.0.0:$PORT`.

- [ ] **Step 1: Teste de fumaça**

Criar `tests/test_app_smoke.py`:

```python
"""A fábrica se recusa a subir sem segredo de sessão — login com segredo default
é login decorativo."""
import pytest


def test_app_exige_segredo_de_sessao(app_db, monkeypatch):
    monkeypatch.delenv("LSF_SECRET", raising=False)
    from app.main import criar_app

    with pytest.raises(RuntimeError, match="LSF_SECRET"):
        criar_app(app_db)


def test_app_sobe_com_segredo(app_db):
    from app.main import criar_app

    app = criar_app(app_db, secret="qualquer-coisa-longa")
    rotas = {r.path for r in app.routes}
    assert "/login" in rotas
    assert "/projetos" in rotas
    assert "/p/{token}" in rotas
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/test_app_smoke.py -v
```

Esperado: os dois passam se a Task 3 foi feita como especificada. Se `test_app_exige_segredo_de_sessao` falhar, o `criar_app` está aceitando segredo default — corrigir.

- [ ] **Step 3: `run_app.py`**

```python
"""Sobe o app. Uso: .venv/bin/python run_app.py

Exige LSF_SECRET no ambiente (Replit Secrets). Constrói/atualiza o banco no boot,
de forma não-destrutiva: nenhum projeto ou proposta é perdido num redeploy.
"""
import os
import pathlib
import sys

import uvicorn

RAIZ = pathlib.Path(__file__).parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "db"))

from build_db import construir  # noqa: E402

from app.main import criar_app  # noqa: E402

DB = pathlib.Path(os.environ.get("LSF_DB", RAIZ / "db" / "lsf_base.db"))

if __name__ == "__main__":
    resultado = construir(DB)   # NÃO destrutivo (Task 1)
    print(f"banco pronto: {DB} ({len(resultado['migracoes_aplicadas'])} migração(ões) nova(s))")
    uvicorn.run(
        criar_app(DB),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
```

- [ ] **Step 4: `.replit`**

```toml
run = ".venv/bin/python run_app.py"

[env]
LD_LIBRARY_PATH = "/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib"
LSF_HTTPS_ONLY = "1"

[deployment]
run = [".venv/bin/python", "run_app.py"]
deploymentTarget = "cloudrun"
```

`LSF_SECRET` **não** entra aqui — vai em Replit Secrets. Segredo em arquivo versionado é segredo vazado.

- [ ] **Step 5: Subir localmente e conferir de olho**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
export LSF_SECRET=teste-local
.venv/bin/python tools/criar_usuario.py voce@veks.com "Seu Nome"
.venv/bin/python run_app.py
```

Abrir `http://localhost:8000/login`, entrar, cadastrar a 109.1506, lançar um quantitativo em `03.01`, abrir o orçamento, tentar publicar (deve **bloquear** com as 7 macroetapas zeradas). Esse bloqueio é o comportamento correto (spec §11).

- [ ] **Step 6: Atualizar `README.md` e `CLAUDE.md`**

No `README.md`, acrescentar:

```markdown
## Rodar o aplicativo

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
export LSF_SECRET=<segredo longo>          # em produção: Replit Secrets
.venv/bin/python db/build_db.py            # cria/atualiza (NÃO apaga dados)
.venv/bin/python tools/criar_usuario.py voce@veks.com "Seu Nome"
.venv/bin/python run_app.py                # http://localhost:8000
```

`db/build_db.py --recriar` apaga o banco — use só em dev.
```

No `CLAUDE.md`, atualizar a árvore da "Estrutura da pasta" com `app/` e `run_app.py`, e acrescentar ao "Estado atual":

```markdown
- **`app/` — casca web (FastAPI + Jinja + htmx)**: login (scrypt + sessão assinada), projetos, quantitativos MANUAL na árvore da EAP, tela de orçamento (KPIs, faixas D4, pendências D4.1, gate R7) e proposta publicada em `/p/<token>` com **snapshot congelado** (o cliente vê o que foi publicado; preço que mude depois não reescreve a proposta). `app/` NÃO contém regra de engenharia: número na UI que não veio de motor é bug de arquitetura. Publicação recusa (409) com macroetapa zerada ou pendência de custo.
- **`db/build_db.py` é não-destrutivo**: schema e migrações aplicados uma vez via `schema_migrations`; seed reaplicado idempotente (é assim que conhecimento novo chega a banco existente). `--recriar` apaga, e só ele.
```

- [ ] **Step 7: Suíte inteira + commit**

```bash
export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib
.venv/bin/python -m pytest tests/
git add .replit run_app.py README.md CLAUDE.md tests/test_app_smoke.py
git commit -m "feat(app): deploy Replit (run_app.py) + documentação da casca"
```

---

## Critério de aceite do plano

Reproduzir, na aplicação rodando, o roteiro da spec §12:

1. login;
2. cadastrar a 109.1506 (referência 2026-06, SP, não desonerado);
3. lançar quantitativos MANUAL nas folhas da EAP;
4. abrir o orçamento — BDI 27,79%, faixas ±%, medidor de completude;
5. tentar publicar → **bloqueado** pelas macroetapas zeradas;
6. completar o escopo, publicar a v1, abrir `/p/<token>` em janela anônima;
7. mudar um preço no banco → a proposta publicada **continua idêntica**.

Suíte inteira verde. Nenhuma regra de engenharia dentro de `app/`.

**O que este plano NÃO fecha (e não deve):** o gate da Fase 2 continua de pé. Cadeia paramétrica, cronograma/curva S e panelizador não são tocados aqui — são plugues numa casca que passará a existir.
