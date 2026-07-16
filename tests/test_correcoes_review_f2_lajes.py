"""Correções do code review do branch fase2-estrutura-lajes-cobertura.

Cada teste fixa um achado: confiança que melhorava o input (D4), peça afirmando
verificação normativa que não houve, área negativa virando quantidade seca (D4.1),
contorno truncado em silêncio e diagonal de canto invertida com beiral=0.
"""
import pytest

from lsf.geradores.geometria import encadear_contorno


def test_contorno_nao_trunca_acima_de_200_segmentos(oraculo=None):
    """O guard fixo de 200 do v7 truncava o contorno em silêncio: footprint menor,
    kg menor, nenhum aviso. Um polígono de 400 lados tem que voltar inteiro."""
    n = 400
    pts = [(float(i), 0.0) for i in range(n)]
    segs = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    assert len(encadear_contorno(segs)) == n


def test_confianca_da_laje_nunca_melhora_no_derivado(projeto_109_estrutura):
    """D4: laje 'parametrico' não pode gerar peça 'estimado' (rank menor = melhor).
    As bordas de varanda e a chapa de piso fixavam o literal 'estimado'.
    A 1LJ da 109 tem extensão (varanda) e chapa de piso, então cobre os dois casos."""
    from lsf.geradores.estrutura import gerar_laje

    con, pid = projeto_109_estrutura
    lid = con.execute("SELECT id FROM laje WHERE projeto_id = ? ORDER BY id",
                      (pid,)).fetchone()[0]
    con.execute("UPDATE laje SET confianca = 'parametrico' WHERE id = ?", (lid,))

    pecas, acess, _ = gerar_laje(con, lid)
    assert pecas and acess, "a laje precisa gerar peças e acessórios"
    melhores = {p.origem_regra for p in pecas if p.confianca != "parametrico"}
    assert not melhores, (
        f"peça derivada afirmou confiança melhor que a da laje: {melhores}")
    assert all(a.confianca == "parametrico" for a in acess)


def test_viga_em_modo_laminada_nao_se_diz_verificada(projeto_109_estrutura):
    """Quando nem a dupla passa, a peça extra é PROVISÃO de orçamento: não pode
    carregar 'viga DUPLA ... [NBR 14762]' como se o cálculo a tivesse aprovado."""
    from lsf.geradores.estrutura import gerar_laje

    con, pid = projeto_109_estrutura
    lid = con.execute("SELECT id FROM laje WHERE projeto_id = ? ORDER BY id",
                      (pid,)).fetchone()[0]
    pecas, _, alertas = gerar_laje(con, lid)
    assert any("laminada" in a for a in alertas), "a 1LJ da 109 reprova até a dupla"
    extras = [p for p in pecas if p.tipo == "viga_laje"
              and "NBR 14762" in p.origem_regra]
    assert not extras, (
        "viga de laje citou NBR 14762 num vão que a verificação reprovou")
    assert any("PROVISÃO" in p.origem_regra for p in pecas)


def test_pendencia_estrutural_sobe_ate_a_eap_e_nao_morre_no_retorno(projeto_109_estrutura):
    """O achado mais grave do review: `derivar_quantitativos` lia só kg e confiança,
    então o alerta 'reprova até viga dupla' das duas lajes da 109 morria no retorno
    e a 03.01 recebia um kg limpo. Gate que não bloqueia nem avisa é disclaimer
    morto — a pendência tem que chegar na linha da EAP."""
    from lsf.geradores.estrutura import MARCA_PENDENCIA, derivar_quantitativos

    con, pid = projeto_109_estrutura
    r = derivar_quantitativos(con, pid)

    assert r["gravado"] is True
    assert r["pendencias_estruturais"], "a 109 reprova nas duas lajes"
    assert all(p.startswith(MARCA_PENDENCIA) for p in r["pendencias_estruturais"])
    assert r["alertas"], "os alertas do gerador têm que subir no retorno"

    origem_regra = con.execute(
        "SELECT origem_regra FROM quantitativo q JOIN eap_item e ON e.id = q.eap_item_id"
        " WHERE e.codigo = '03.01' AND q.projeto_id = ?", (pid,)).fetchone()[0]
    assert MARCA_PENDENCIA in origem_regra, (
        "o kg foi gravado na EAP sem rastro de que a verificação reprovou")
    assert "PROVISÃO" in origem_regra


