"""Validação do takedown por cálculo próprio (R9 adaptado — decisão do usuário
em 2026-07-18: sem revisão externa de engenheiro; o produto continua emitindo
pré-dimensionamento com gates, mas a VALIDAÇÃO do motor é feita aqui, por conta
independente).

Duas frentes, ambas com a física explícita:

1. EQUILÍBRIO GLOBAL na 109.1506 — estática elementar (ΣFv = 0): tudo que entra
   no modelo (peso próprio das paredes portantes, laje g+q, cobertura) tem que
   sair no térreo ou numa órfã DECLARADA. Se o balanço não fecha, o takedown
   criou ou evaporou carga em silêncio — o pior defeito possível deste motor.

2. CAIXA RETANGULAR calculada À MÃO [NBR 6120] — um caso pequeno o bastante para
   a conta caber num comentário: viga biapoiada entrega w·L/2 em cada apoio;
   parede recebe Σ reações / comprimento. O motor tem que reproduzir o papel.

O que isto NÃO valida (fica registrado, não escondido): a calibração contra uma
obra com projeto ESTRUTURAL real (R9 original) segue pendente por falta do dado
— mesma família da R6 (calibração de coeficientes). Quando um projeto estrutural
da 109 ou da Baias Kabod existir, ele entra como oráculo aqui.
"""
import math

import pytest

from lsf.geradores.estrutura import MARCA_2A_VIGA, gerar_cobertura, gerar_laje
from lsf.motores.cargas import G, peso_parede_kn_m2, takedown_por_parede


def _entradas_kn(con, pid):
    """Tudo que o modelo deixa entrar, somado por fora do takedown."""
    regras = dict(con.execute("SELECT chave, valor FROM regra_lsf"))
    q_uso = regras["carga_sc"]

    entradas = 0.0
    # peso próprio de cada parede PORTANTE (só elas carregam no modelo)
    for ax, az, bx, bz, externa, pd_m in con.execute(
            "SELECT a.x, a.y, b.x, b.y, p.externa, n.pe_direito_m"
            "  FROM parede p"
            "  JOIN no_planta a ON a.id = p.no_a"
            "  JOIN no_planta b ON b.id = p.no_b"
            "  JOIN nivel n ON n.id = p.nivel_id"
            " WHERE n.projeto_id = ? AND p.portante = 1", (pid,)):
        comp = math.hypot(bx - ax, bz - az)
        if comp <= 0:
            continue
        g_m2, _ = peso_parede_kn_m2(con, bool(externa))
        entradas += g_m2 * pd_m * comp

    # laje: cada viga carrega w·L (metade em cada apoio); a 2ª viga do par dá
    # capacidade ao MESMO vão, não carrega outra faixa — fora da soma
    contrapiso = con.execute(
        "SELECT kg_m2 FROM peso_camada WHERE material LIKE 'Contrapiso%'"
    ).fetchone()[0]
    for laje_id, esp in con.execute(
            "SELECT id, esp_m FROM laje WHERE projeto_id = ?", (pid,)):
        pecas, _, _ = gerar_laje(con, laje_id)
        soma_l = sum(p.comp for p in pecas
                     if p.tipo == "viga_laje"
                     and not p.origem_regra.startswith(MARCA_2A_VIGA))
        entradas += (contrapiso * G + q_uso) * esp * soma_l

    # cobertura: banzo inferior carrega w·L da faixa da tesoura
    cob = con.execute(
        "SELECT id FROM cobertura WHERE projeto_id = ? ORDER BY id", (pid,)
    ).fetchone()
    if cob is not None:
        telha = con.execute(
            "SELECT kg_m2 FROM peso_camada WHERE material LIKE 'Telha%'"
            " ORDER BY kg_m2 DESC").fetchone()[0]
        pecas_cob, _, _ = gerar_cobertura(con, cob[0])
        soma_b = sum(p.comp for p in pecas_cob if p.tipo == "banzo_inferior")
        entradas += telha * G * regras["cobertura_esp_tesoura"] * soma_b
    return entradas


