"""Fixtures comuns. Sem pyproject/instalação: `src/` entra no sys.path aqui."""
import pathlib
import sqlite3
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ))       # para importar `app`
sys.path.insert(0, str(RAIZ / "db"))  # para importar `build_db`


@pytest.fixture
def con():
    """Banco em memória, construído de schema.sql + migrations/ + seed.sql (nunca do artefato .db).

    Ordem igual à de db/build_db.py: estrutura (schema + migrações) primeiro, seed por
    último — o seed é idempotente via ON CONFLICT sobre chaves naturais, algumas das
    quais (ex.: composicao_item) só existem depois de uma migração ser aplicada.
    """
    c = sqlite3.connect(":memory:")
    c.executescript((RAIZ / "db" / "schema.sql").read_text())
    for migracao in sorted((RAIZ / "db" / "migrations").glob("*.sql")):
        c.executescript(migracao.read_text())
    c.executescript((RAIZ / "db" / "seed.sql").read_text())
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


@pytest.fixture
def base():
    """Referência travada pelo projeto (D5), no formato que o motor recebe."""
    return {"referencia": "2026-06", "uf": "SP", "desonerado": 0}


@pytest.fixture
def db_veks(con):
    """id da data-base VEKS/2026-06 — para cadastrar preços nos testes."""
    return con.execute(
        "SELECT db.id FROM data_base db JOIN fonte f ON f.id = db.fonte_id"
        " WHERE f.sigla = 'VEKS' AND db.referencia = '2026-06'"
    ).fetchone()[0]


@pytest.fixture
def id_de(con):
    """id_de('VK-C-001') -> id da composição; id_de.insumo('VK-I-001') -> id do insumo."""

    def composicao(codigo):
        return con.execute(
            "SELECT id FROM composicao WHERE codigo_fonte = ?", (codigo,)
        ).fetchone()[0]

    composicao.insumo = lambda codigo: con.execute(
        "SELECT id FROM insumo WHERE codigo_fonte = ?", (codigo,)
    ).fetchone()[0]
    return composicao


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
        # Sempre uma folha .99 com a composição da 03.01 (a única garantidamente
        # completa no seed): folhas de fábrica como a 06.01 apontam para composição
        # SINAPI sem analítica e derrubariam o caminho feliz por D4.1 — que é
        # exatamente o comportamento certo do motor, mas não o arranjo deste teste.
        cur = con_app.execute(
            "INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap,"
            " composicao_id) VALUES (?,?,?,?,?,?)",
            (f"{macro['codigo']}.99", macro["id"], "Item de teste", "kg",
             macro["grupo_eap"], composicao),
        )
        folha_id = cur.lastrowid
        con_app.execute(
            "INSERT INTO quantitativo (projeto_id, eap_item_id, quantidade, origem, confianca)"
            " VALUES (?,?,100,'MANUAL','real')",
            (pid, folha_id),
        )
    con_app.commit()
    return pid


@pytest.fixture
def anonimo(app_db):
    """TestClient separado, garantidamente SEM sessão — é o cliente final."""
    from starlette.testclient import TestClient

    from app.main import criar_app

    return TestClient(criar_app(app_db, secret="teste"), follow_redirects=False)
