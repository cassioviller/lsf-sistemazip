"""O gate de publicação tem que BLOQUEAR com pendência estrutural.

Por que bloqueia (e não carimba como a sondagem): a 109 é a prova. O gerador diz
que as duas lajes exigem viga laminada 1VG + pilares 1AL, a obra foi construída
com eles, e o orçamento de referência — o mesmo que fechou a Fase 1 com 0,00% —
NÃO tem linha para nenhum dos dois. O kg que sai é provisão em perfil LSF.
Publicar isso como preço fechado é o "escopo vazado = prejuízo" do CLAUDE.md
acontecendo no projeto de referência.
"""
import pytest


def test_derivar_grava_pendencia_no_banco(projeto_109_estrutura):
    from lsf.geradores.estrutura import derivar_quantitativos

    con, pid = projeto_109_estrutura
    r = derivar_quantitativos(con, pid)
    assert r["pendencias_estruturais"]

    gravadas = [m for (m,) in con.execute(
        "SELECT mensagem FROM pendencia WHERE projeto_id = ? AND motor = 'estrutura'",
        (pid,))]
    assert len(gravadas) == len(r["pendencias_estruturais"])


def test_rederivar_substitui_as_pendencias_em_vez_de_empilhar(projeto_109_estrutura):
    """D2: re-derivar troca as linhas. Pendência duplicada viraria ruído e o gate
    pararia de ser lido."""
    from lsf.geradores.estrutura import derivar_quantitativos

    con, pid = projeto_109_estrutura
    derivar_quantitativos(con, pid)
    n1 = con.execute("SELECT COUNT(*) FROM pendencia WHERE projeto_id = ?",
                     (pid,)).fetchone()[0]
    derivar_quantitativos(con, pid)
    n2 = con.execute("SELECT COUNT(*) FROM pendencia WHERE projeto_id = ?",
                     (pid,)).fetchone()[0]
    assert n1 == n2 > 0


def test_pendencia_resolvida_some_do_banco(projeto_109_estrutura):
    """Sumiu a causa, some a pendência — senão o gate trava para sempre e alguém
    aprende a ignorá-lo."""
    from lsf.geradores.estrutura import derivar_quantitativos

    con, pid = projeto_109_estrutura
    derivar_quantitativos(con, pid)
    assert con.execute("SELECT COUNT(*) FROM pendencia WHERE projeto_id = ?",
                       (pid,)).fetchone()[0] > 0

    con.execute("DELETE FROM laje_abertura")
    con.execute("DELETE FROM laje_extensao")
    con.execute("DELETE FROM laje WHERE projeto_id = ?", (pid,))
    con.execute("DELETE FROM furo_critico WHERE projeto_id = ?", (pid,))
    derivar_quantitativos(con, pid)
    assert con.execute("SELECT COUNT(*) FROM pendencia WHERE projeto_id = ?",
                       (pid,)).fetchone()[0] == 0
