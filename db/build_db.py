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
