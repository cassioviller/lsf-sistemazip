"""Seed de conhecimento — regras estruturais (laje/escada/cobertura), cargas NBR e perfis novos.

Fase 2, Task 3. `con` (banco em memória de schema+migrações+seed) vem de tests/conftest.py.
"""


def _regra(con, chave):
    r = con.execute("SELECT valor FROM regra_lsf WHERE chave=?", (chave,)).fetchone()
    return r[0] if r else None


def test_regras_de_laje_seedadas(con):
    assert _regra(con, "laje_esp_m") == 0.40
    assert _regra(con, "laje_bloqueador_max_m") == 2.40
    assert _regra(con, "laje_vao_ue200") == 4.0


def test_cargas_estruturais_seedadas_com_referencia(con):
    for chave in ("carga_sc", "carga_g", "aco_fy", "aco_E", "coef_gm", "flecha_lim"):
        row = con.execute(
            "SELECT valor, referencia FROM regra_lsf WHERE chave=?", (chave,)).fetchone()
        assert row is not None, chave
        assert row[1] and ("NBR" in row[1]), f"{chave} sem referência normativa"


def test_perfis_novos_com_massa(con):
    for cod, massa in [("U202#0.95", 2.10), ("U252#1.25", 3.26),
                       ("W310x32.7", 32.7), ("HSS100x100x4.8", 14.2)]:
        m = con.execute("SELECT massa_kg_m FROM perfil_lsf WHERE codigo=?",
                        (cod,)).fetchone()
        assert m is not None and m[0] == massa, cod
