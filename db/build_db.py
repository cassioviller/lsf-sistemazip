"""Constrói/atualiza lsf_base.db a partir de schema.sql + seed.sql + migrations/.

NÃO destrutivo: dado de instância (projeto, quantitativo, proposta, usuario) sobrevive
a todo build. Estrutura (schema + migrações) é aplicada uma vez, registrada em
`schema_migrations`. O seed é conhecimento declarativo e é REAPLICADO a cada build,
de forma idempotente — é assim que composições novas chegam a um banco existente.

Atomicidade (schema/migração + ledger): `executescript` faz um COMMIT implícito de
qualquer transação pendente ANTES de rodar o script, o que destruiria um `BEGIN`
explícito nosso. Por isso cada script estrutural é dividido em statements individuais
(via `sqlite3.complete_statement`, que entende strings/comentários/blocos de trigger
BEGIN..END) e executado um a um dentro de uma única transação que também contém o
INSERT no ledger. Uma falha no meio faz ROLLBACK total: nenhuma tabela parcial,
nenhum ledger inconsistente, e a retentativa (depois de corrigir o SQL) começa limpa.

Banco legado (sem `schema_migrations`, criado por versão anterior deste script): o
ledger vazio faria o build reaplicar schema.sql/migrações incondicionalmente, o que
explode com "table X already exists" — e o operador não tem, além do `--recriar`
destrutivo, nenhuma saída. Em vez disso, quando um script estrutural falha
especificamente porque a estrutura JÁ EXISTE (mensagem "already exists" ou
"duplicate column name"), o build ADOTA: registra o arquivo como aplicado sem
reexecutá-lo, e segue. Qualquer outra falha (erro de sintaxe genuíno) propaga
normalmente, com rollback total (ver acima).

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


class EstruturaJaExiste(Exception):
    """Um script estrutural falhou porque o que ele cria já existe (banco legado)."""


def _ja_aplicadas(con) -> set[str]:
    return {linha[0] for linha in con.execute("SELECT arquivo FROM schema_migrations")}


def _dividir_statements(sql_texto: str) -> list[str]:
    """Divide um script SQL em statements individuais e completos.

    Usa `sqlite3.complete_statement`, apoiado no mesmo tokenizer do SQLite, então
    respeita strings literais, comentários `--` e blocos `CREATE TRIGGER ... BEGIN
    ... END;` (que contêm ';' internos mas são um único statement). Isso é o que
    permite executar statement-a-statement (necessário para atomicidade real — ver
    módulo) sem quebrar scripts com múltiplas instruções.
    """
    statements: list[str] = []
    buffer = ""
    for linha in sql_texto.splitlines(keepends=True):
        buffer += linha
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    resto_sem_comentarios = "\n".join(
        l for l in buffer.splitlines() if not l.strip().startswith("--")
    ).strip()
    if resto_sem_comentarios:
        raise ValueError(f"SQL incompleto (falta ';' final?): {resto_sem_comentarios[:200]!r}")
    return statements


def _mensagem_indica_estrutura_existente(exc: sqlite3.OperationalError) -> bool:
    msg = str(exc).lower()
    return "already exists" in msg or "duplicate column name" in msg


def _aplicar(con, caminho: pathlib.Path) -> None:
    """Aplica um script estrutural (schema.sql ou uma migração) e registra no ledger,
    tudo numa ÚNICA transação: ou os dois efeitos acontecem, ou nenhum. Ver docstring
    do módulo para o porquê de não usar `executescript` aqui.
    """
    statements = _dividir_statements(caminho.read_text())
    con.execute("BEGIN")
    try:
        for statement in statements:
            con.execute(statement)
    except sqlite3.OperationalError as exc:
        con.rollback()
        if _mensagem_indica_estrutura_existente(exc):
            raise EstruturaJaExiste(str(exc)) from exc
        raise
    else:
        con.execute("INSERT INTO schema_migrations (arquivo) VALUES (?)", (caminho.name,))
        con.commit()


def _aplicar_ou_adotar(con, caminho: pathlib.Path) -> str:
    """Aplica normalmente; se a estrutura já existir (banco legado sem ledger),
    adota (registra como aplicada sem reexecutar) em vez de propagar o erro."""
    try:
        _aplicar(con, caminho)
        return "aplicada"
    except EstruturaJaExiste:
        con.execute("BEGIN")
        con.execute("INSERT INTO schema_migrations (arquivo) VALUES (?)", (caminho.name,))
        con.commit()
        return "adotada"


def _aplicar_seed(con, caminho: pathlib.Path) -> None:
    """Reaplica o seed (conhecimento declarativo, idempotente via ON CONFLICT) numa
    única transação — uma falha no meio não deixa preço/composição pela metade."""
    statements = _dividir_statements(caminho.read_text())
    con.execute("BEGIN")
    try:
        for statement in statements:
            con.execute(statement)
    except Exception:
        con.rollback()
        raise
    else:
        con.commit()


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
        resultado = _aplicar_ou_adotar(con, AQUI / "schema.sql")
        if resultado == "aplicada":
            novas.append("schema.sql")

    for migracao in sorted((AQUI / "migrations").glob("*.sql")):
        if migracao.name not in aplicadas:
            resultado = _aplicar_ou_adotar(con, migracao)
            if resultado == "aplicada":
                novas.append(migracao.name)

    # Seed: conhecimento declarativo, reaplicado sempre (idempotente por ON CONFLICT).
    _aplicar_seed(con, AQUI / "seed.sql")

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
