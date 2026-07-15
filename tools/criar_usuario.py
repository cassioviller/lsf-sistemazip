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
