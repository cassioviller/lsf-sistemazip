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
