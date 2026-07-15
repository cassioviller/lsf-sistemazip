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


def test_migracao_com_rebuild_de_tabela_referenciada_preserva_fk(tmp_path):
    """Crítico 1 (revisão da migração 006): `PRAGMA foreign_keys = OFF/ON` dentro do
    script de migração é NO-OP porque `_aplicar` já roda o script numa transação
    (`BEGIN` explícito) — e PRAGMA não tem efeito com transação aberta. Uma migração
    que reconstrói (DROP/RENAME) uma tabela referenciada por FK, como `perfil_lsf`
    (referenciada por `parede.perfil_codigo` desde a migração 004), tinha que falhar
    com "FOREIGN KEY constraint failed" assim que existisse dado de instância
    apontando para ela. `_aplicar` agora liga/desliga o PRAGMA FORA da transação."""
    db = tmp_path / "lsf.db"
    construir(db)

    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf, desonerado)"
        " VALUES ('109.1506', 'Edifício', '2026-06', 'SP', 0)"
    )
    projeto_id = con.execute("SELECT id FROM projeto WHERE codigo='109.1506'").fetchone()[0]
    con.execute(
        "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m)"
        " VALUES (?, 0, 'Térreo', 2.80)", (projeto_id,)
    )
    nivel_id = con.execute("SELECT id FROM nivel WHERE projeto_id=?", (projeto_id,)).fetchone()[0]
    con.execute("INSERT INTO no_planta (nivel_id, x, y) VALUES (?, 0, 0)", (nivel_id,))
    con.execute("INSERT INTO no_planta (nivel_id, x, y) VALUES (?, 5, 0)", (nivel_id,))
    no_a, no_b = (r[0] for r in con.execute(
        "SELECT id FROM no_planta WHERE nivel_id=? ORDER BY id", (nivel_id,)
    ))
    con.execute(
        "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, perfil_codigo, origem)"
        " VALUES (?, ?, ?, 0.10, 'Ue90#0.95', 'MANUAL')",
        (nivel_id, no_a, no_b),
    )
    con.commit()
    con.close()

    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    # Mesmo padrão de rebuild da migração 006 (CREATE/INSERT..SELECT/DROP/RENAME),
    # passado pelo mesmo helper que build_db usa para aplicar um script estrutural —
    # sem o PRAGMA foreign_keys = OFF/ON dentro do próprio script (esse é o ponto).
    caminho_script = tmp_path / "999_rebuild_teste.sql"
    caminho_script.write_text(
        "CREATE TABLE perfil_lsf_novo (\n"
        "  codigo TEXT PRIMARY KEY,\n"
        "  familia TEXT NOT NULL,\n"
        "  tipo TEXT NOT NULL CHECK (tipo IN ('montante','guia','laminado')),\n"
        "  drywall INTEGER NOT NULL DEFAULT 0,\n"
        "  alma_mm REAL NOT NULL, aba_mm REAL NOT NULL,\n"
        "  enrijecedor_mm REAL, espessura_mm REAL NOT NULL,\n"
        "  massa_kg_m REAL NOT NULL,\n"
        "  fonte TEXT NOT NULL DEFAULT 'LSF_DB v7 (obra ref. 484125)'\n"
        ");\n"
        "INSERT INTO perfil_lsf_novo SELECT * FROM perfil_lsf;\n"
        "DROP TABLE perfil_lsf;\n"
        "ALTER TABLE perfil_lsf_novo RENAME TO perfil_lsf;\n"
    )
    build_db._aplicar(con, caminho_script)  # não pode levantar FOREIGN KEY constraint failed

    linha = con.execute(
        "SELECT perfil_codigo FROM parede WHERE nivel_id=?", (nivel_id,)
    ).fetchone()
    assert linha is not None, "parede sumiu no rebuild"
    assert linha[0] == "Ue90#0.95", "FK da parede não sobreviveu ao rebuild de perfil_lsf"
    con.close()


