"""O build da base de conhecimento não pode destruir dado de instância."""
import shutil
import sqlite3
import subprocess
import sys
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "db"))

import build_db  # noqa: E402
from build_db import construir  # noqa: E402


def _area_temporaria(tmp_path: pathlib.Path) -> pathlib.Path:
    """Cópia de db/ (schema.sql, seed.sql, migrations/) num diretório descartável, para
    testes que precisam injetar uma migração NOVA sem sujar db/migrations/ real."""
    area = tmp_path / "db_area"
    area.mkdir()
    shutil.copy(RAIZ / "db" / "schema.sql", area / "schema.sql")
    shutil.copy(RAIZ / "db" / "seed.sql", area / "seed.sql")
    shutil.copytree(RAIZ / "db" / "migrations", area / "migrations")
    return area


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


# ---------------------------------------------------------------------------
# Correções da revisão (Crítico 1, Crítico 2, Importante 4)
# ---------------------------------------------------------------------------


def test_migracao_nova_aplicada_a_banco_existente_preserva_dado(tmp_path, monkeypatch):
    """O caso que justifica o ledger: um banco já em uso (com projeto gravado) recebe
    uma migração NOVA num build seguinte — ela precisa ser aplicada, e o dado precisa
    sobreviver. Um `_aplicar` que apagasse o banco antes de migrar passaria nos 6
    testes originais (todos partem de um banco vazio) mas falharia aqui."""
    area = _area_temporaria(tmp_path)
    monkeypatch.setattr(build_db, "AQUI", area)

    db = tmp_path / "lsf.db"
    construir(db)

    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, desonerado)"
        " VALUES ('109.1506', 'Edifício', '2026-06', 0)"
    )
    con.commit()
    con.close()

    (area / "migrations" / "005_teste_temp.sql").write_text(
        "CREATE TABLE tabela_teste_temp (id INTEGER PRIMARY KEY, valor TEXT);\n"
    )

    resultado = construir(db)
    assert "005_teste_temp.sql" in resultado["migracoes_aplicadas"]

    con = sqlite3.connect(db)
    # a migração nova realmente rodou (tabela existe)
    assert con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tabela_teste_temp'"
    ).fetchone()[0] == 1
    # e o dado de instância gravado ANTES da migração nova sobreviveu
    assert con.execute("SELECT COUNT(*) FROM projeto").fetchone()[0] == 1
    assert con.execute("SELECT codigo FROM projeto").fetchone()[0] == "109.1506"
    con.close()


def test_migracao_invalida_nao_deixa_banco_meio_migrado(tmp_path, monkeypatch):
    """Crítico 1: migração + ledger numa transação só. Uma migração com erro no meio
    do script não pode deixar tabela parcial nem ledger inconsistente — senão todo
    build seguinte morre no mesmo ponto ('table already exists')."""
    area = _area_temporaria(tmp_path)
    monkeypatch.setattr(build_db, "AQUI", area)

    db = tmp_path / "lsf.db"
    construir(db)

    (area / "migrations" / "005_quebrada.sql").write_text(
        "CREATE TABLE meia_migracao (id INTEGER PRIMARY KEY);\n"
        "ISTO NAO E SQL VALIDO;\n"
    )

    with pytest.raises(sqlite3.OperationalError):
        construir(db)

    con = sqlite3.connect(db)
    tabelas = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "meia_migracao" not in tabelas, "rollback incompleto: tabela parcial sobrou"
    aplicadas = {r[0] for r in con.execute("SELECT arquivo FROM schema_migrations")}
    assert "005_quebrada.sql" not in aplicadas
    con.close()

    # corrige a migração — o build seguinte precisa funcionar limpo, sem lixo do
    # tentativa anterior atrapalhando (essa é a prova de que a retentativa é limpa)
    (area / "migrations" / "005_quebrada.sql").write_text(
        "CREATE TABLE meia_migracao (id INTEGER PRIMARY KEY);\n"
    )
    resultado = construir(db)
    assert "005_quebrada.sql" in resultado["migracoes_aplicadas"]
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM meia_migracao").fetchone()[0] == 0
    con.close()


