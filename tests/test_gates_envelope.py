"""Gate de envelope — porta de `rodarGates` (v7).

Auto-verificação do gerador: peça de sistema horizontal (laje/escada/cobertura/
forro) que cai fora do envelope do prédio (bbox do térreo + 0,5 m + beiral) é bug
do gerador, não geometria exótica. O v7 marca sev='alta'; aqui vira pendência,
porque kg de peça fora do prédio já entrou na conta.

Existe por experiência: a diagonal de canto 1CB apontava para FORA da água quando
beiral=0 (`direcao` derivada de `xe < bb.x0`), e nada acusava. Gate pega a classe,
não o caso.
"""
import pytest


def test_109_nao_tem_peca_fora_do_envelope(projeto_109_estrutura):
    from lsf.geradores.estrutura import gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    assert [a for a in est.alertas if "envelope" in a] == []


def test_peca_fora_do_envelope_vira_pendencia(projeto_109_estrutura):
    """Empurra a cobertura para longe do prédio: as peças dela saem do envelope
    e o gate tem que acusar — em vez de somar kg de um telhado no vizinho."""
    from lsf.geradores.estrutura import MARCA_PENDENCIA, gerar_estrutura

    con, pid = projeto_109_estrutura
    # extensão de laje (faixa de varanda) cadastrada longe do prédio: as bordas e
    # vigas dela nascem em x=500, muito além do envelope
    lid = con.execute("SELECT id FROM laje WHERE projeto_id = ? ORDER BY id",
                      (pid,)).fetchone()[0]
    con.execute("INSERT INTO laje_extensao (laje_id, x, z, w, d) VALUES (?,500,2,3,4)",
                (lid,))

    est = gerar_estrutura(con, pid)
    fora = [a for a in est.alertas if "envelope" in a]
    assert fora, "peça fora do envelope passou calada"
    assert fora[0].startswith(MARCA_PENDENCIA)
    assert fora[0] in est.pendencias_estruturais


def test_parede_nao_entra_no_gate(projeto_109_estrutura):
    """O v7 pula `sistema==='parede'`: a parede DEFINE o envelope, não é medida
    contra ele — senão o gate acusaria a si mesmo."""
    from lsf.geradores.estrutura import rodar_gates_envelope, gerar_estrutura

    con, pid = projeto_109_estrutura
    est = gerar_estrutura(con, pid)
    paredes = [p for p in est.pecas if p.sistema == "parede"]
    assert paredes
    assert rodar_gates_envelope(con, pid, paredes) == []