def test_migracao_corruptora_faz_rollback_e_nao_registra_no_ledger(tmp_path, monkeypatch):
    """Crítico 1 (revisão pós-fase-1): uma migração que corromperia a integridade
    referencial deve fazer rollback limpo PRÉ-COMMIT, de modo que nem a estrutura
    parcial nem o ledger sejam poluídos. Sem isso, o build seguinte morreria no mesmo
    ponto ('table already exists' ou similar) porque o ledger diz "foi aplicada"."""
    area = _area_temporaria(tmp_path)
    monkeypatch.setattr(build_db, "AQUI", area)

    db = tmp_path / "lsf.db"
    construir(db)

    # Coloca dado de instância apontando para uma tabela referenciada
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(
        "INSERT INTO projeto (codigo, nome, referencia, uf, desonerado)"
        " VALUES ('109.1506', 'Edifício', '2026-06', 'SP', 0)"
    )
    projeto_id = con.execute("SELECT id FROM projeto WHERE codigo='109.1506'").fetchone()[0]
    con.execute(
        "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m)"
        " VALUES (?, 0, 'Térreo', 2.80)", (projeto_id,)
    )
    nivel_id = con.execute("SELECT id FROM nivel WHERE projeto_id=?", (projeto_id,)).fetchone()[0]
    con.execute("INSERT INTO no_planta (nivel_id, x, y) VALUES (?, 0, 0)", (nivel_id,))
    con.execute("INSERT INTO no_planta (nivel_id, x, y) VALUES (?, 5, 0)", (nivel_id,))
    no_a, no_b = (r[0] for r in con.execute(
        "SELECT id FROM no_planta WHERE nivel_id=? ORDER BY id", (nivel_id,)
    ))
    con.execute(
        "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, perfil_codigo, origem)"
        " VALUES (?, ?, ?, 0.10, 'Ue90#0.95', 'MANUAL')",
        (nivel_id, no_a, no_b),
    )
    con.commit()
    con.close()

    # Cria uma migração CORRUPTORA: reconstrói perfil_lsf mas *esquece* de copiar os dados
    # Isso deixaria a FK parede.perfil_codigo->perfil_lsf órfã
    (area / "migrations" / "999_corruptora.sql").write_text(
        "CREATE TABLE perfil_lsf_novo (\n"
        "  codigo TEXT PRIMARY KEY,\n"
        "  familia TEXT NOT NULL,\n"
        "  tipo TEXT NOT NULL CHECK (tipo IN ('montante','guia','laminado')),\n"
        "  drywall INTEGER NOT NULL DEFAULT 0,\n"
        "  alma_mm REAL NOT NULL, aba_mm REAL NOT NULL,\n"
        "  enrijecedor_mm REAL, espessura_mm REAL NOT NULL,\n"
        "  massa_kg_m REAL NOT NULL,\n"
        "  fonte TEXT NOT NULL DEFAULT 'LSF_DB v7 (obra ref. 484125)'\n"
        ");\n"
        "DROP TABLE perfil_lsf;\n"
        "ALTER TABLE perfil_lsf_novo RENAME TO perfil_lsf;\n"
    )

    # Tenta aplicar — deve falhar ANTES de commitar
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError, match="corromperia integridade referencial"):
        build_db._aplicar(con, area / "migrations" / "999_corruptora.sql")

    # Verifica que o banco está intacto (rollback bem-sucedido)
    # Abre nova conexão para verificar estado pós-rollback
    con.close()
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")

    # A tabela perfil_lsf ainda existe (não foi droppada)
    tabelas = {
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='perfil_lsf'"
        )
    }
    assert "perfil_lsf" in tabelas, "rollback incompleto: perfil_lsf foi droppada mesmo assim"

    # O perfil específico Ue90#0.95 ainda está lá
    linha = con.execute("SELECT 1 FROM perfil_lsf WHERE codigo = 'Ue90#0.95'").fetchone()
    assert linha is not None, "rollback incompleto: perfil referenciado foi deletado"

    # A parede ainda referencia o perfil (FK não foi orfanada)
    linha = con.execute(
        "SELECT perfil_codigo FROM parede WHERE nivel_id=?", (nivel_id,)
    ).fetchone()
    assert linha is not None and linha[0] == "Ue90#0.95", "rollback incompleto: parede/FK corrompidas"

    # E o ledger NÃO contém a migração corruptora
    aplicadas = {r[0] for r in con.execute("SELECT arquivo FROM schema_migrations")}
    assert "999_corruptora.sql" not in aplicadas, "migração corruptora foi registrada no ledger!"

    con.close()


