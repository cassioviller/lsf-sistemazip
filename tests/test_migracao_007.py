"""Migração 007: `vao.peitoril_m` vira NULLable — NULL = "não informado".

Semântica do v7 (`a.peitoril ?? R.peitorilPadrao`, nullish): ausente usa a regra
`peitoril_padrao_m`; 0 explícito é respeitado (porta-janela). O schema da 004
tinha NOT NULL DEFAULT 0, que confundia os dois casos.
"""
import sqlite3

import pytest


def _vao(con, planta, **campos):
    parede_id = planta(comp=4.0)
    colunas = {"parede_id": parede_id, "tipo": "JANELA", "posicao_m": 1.2,
               "largura_m": 1.6, "altura_m": 1.2, **campos}
    nomes = ",".join(colunas)
    cur = con.execute(
        f"INSERT INTO vao ({nomes}) VALUES ({','.join('?' * len(colunas))})",
        tuple(colunas.values()))
    return cur.lastrowid


def test_peitoril_ausente_vira_null_nao_zero(con, planta):
    """DEFAULT agora é NULL: inserir sem informar peitoril grava NULL."""
    vao_id = _vao(con, planta)
    valor = con.execute(
        "SELECT peitoril_m FROM vao WHERE id = ?", (vao_id,)).fetchone()[0]
    assert valor is None


def test_peitoril_null_explicito_aceito(con, planta):
    vao_id = _vao(con, planta, peitoril_m=None)
    valor = con.execute(
        "SELECT peitoril_m FROM vao WHERE id = ?", (vao_id,)).fetchone()[0]
    assert valor is None


def test_peitoril_zero_explicito_permanece_zero(con, planta):
    """0 explícito é dado, não ausência (porta-janela) — e é o que acontece com
    linhas legadas gravadas pelo DEFAULT 0 antigo (indistinguíveis, anotado na
    migração)."""
    vao_id = _vao(con, planta, peitoril_m=0)
    valor = con.execute(
        "SELECT peitoril_m FROM vao WHERE id = ?", (vao_id,)).fetchone()[0]
    assert valor == 0


def test_peitoril_negativo_continua_rejeitado(con, planta):
    with pytest.raises(sqlite3.IntegrityError):
        _vao(con, planta, peitoril_m=-0.5)


def test_fk_para_parede_sobrevive_ao_rebuild(con, planta):
    """O rebuild (CREATE+INSERT SELECT+DROP+RENAME) tem que preservar a FK."""
    planta(comp=4.0)  # garante que a estrutura existe
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO vao (parede_id, tipo, posicao_m, largura_m, altura_m)"
            " VALUES (999999, 'PORTA', 1.0, 0.9, 2.1)")


def test_migracao_preserva_dados_legados(tmp_path):
    """Banco pré-007 com vãos gravados: o rebuild preserva TODAS as linhas e
    valores. ATENÇÃO documentada: legado com 0 (o DEFAULT antigo) continua 0 —
    não há como distinguir retroativamente '0 explícito' de 'não informado'."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[1]
    c = sqlite3.connect(":memory:")
    c.executescript((raiz / "db" / "schema.sql").read_text())
    migracoes = sorted((raiz / "db" / "migrations").glob("*.sql"))
    for m in migracoes:
        if m.name.startswith("007"):
            break
        c.executescript(m.read_text())
    c.executescript((raiz / "db" / "seed.sql").read_text())
    # instância pré-007 (peitoril_m NOT NULL DEFAULT 0)
    c.execute("INSERT INTO projeto (codigo, nome, referencia, uf, desonerado)"
              " VALUES ('LEG', 'Legado', '2026-06', 'SP', 0)")
    pid = c.execute("SELECT id FROM projeto WHERE codigo='LEG'").fetchone()[0]
    c.execute("INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m)"
              " VALUES (?,0,'Térreo',3.1)", (pid,))
    nid = c.execute("SELECT id FROM nivel").fetchone()[0]
    a = c.execute("INSERT INTO no_planta (nivel_id,x,y) VALUES (?,0,0)", (nid,)).lastrowid
    b = c.execute("INSERT INTO no_planta (nivel_id,x,y) VALUES (?,4,0)", (nid,)).lastrowid
    parede_id = c.execute(
        "INSERT INTO parede (nivel_id,no_a,no_b,espessura_m,origem)"
        " VALUES (?,?,?,0.14,'MANUAL')", (nid, a, b)).lastrowid
    c.execute("INSERT INTO vao (parede_id,tipo,posicao_m,largura_m,altura_m)"
              " VALUES (?,'JANELA',1.2,1.6,1.2)", (parede_id,))       # DEFAULT 0 antigo
    c.execute("INSERT INTO vao (parede_id,tipo,posicao_m,largura_m,altura_m,peitoril_m)"
              " VALUES (?,'JANELA',2.9,0.6,0.6,1.5)", (parede_id,))

    sete = [m for m in migracoes if m.name.startswith("007")]
    assert sete, "migração 007 não existe"
    c.executescript(sete[0].read_text())

    linhas = c.execute(
        "SELECT posicao_m, peitoril_m FROM vao ORDER BY posicao_m").fetchall()
    assert [tuple(l) for l in linhas] == [(1.2, 0.0), (2.9, 1.5)]
    c.close()