def test_projeto_sem_pendencia_nao_marca_a_eap(projeto_109_estrutura):
    """A marca só aparece quando há reprovação: sem isso ela viraria ruído e
    pararia de significar alguma coisa."""
    from lsf.geradores.estrutura import MARCA_PENDENCIA, derivar_quantitativos

    con, pid = projeto_109_estrutura
    # sem laje não há verificação de viga → não há pendência estrutural
    con.execute("DELETE FROM laje_abertura")
    con.execute("DELETE FROM laje_extensao")
    con.execute("DELETE FROM laje WHERE projeto_id = ?", (pid,))

    r = derivar_quantitativos(con, pid)
    assert r["pendencias_estruturais"] == []
    origem_regra = con.execute(
        "SELECT origem_regra FROM quantitativo q JOIN eap_item e ON e.id = q.eap_item_id"
        " WHERE e.codigo = '03.01' AND q.projeto_id = ?", (pid,)).fetchone()[0]
    assert MARCA_PENDENCIA not in origem_regra


def test_diagonal_de_canto_aponta_para_dentro_mesmo_sem_beiral(projeto_109_estrutura):
    """`direcao = 1 if xe < bb.x0 else -1` invertia a ponta esquerda quando
    beiral=0 (xe == bb.x0 → False → -1), jogando a diagonal para fora da água."""
    from lsf.geradores.estrutura import gerar_cobertura

    con, pid = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura WHERE projeto_id = ?",
                      (pid,)).fetchone()[0]
    con.execute("UPDATE cobertura SET beiral_m = 0 WHERE id = ?", (cid,))

    pecas, _, _ = gerar_cobertura(con, cid)
    diags = [p for p in pecas if p.tipo == "diag_canto_1CB"]
    assert diags
    xs = [p.x0 for p in pecas]
    x_min, x_max = min(xs), max(xs)
    for d in diags:
        assert x_min - 1e-6 <= d.x1 <= x_max + 1e-6, (
            f"diagonal de canto saiu da água: x0={d.x0} → x1={d.x1}")


def test_area_de_telha_nao_negativa_vira_pendencia(projeto_109_estrutura):
    """D4.1: pátio maior que a água não pode virar m² negativo de telha."""
    from lsf.geradores.estrutura import DadoIndisponivel, gerar_cobertura

    con, pid = projeto_109_estrutura
    cid = con.execute("SELECT id FROM cobertura WHERE projeto_id = ?",
                      (pid,)).fetchone()[0]
    con.execute("UPDATE area_descoberta SET w = 500, d = 500 WHERE tipo = 'patio'")

    with pytest.raises(DadoIndisponivel, match="telha"):
        gerar_cobertura(con, cid)


def test_area_de_piso_nao_negativa_vira_pendencia(projeto_109_estrutura):
    """D4.1: aberturas somando mais que o footprint não viram chapa negativa."""
    from lsf.geradores.estrutura import DadoIndisponivel, gerar_laje

    con, pid = projeto_109_estrutura
    lid = con.execute(
        "SELECT l.id FROM laje l JOIN laje_abertura a ON a.laje_id = l.id"
        " WHERE l.projeto_id = ? AND l.chapa_piso_tipo IS NOT NULL"
        " ORDER BY l.id", (pid,)).fetchone()[0]
    con.execute("UPDATE laje_abertura SET w = 500, d = 500 WHERE laje_id = ?", (lid,))

    with pytest.raises(DadoIndisponivel, match="área de piso"):
        gerar_laje(con, lid)
