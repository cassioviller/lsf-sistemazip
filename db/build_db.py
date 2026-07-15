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
destrutivo, nenhuma saída. Em vez disso, a tolerância é POR STATEMENT: um statement
que falha especificamente porque o que ele criaria JÁ EXISTE — estrutura ("already
exists", "duplicate column name") ou linha declarativa embutida em migração ("UNIQUE
constraint failed") — é PULADO e os demais EXECUTAM — assim um banco legado
PARCIAL (só uma tabela de um script multi-objeto) ganha os objetos restantes em vez
de ficar permanentemente quebrado. "Adotar" significa: todo statement do script ou
aplicou ou já existia; só então o arquivo entra no ledger. Qualquer outra falha
(erro de sintaxe genuíno) propaga normalmente, com rollback total e NADA no ledger
(ver acima) — um script revertido pela metade nunca é ledgerado.

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


def _falha_indica_ja_existente(exc: sqlite3.DatabaseError) -> bool:
    """O statement falhou porque o que ele criaria JÁ EXISTE no banco (legado)?

    Estrutura: "already exists" (tabela/índice/trigger/view) e "duplicate column
    name" (ALTER TABLE ADD COLUMN repetido). Dado declarativo embutido em migração
    (ex.: raízes da EAP na 001, parâmetros de BDI na 002): reinserir a mesma linha
    num banco legado dá "UNIQUE constraint failed" — a linha já está lá, mesmo caso.
    FK, CHECK e NOT NULL violados NÃO são "já existia" e propagam normalmente.
    """
    msg = str(exc).lower()
    if isinstance(exc, sqlite3.OperationalError):
        return "already exists" in msg or "duplicate column name" in msg
    if isinstance(exc, sqlite3.IntegrityError):
        return "unique constraint failed" in msg
    return False


def _aplicar(con, caminho: pathlib.Path) -> dict:
    """Aplica um script estrutural (schema.sql ou uma migração) e registra no ledger,
    tudo numa ÚNICA transação: ou os dois efeitos acontecem, ou nenhum. Ver docstring
    do módulo para o porquê de não usar `executescript` aqui.

    Tolerância POR STATEMENT (banco legado, possivelmente parcial): statement que
    falha porque a estrutura JÁ EXISTE é pulado; os demais executam. Qualquer outro
    erro reverte o script INTEIRO (inclusive statements já executados nesta chamada)
    e nada entra no ledger. Retorna {"executados": n, "pulados": m}.

    `PRAGMA foreign_keys` é NO-OP dentro de uma transação já aberta — por isso liga/
    desliga aqui FORA do `BEGIN`/`COMMIT`, nunca dentro dele. Isso é o que permite uma
    migração reconstruir (DROP/RENAME, o único jeito de alterar CHECK no SQLite) uma
    tabela referenciada por FK de outra (ex.: `parede.perfil_codigo -> perfil_lsf`) sem
    que o `DROP` explodido com "FOREIGN KEY constraint failed" quando já existe dado de
    instância referenciando-a. Verificação de integridade referencial ocorre PRÉ-COMMIT,
    dentro da transação, de forma que violações fazem rollback limpo — nenhuma corrupção
    registrada no ledger.
    """
    statements = _dividir_statements(caminho.read_text())
    executados = 0
    pulados = 0
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.execute("BEGIN")
        try:
            for statement in statements:
                try:
                    con.execute(statement)
                    executados += 1
                except (sqlite3.OperationalError, sqlite3.IntegrityError) as exc:
                    if _falha_indica_ja_existente(exc):
                        pulados += 1  # legado: este objeto/linha já existe, os demais seguem
                    else:
                        raise
            # Verificar integridade referencial PRÉ-COMMIT, ainda dentro da transação
            violacoes = con.execute("PRAGMA foreign_key_check").fetchall()
            if violacoes:
                raise sqlite3.IntegrityError(
                    f"{caminho.name} corromperia integridade referencial: {violacoes}"
                )
        except BaseException:
            con.rollback()  # rollback total: nem tabela parcial, nem ledger
            raise
        con.execute("INSERT INTO schema_migrations (arquivo) VALUES (?)", (caminho.name,))
        con.commit()
    finally:
        con.execute("PRAGMA foreign_keys = ON")
    return {"executados": executados, "pulados": pulados}


def _aplicar_ou_adotar(con, caminho: pathlib.Path) -> str:
    """Aplica com tolerância por statement (ver `_aplicar`). "adotada" = todos os
    statements já existiam (banco legado completo); "aplicada" = ao menos um statement
    executou de fato (script novo ou legado parcial completado agora)."""
    resultado = _aplicar(con, caminho)
    if resultado["executados"] == 0 and resultado["pulados"] > 0:
        return "adotada"
    return "aplicada"


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