def test_banco_legado_sem_ledger_e_adotado_sem_reaplicar(tmp_path):
    """Crítico 2: um banco criado pela versão ANTERIOR do script (schema+migrações
    aplicados, mas sem tabela `schema_migrations`) não pode explodir com "table already
    exists" nem perder dado — `construir()` precisa adotar o banco (registrar o que já
    existe no ledger) e seguir normalmente."""
    db = tmp_path / "legado.db"
    con = sqlite3.connect(db)
    con.executescript((RAIZ / "db" / "schema.sql").read_text())
    for migracao in sorted((RAIZ / "db" / "migrations").glob("*.sql")):
        con.executescript(migracao.read_text())
    con.executescript((RAIZ / "db" / "seed.sql").read_text())
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, desonerado)"
        " VALUES ('LEGADO', 'Obra Legada', '2026-06', 0)"
    )
    con.commit()
    con.close()

    # o ledger não existe neste banco (é exatamente o estado de db/lsf_base.db hoje,
    # gerado pela versão anterior do script) — não pode explodir, não pode sugerir
    # --recriar, não pode apagar o projeto já gravado.
    resultado = construir(db)
    assert resultado["criado"] is False

    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM projeto").fetchone()[0] == 1
    assert con.execute("SELECT codigo FROM projeto").fetchone()[0] == "LEGADO"
    aplicadas = {r[0] for r in con.execute("SELECT arquivo FROM schema_migrations")}
    assert "schema.sql" in aplicadas
    for migracao in sorted((RAIZ / "db" / "migrations").glob("*.sql")):
        assert migracao.name in aplicadas
    con.close()

    # e um segundo build (agora COM ledger) continua idempotente e não duplica nada
    resultado2 = construir(db)
    assert resultado2["migracoes_aplicadas"] == []
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM projeto").fetchone()[0] == 1
    con.close()


def test_seed_reaplicado_nao_fabrica_preco_fantasma(tmp_path):
    """Importante 3: o INSERT..SELECT de insumo_preco juntava com data_base só por
    `referencia`, sem filtrar a fonte (D5.1). Quando outra fonte (ex.: SINAPI via
    tools/bridge_autosinapi.py) ganha uma data_base própria na mesma referência
    '2026-06', o seed reaplicado não pode fabricar preço fantasma de insumo VEKS
    sob a data-base errada — o revisor reproduziu 7 -> 14 linhas com o bug."""
    db = tmp_path / "lsf.db"
    construir(db)
    con = sqlite3.connect(db)
    antes = con.execute("SELECT COUNT(*) FROM insumo_preco").fetchone()[0]
    assert antes == 7

    # simula o que a ponte AutoSINAPI cria: data_base de OUTRA fonte na mesma referência
    con.execute(
        "INSERT INTO data_base (fonte_id, referencia, uf, desonerado, publicado_em)"
        " SELECT id, '2026-06', 'SP', 0, '2026-07-05' FROM fonte WHERE sigla='SINAPI'"
    )
    con.commit()
    con.close()

    construir(db)  # seed reaplicado

    con = sqlite3.connect(db)
    depois = con.execute("SELECT COUNT(*) FROM insumo_preco").fetchone()[0]
    assert depois == antes, f"preço fantasma fabricado: {antes} -> {depois}"
    con.close()


def test_folhas_eap_saem_com_composicao_preenchida(tmp_path):
    """Regressão silenciosa caçada à mão na Task 1: as 5 folhas da EAP com composição
    (03.01, 04.01, 04.02, 04.03, 06.01) precisam sair de um `construir()` do zero já
    com `composicao_id` preenchido — não em um segundo build."""
    db = tmp_path / "lsf.db"
    construir(db)
    con = sqlite3.connect(db)
    for codigo in ("03.01", "04.01", "04.02", "04.03", "06.01"):
        linha = con.execute(
            "SELECT composicao_id FROM eap_item WHERE codigo = ?", (codigo,)
        ).fetchone()
        assert linha is not None, f"eap_item {codigo} não existe"
        assert linha[0] is not None, f"eap_item {codigo} sem composicao_id"
    con.close()