# ---------------------------------------------------------------------------
# Adoção POR STATEMENT (correção do review F2, Task 4): um script estrutural
# parcialmente existente não pode ser ledgerado com a metade restante revertida.
# ---------------------------------------------------------------------------


def test_adocao_parcial_executa_statements_restantes_e_ledgera(tmp_path, monkeypatch):
    """Banco legado que já tem UMA tabela de um script multi-objeto: o build precisa
    PULAR o statement 'already exists', EXECUTAR os demais e ledgerar o script. A
    semântica antiga (rollback do script inteiro + ledger mesmo assim) deixava o
    banco permanentemente sem as tabelas restantes — só --recriar salvava."""
    area = _area_temporaria(tmp_path)
    monkeypatch.setattr(build_db, "AQUI", area)

    db = tmp_path / "lsf.db"
    construir(db)

    # simula o legado parcial: a primeira tabela do script novo JÁ existe
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE adocao_a (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    (area / "migrations" / "900_multi_objeto.sql").write_text(
        "CREATE TABLE adocao_a (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE adocao_b (id INTEGER PRIMARY KEY, valor TEXT);\n"
        "CREATE INDEX idx_adocao_b_valor ON adocao_b (valor);\n"
    )

    resultado = construir(db)
    assert "900_multi_objeto.sql" in resultado["migracoes_aplicadas"]

    con = sqlite3.connect(db)
    tabelas = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "adocao_b" in tabelas, "statement restante do script parcial não executou"
    indices = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert "idx_adocao_b_valor" in indices
    aplicadas = {r[0] for r in con.execute("SELECT arquivo FROM schema_migrations")}
    assert "900_multi_objeto.sql" in aplicadas
    con.close()


def test_erro_genuino_apos_statement_pulado_faz_rollback_e_nao_ledgera(tmp_path, monkeypatch):
    """Erro que NÃO é 'already exists' no meio do script (mesmo depois de um statement
    pulado por já existir): rollback COMPLETO, nada no ledger, exceção propaga. A
    semântica antiga ADOTAVA o script no primeiro 'already exists' e nunca via o
    erro genuíno — ledger mentiroso sobre um script quebrado."""
    area = _area_temporaria(tmp_path)
    monkeypatch.setattr(build_db, "AQUI", area)

    db = tmp_path / "lsf.db"
    construir(db)

    con = sqlite3.connect(db)
    con.execute("CREATE TABLE adocao_a (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    (area / "migrations" / "901_meio_quebrado.sql").write_text(
        "CREATE TABLE adocao_a (id INTEGER PRIMARY KEY);\n"   # pulado (já existe)
        "CREATE TABLE adocao_nova (id INTEGER PRIMARY KEY);\n"  # executa...
        "ISTO NAO E SQL VALIDO;\n"                              # ...mas isto reverte tudo
    )

    with pytest.raises(sqlite3.OperationalError):
        construir(db)

    con = sqlite3.connect(db)
    tabelas = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "adocao_nova" not in tabelas, "rollback incompleto: tabela parcial sobrou"
    aplicadas = {r[0] for r in con.execute("SELECT arquivo FROM schema_migrations")}
    assert "901_meio_quebrado.sql" not in aplicadas, "script quebrado foi ledgerado!"
    con.close()


def test_adocao_parcial_rodar_duas_vezes_continua_ok(tmp_path, monkeypatch):
    """Idempotência: depois de uma adoção parcial, um segundo build não tem nada a
    fazer e não explode."""
    area = _area_temporaria(tmp_path)
    monkeypatch.setattr(build_db, "AQUI", area)

    db = tmp_path / "lsf.db"
    construir(db)

    con = sqlite3.connect(db)
    con.execute("CREATE TABLE adocao_a (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    (area / "migrations" / "900_multi_objeto.sql").write_text(
        "CREATE TABLE adocao_a (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE adocao_b (id INTEGER PRIMARY KEY);\n"
    )

    construir(db)
    resultado2 = construir(db)
    assert resultado2["migracoes_aplicadas"] == []

    con = sqlite3.connect(db)
    tabelas = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "adocao_b" in tabelas
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
