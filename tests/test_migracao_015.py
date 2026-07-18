"""Migração 015 — rede de precedências LSF e equipes como DADO (Fase 4).
A rede mora no banco porque é conhecimento de obra que muda com calibração,
não estrutura de código."""


def _grupos(con):
    return {g for (g,) in con.execute(
        "SELECT DISTINCT grupo_eap FROM eap_item WHERE pai_id IS NULL")}


def test_rede_lsf_semeada_e_valida(con):
    grupos = _grupos(con)
    rede = con.execute(
        "SELECT grupo_pred, grupo_succ, tipo, lag_dias FROM precedencia_macroetapa"
    ).fetchall()
    assert rede, "rede de precedências vazia"
    for pred, succ, tipo, lag in rede:
        assert pred in grupos and succ in grupos
        assert tipo in ("TI", "II", "TT")
        assert lag >= 0

    # os vínculos estruturantes da obra LSF, com os três tipos exercidos
    assert ("PRELIM", "FUNDACAO", "TI") in {(p, s, t) for p, s, t, _ in rede}
    assert ("FUNDACAO", "ESTRUTURA", "TI") in {(p, s, t) for p, s, t, _ in rede}
    assert ("ESTRUTURA", "FECHAMENTO", "II") in {(p, s, t) for p, s, t, _ in rede}
    assert ("ESTRUTURA", "FECHAMENTO", "TT") in {(p, s, t) for p, s, t, _ in rede}


def test_rede_sem_ciclo(con):
    """CPM sobre rede cíclica trava — o dado tem que nascer acíclico."""
    arestas = con.execute(
        "SELECT grupo_pred, grupo_succ FROM precedencia_macroetapa").fetchall()
    suc = {}
    for p, s in arestas:
        suc.setdefault(p, []).append(s)

    visitando, ok = set(), set()

    def visita(n):
        if n in ok:
            return
        assert n not in visitando, f"ciclo passando por {n}"
        visitando.add(n)
        for s in suc.get(n, []):
            visita(s)
        visitando.discard(n)
        ok.add(n)

    for n in list(suc):
        visita(n)


def test_equipes_para_todo_grupo_com_folha(con):
    """Grupo que pode ter quantitativo precisa de equipe — senão a duração não
    deriva e o cronograma quebraria só em runtime."""
    equipes = {g: (t, h) for g, t, h in con.execute(
        "SELECT grupo_eap, trabalhadores, hammock FROM equipe_macroetapa")}
    for g in _grupos(con):
        assert g in equipes, f"grupo {g} sem equipe cadastrada"
        assert equipes[g][0] > 0

    assert equipes["GERENCIAMENTO"][1] == 1, "GERENCIAMENTO é hammock"
    assert sum(h for _, h in equipes.values()) == 1, "só um hammock na rede"

    jornada = con.execute(
        "SELECT valor FROM regra_lsf WHERE chave='jornada_h_dia'").fetchone()
    assert jornada is not None and jornada[0] == 8.0
