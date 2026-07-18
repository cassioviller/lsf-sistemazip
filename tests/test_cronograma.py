"""MOTOR 2 — Cronograma (Fase 4): CPM TI/II/TT com lag sobre a MESMA EAP do
orçamento (D1). Toda rede de teste tem o gabarito calculado à mão no docstring."""
import pytest

from lsf.motores.cronograma import (Atividade, CicloNaRede, cpm,
                                    cronograma_projeto, horas_mo_composicao,
                                    montar_atividades)
from lsf.motores.orcamento import CustoIndisponivel


def _id_comp(con, codigo):
    return con.execute("SELECT id FROM composicao WHERE codigo_fonte = ?",
                       (codigo,)).fetchone()[0]


# ---------- homem-horas por unidade ----------

def test_horas_mo_das_composicoes_do_seed(con):
    """VK-C-001: montador 0,040 + ajudante 0,040 = 0,080 h/kg.
    VK-C-005: pedreiro 3,5 + ajudante 5,0 = 8,5 h/m³."""
    assert horas_mo_composicao(con, _id_comp(con, "VK-C-001")) == pytest.approx(0.080)
    assert horas_mo_composicao(con, _id_comp(con, "VK-C-005")) == pytest.approx(8.5)


def test_horas_mo_recursivo_em_composicao_aninhada(con):
    """Composição que contém VK-C-001 com coeficiente 2 herda 2×0,080=0,16 h."""
    fonte = con.execute("SELECT id FROM fonte WHERE sigla='VEKS'").fetchone()[0]
    nova = con.execute(
        "INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,"
        " grupo_eap,confianca) VALUES (?,?,?,?,?,?)",
        (fonte, "VK-C-TST", "aninhada", "un", "ESTRUTURA", "estimado")).lastrowid
    con.execute(
        "INSERT INTO composicao_item (composicao_id,item_tipo,item_id,coeficiente)"
        " VALUES (?,?,?,2.0)", (nova, "COMPOSICAO", _id_comp(con, "VK-C-001")))
    con.commit()
    assert horas_mo_composicao(con, nova) == pytest.approx(0.16)


def test_horas_mo_sem_analitica_e_erro(con):
    """Composição SINAPI sem analítica importada: exceção, nunca 0 h (D4.1) —
    0 h viraria atividade de duração zero calada."""
    with pytest.raises(CustoIndisponivel):
        horas_mo_composicao(con, _id_comp(con, "96359"))


# ---------- CPM ----------

def _atv(grupo, dur, custo=1000.0):
    return Atividade(grupo=grupo, codigo=grupo, descricao=grupo,
                     duracao_dias=dur, custo=custo, hh=0.0, confianca="estimado")


def test_cpm_reproduz_o_spike_2():
    """A(3)→B(4)→D(2) e A→C(2)→D, tudo TI+0: fim=9, crítico A-B-D."""
    ats = [_atv("A", 3), _atv("B", 4), _atv("C", 2), _atv("D", 2)]
    rede = [("A", "B", "TI", 0), ("A", "C", "TI", 0),
            ("B", "D", "TI", 0), ("C", "D", "TI", 0)]
    prog, makespan = cpm(ats, rede)
    assert makespan == 9
    assert [p.atividade.grupo for p in prog if p.critica] == ["A", "B", "D"]
    folga_c = next(p for p in prog if p.atividade.grupo == "C")
    assert folga_c.folga == pytest.approx(2)


def test_cpm_ii_e_tt_conferidos_a_mao():
    """A(10) e B(4) com A→B II+5 e A→B TT+2 (atividade contígua, sem esticar):
      ES_B = max(ES_A+5, EF_A+2−4) = max(5, 8) = 8 → EF_B = 12 (TT governa).
    Makespan 12; ambas críticas (B não pode adiantar nem atrasar)."""
    prog, makespan = cpm([_atv("A", 10), _atv("B", 4)],
                         [("A", "B", "II", 5), ("A", "B", "TT", 2)])
    b = next(p for p in prog if p.atividade.grupo == "B")
    assert (b.es, b.ef) == (8, 12)
    assert makespan == 12
    assert all(p.critica for p in prog)


def test_cpm_ciclo_e_erro():
    with pytest.raises(CicloNaRede):
        cpm([_atv("A", 1), _atv("B", 1)],
            [("A", "B", "TI", 0), ("B", "A", "TI", 0)])


def test_cpm_vinculo_para_grupo_ausente_e_ignorado():
    """Rede do banco cita PRELIM; projeto sem quantitativo em PRELIM não pode
    travar o CPM — o vínculo com ponta ausente sai da conta."""
    prog, makespan = cpm([_atv("B", 4)], [("A", "B", "TI", 3)])
    assert makespan == 4


# ---------- atividades derivadas do projeto (D1: mesma EAP) ----------

def _derivar_caixa(con, caixa_6x4):
    from lsf.geradores.estrutura import derivar_quantitativos
    from lsf.motores.fundacao import derivar_fundacao

    pid, _ = caixa_6x4
    con.execute(
        "UPDATE projeto SET classe_solo_id ="
        " (SELECT id FROM classe_solo WHERE classe='S3') WHERE id = ?", (pid,))
    con.commit()
    derivar_quantitativos(con, pid)
    derivar_fundacao(con, pid)
    return pid


def test_atividades_da_caixa_com_duracao_derivada(con, caixa_6x4):
    """Duração = ceil(Σ hh / (equipe × jornada)) — na caixa, à mão:
      02: 2,400 m³ × 8,5 h = 20,4 hh ÷ (4×8) = 0,64 → 1 dia
      03: a caixa TEM laje (fixture) → kg comprado ≈ 929; 929 × 0,080 = 74,3 hh
          ÷ 32 = 2,32 → 3 dias."""
    pid = _derivar_caixa(con, caixa_6x4)
    atividades, alertas = montar_atividades(con, pid)
    por_grupo = {a.grupo: a for a in atividades}
    assert por_grupo["FUNDACAO"].duracao_dias == 1
    assert por_grupo["ESTRUTURA"].duracao_dias == 3
    assert por_grupo["ESTRUTURA"].hh == pytest.approx(74.3, abs=1.0)
    assert por_grupo["FUNDACAO"].custo and por_grupo["FUNDACAO"].custo > 0
    # macroetapas sem quantitativo ficam fora, MAS avisadas (o R7 cuida do gate)
    assert "PRELIM" not in por_grupo
    assert any("zerada" in a.lower() or "sem quantitativo" in a.lower()
               for a in alertas)


def test_cronograma_da_caixa_na_conta_de_mao(con, caixa_6x4):
    """FUNDACAO(1d) →TI+3 (cura Parabolt)→ ESTRUTURA(3d):
    ES/EF = 02:[0,1] · 03:[4,7] → makespan 7, ambos críticos."""
    pid = _derivar_caixa(con, caixa_6x4)
    crono = cronograma_projeto(con, pid)
    por_grupo = {p.atividade.grupo: p for p in crono.atividades}
    assert (por_grupo["FUNDACAO"].es, por_grupo["FUNDACAO"].ef) == (0, 1)
    assert (por_grupo["ESTRUTURA"].es, por_grupo["ESTRUTURA"].ef) == (4, 7)
    assert crono.makespan_dias == 7
    assert por_grupo["FUNDACAO"].critica and por_grupo["ESTRUTURA"].critica
    assert crono.confianca in ("estimado", "parametrico")
