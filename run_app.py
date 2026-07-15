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
