"""Suíte de regressão: os 6 spikes que validaram o plano (docs/02, §2) devem passar sempre.
Pré-requisito: python3 db/build_db.py (o spike 4 e 6 leem o banco)."""
import subprocess, sys, pathlib, shutil
def test_spikes_validacao():
    root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(root / "db" / "lsf_base.db", root / "tests" / "lsf_base.db")
    r = subprocess.run([sys.executable, str(root / "tests" / "spikes_validacao.py")],
                       cwd=root / "tests", capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TODOS OS 6 SPIKES PASSARAM" in r.stdout
