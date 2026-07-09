"""Constrói lsf_base.db a partir de schema.sql + seed.sql. Uso: python3 db/build_db.py"""
import sqlite3, pathlib
d = pathlib.Path(__file__).parent
db_path = d / "lsf_base.db"
if db_path.exists(): db_path.unlink()
con = sqlite3.connect(db_path)
con.executescript((d / "schema.sql").read_text())
con.executescript((d / "seed.sql").read_text())
con.commit()
n = con.execute("SELECT COUNT(*) FROM vw_custo_composicao").fetchone()[0]
print(f"lsf_base.db construído ✓  ({n} composições precificáveis na view)")