def test_equilibrio_global_da_109_fecha(projeto_109_estrutura):
    """ΣFv = 0 no edifício inteiro: entradas == térreo + órfãs declaradas.

    O teste de desigualdade (desce ≤ existe) já existia; este é mais duro — é
    IGUALDADE. Carga que o takedown perdesse sem declarar órfã, ou contasse duas
    vezes, quebra o balanço dos dois lados."""
    con, pid = projeto_109_estrutura
    r = takedown_por_parede(con, pid, com_resumo=True)

    chega_ao_terreo = sum(c.total_kn_m * c.comp_m
                          for c in r.cargas if c.nivel_indice == 0)
    saidas = (chega_ao_terreo + r.orfa_laje_kn + r.orfa_cobertura_kn
              + r.orfa_takedown_kn)
    entradas = _entradas_kn(con, pid)

    # tolerância: total_kn_m sai arredondado a 3 casas × ~160 paredes × ~15 m
    assert saidas == pytest.approx(entradas, rel=2e-3), (
        f"balanço não fecha: entram {entradas:.0f} kN, saem {saidas:.0f} kN —"
        " o takedown criou ou evaporou carga sem declarar órfã")


def test_caixa_retangular_reproduz_a_conta_de_mao(con, caixa_6x4):
    """A conta, no papel [NBR 6120 — viga biapoiada, carga uniforme]:

      w_viga = (contrapiso·g + sc) · modulação = (22·0,00981 + 4,0) · 0,40
             = 1,6863 kN/m
      vigas: z = 0,40 … 3,60 de 0,40 em 0,40  →  9 vigas de 6,00 m
      reação por ponta: w·L/2 = 1,6863 · 3,0  =  5,059 kN
      parede x=0 (4 m): 9 · 5,059 / 4         =  11,38 kN/m de laje
      parede z=0 (6 m): nenhuma viga termina nela → só o peso próprio
      peso próprio ext.: 41,4 kg/m² · 0,00981 · 3,10 = 1,259 kN/m

    O motor tem que devolver isto — não 'algo plausível'."""
    pid, paredes = caixa_6x4
    regras = dict(con.execute("SELECT chave, valor FROM regra_lsf"))
    contrapiso = con.execute(
        "SELECT kg_m2 FROM peso_camada WHERE material LIKE 'Contrapiso%'"
    ).fetchone()[0]

    w_viga = (contrapiso * G + regras["carga_sc"]) * 0.40
    reacao_ponta = w_viga * 6.0 / 2
    g_m2, _ = peso_parede_kn_m2(con, externa=True)
    g_proprio = g_m2 * 3.10

    r = takedown_por_parede(con, pid, com_resumo=True)
    assert r.orfa_laje_kn == 0 and r.orfa_takedown_kn == 0, (
        "na caixa fechada toda viga acha parede: órfã aqui é bug de apoio")

    por_id = {c.parede_id: c for c in r.cargas}
    # 9 vigas: z0+esp até < z1-0,05 → 0,40..3,60
    n_vigas = 9
    laje_kn_m = n_vigas * reacao_ponta / 4.0

    for lado in (1, 3):    # paredes x=0 e x=6 (4 m): recebem as pontas das vigas
        c = por_id[paredes[lado]]
        assert c.g_laje_kn_m + c.q_laje_kn_m == pytest.approx(laje_kn_m, rel=1e-3)
        assert c.total_kn_m == pytest.approx(g_proprio + laje_kn_m, rel=1e-3)
    for lado in (0, 2):    # paredes z=0 e z=4 (6 m): nenhuma viga termina nelas
        c = por_id[paredes[lado]]
        assert c.g_laje_kn_m + c.q_laje_kn_m == 0.0
        assert c.total_kn_m == pytest.approx(g_proprio, rel=1e-3)

    # e o balanço fecha também no caso pequeno, sem órfã nenhuma
    total = sum(c.total_kn_m * c.comp_m for c in r.cargas)
    esperado = g_proprio * (2 * 6 + 2 * 4) + w_viga * n_vigas * 6.0
    assert total == pytest.approx(esperado, rel=1e-3)
