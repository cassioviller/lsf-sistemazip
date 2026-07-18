"""MOTOR 4 — pré-dimensionamento de fundação (Fase 3): NBR 6122 com tensão
presumida da classe_solo + I3 (mínimo construtivo governa em LSF, provado no
spike 4). Emite PRÉ-DIMENSIONAMENTO para orçamento, nunca projeto."""
import pytest

from lsf.geradores.estrutura import DadoIndisponivel
from lsf.motores.fundacao import largura_baldrame, pre_dimensionar


def _solo(con, pid, classe, sondagem_pendente=1):
    con.execute(
        "UPDATE projeto SET classe_solo_id ="
        " (SELECT id FROM classe_solo WHERE classe = ?), sondagem_pendente = ?"
        " WHERE id = ?", (classe, sondagem_pendente, pid))
    con.commit()


def test_largura_os_dois_regimes_na_conta_de_mao():
    """A função central, nos dois regimes [NBR 6122 / I3]:
    12,6 kN/m ÷ 100 kPa = 0,126 m < 0,30 → mínimo construtivo governa;
    45 kN/m ÷ 100 kPa = 0,45 m > 0,30 → tensão do solo governa."""
    larg, governa = largura_baldrame(12.6, 100.0, 0.30)
    assert larg == pytest.approx(0.30) and governa == "mínimo construtivo"
    larg, governa = largura_baldrame(45.0, 100.0, 0.30)
    assert larg == pytest.approx(0.45) and governa == "tensão do solo"


def test_caixa_6x4_volume_exato_da_conta_de_mao(con, caixa_6x4):
    """LSF é leve: TODAS as paredes da caixa caem no mínimo construtivo
    (maior carga ~12,6 kN/m ÷ 100 kPa = 12,6 cm << 30 cm). Volume no papel:
    perímetro 20 m × 0,30 × 0,40 = 2,400 m³ exatos."""
    pid, _ = caixa_6x4
    _solo(con, pid, "S3")
    r = pre_dimensionar(con, pid)
    assert not r.bloqueado
    assert all(f.governa == "mínimo construtivo" for f in r.paredes)
    assert r.volume_m3 == pytest.approx(2.400, rel=1e-3)


def test_sondagem_pendente_rebaixa_a_confianca(con, caixa_6x4):
    """Solo presumido sem sondagem não pode sair com a confiança das cargas:
    o flag rebaixa TUDO da fundação para parametrico (CLAUDE.md: solo é o input
    que o arquitetônico não dá).

    Arranjo: o seed tem 'Peso próprio perfis parede (ref.)' como parametrico, o
    que mascara o rebaixamento (a carga já chega no pior nível). Para ISOLAR o
    mecanismo, eleva-se a camada a estimado — aí a diferença é só a sondagem."""
    pid, _ = caixa_6x4
    con.execute("UPDATE peso_camada SET confianca = 'estimado'"
                " WHERE material = 'Peso próprio perfis parede (ref.)'")
    con.commit()

    _solo(con, pid, "S3", sondagem_pendente=0)
    assert pre_dimensionar(con, pid).confianca == "estimado"

    _solo(con, pid, "S3", sondagem_pendente=1)
    assert pre_dimensionar(con, pid).confianca == "parametrico"


def test_projeto_sem_classe_de_solo_e_erro(con, caixa_6x4):
    """D4.1: fundação sem solo não é fundação com solo default."""
    pid, _ = caixa_6x4
    with pytest.raises(DadoIndisponivel):
        pre_dimensionar(con, pid)


def test_s1_bloqueia_o_pre_dimensionamento(con, caixa_6x4):
    """S1 (aterro não controlado) BLOQUEIA: sem número nenhum, com pendência —
    número em cima de aterro seria pior que nenhum número (gate, não aviso)."""
    pid, _ = caixa_6x4
    _solo(con, pid, "S1")
    r = pre_dimensionar(con, pid)
    assert r.bloqueado
    assert r.volume_m3 is None
    assert not r.paredes
    assert any("S1" in p for p in r.pendencias)


def test_fundacao_e_do_menor_nivel_nao_do_indice_zero(con, caixa_6x4):
    """O radier é o menor nível (a 109 tem cota 0,57 no índice 0 — mas se um
    projeto tiver subsolo com índice -1, é lá que a fundação mora)."""
    pid, _ = caixa_6x4
    _solo(con, pid, "S3")
    nid_sub = con.execute(
        "INSERT INTO nivel (projeto_id, indice, nome, pe_direito_m, cota_m)"
        " VALUES (?, -1, 'subsolo', 2.60, -2.60)", (pid,)).lastrowid
    nos = [con.execute(
        "INSERT INTO no_planta (nivel_id, x, y, confianca) VALUES (?,?,?,'real')",
        (nid_sub, x, y)).lastrowid for x, y in [(0, 0), (6, 0)]]
    con.execute(
        "INSERT INTO parede (nivel_id, no_a, no_b, espessura_m, portante, externa,"
        " perfil_codigo, origem, confianca)"
        " VALUES (?,?,?,0.14,1,1,'Ue90#0.95','MANUAL','real')",
        (nid_sub, nos[0], nos[1]))
    con.commit()

    r = pre_dimensionar(con, pid)
    # só a parede do subsolo entra: 6 m × 0,30 × 0,40 = 0,72 m³
    assert len(r.paredes) == 1
    assert r.volume_m3 == pytest.approx(0.72, rel=1e-3)


def test_origem_regra_anotada(con, caixa_6x4):
    pid, _ = caixa_6x4
    _solo(con, pid, "S3")
    r = pre_dimensionar(con, pid)
    assert "NBR 6122" in r.origem_regra
    for f in r.paredes:
        assert "NBR 6122" in f.origem_regra
