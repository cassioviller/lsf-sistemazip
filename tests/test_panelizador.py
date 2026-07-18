"""Panelizador (Fase 5, evolução do spike 5): painéis com ID no padrão do
caderno (1PV-P01), peças atribuídas por posição. O invariante que importa:
NENHUMA peça órfã, NENHUMA duplicada — o kg dos painéis É o kg da parede."""
import pytest

from lsf.geradores.estrutura import gerar_parede
from lsf.geradores.panelizador import panelizar_parede


def _parede_longa_da_109(con, projeto_109):
    """T-E2 (fundo, 15,8 m): 5 painéis — a parede mais comprida do térreo."""
    pid = projeto_109["mapa"]["0/T-E2"]
    return pid, gerar_parede(con, pid)


def test_paineis_cobrem_todas_as_pecas_sem_duplicar(con, projeto_109):
    parede_id, est = _parede_longa_da_109(con, projeto_109)
    paineis = panelizar_parede(est, nivel_indice=0, seq_inicial=1)
    assert len(paineis) == est.n_paineis

    tags_paineis = [p.tag for painel in paineis for p in painel.pecas]
    tags_parede = [p.tag for p in est.pecas]
    assert sorted(tags_paineis) == sorted(tags_parede), (
        "peça órfã ou duplicada na panelização")

    # cada painel arredonda o kg a 2 casas — o desvio admissível é só isso
    # (peça perdida é pega pela igualdade de tags acima, que é EXATA)
    kg_paineis = sum(painel.kg for painel in paineis)
    kg_parede = sum(est.kg_por_perfil.values())
    assert kg_paineis == pytest.approx(kg_parede, abs=0.01 * len(paineis))


def test_ids_no_padrao_do_caderno(con, projeto_109):
    _, est = _parede_longa_da_109(con, projeto_109)
    paineis = panelizar_parede(est, nivel_indice=0, seq_inicial=7)
    assert paineis[0].id == "1PV-P07"
    assert paineis[1].id == "1PV-P08"
    # nível 1 usa o prefixo 2PV (índice+1, como o v7)
    paineis_n1 = panelizar_parede(est, nivel_indice=1, seq_inicial=1)
    assert paineis_n1[0].id == "2PV-P01"


def test_peca_atribuida_ao_painel_onde_comeca(con, projeto_109):
    """As faixas dos painéis particionam a parede: toda peça cai no painel em
    cujo intervalo [x_ini, x_fim) o seu menor x está."""
    _, est = _parede_longa_da_109(con, projeto_109)
    paineis = panelizar_parede(est, nivel_indice=0, seq_inicial=1)
    for painel in paineis:
        for p in painel.pecas:
            inicio = min(p.x0, p.x1)
            assert painel.x_ini - 1e-6 <= inicio < painel.x_fim + 1e-6, (
                f"peça {p.tag} começa em {inicio} fora do painel"
                f" [{painel.x_ini}, {painel.x_fim})")


def test_parede_de_um_painel_so(con, projeto_109):
    """Parede curta (T-E4, 2,9 m): 1 painel com tudo dentro."""
    pid = projeto_109["mapa"]["0/T-E4"]
    est = gerar_parede(con, pid)
    paineis = panelizar_parede(est, nivel_indice=0, seq_inicial=1)
    assert len(paineis) == 1
    assert len(paineis[0].pecas) == len(est.pecas)


# ---------- romaneio fábrica/obra ----------

def test_romaneio_da_109_cobre_todo_o_kg_de_parede(con, projeto_109):
    """O aceite da fase: nenhum kg de parede fora de painel. O total do romaneio
    é o Σ das paredes do gerador (lajes/cobertura não são painéis de parede)."""
    from lsf.geradores.estrutura import gerar_estrutura
    from lsf.geradores.panelizador import romaneio_projeto

    pid = projeto_109["projeto_id"]
    rom = romaneio_projeto(con, pid)
    est = gerar_estrutura(con, pid)
    kg_paredes = sum(sum(ep.kg_por_perfil.values()) for ep in est.paredes)
    assert rom.kg_total == pytest.approx(kg_paredes, abs=0.01 * len(rom.paineis))
    assert len(rom.paineis) == sum(ep.n_paineis for ep in est.paredes)


def test_romaneio_ids_por_nivel_e_kits_por_perfil(con, projeto_109):
    from lsf.geradores.panelizador import romaneio_projeto

    pid = projeto_109["projeto_id"]
    rom = romaneio_projeto(con, pid)
    ids = [p.painel.id for p in rom.paineis]
    assert ids[0] == "1PV-P01"
    assert any(i.startswith("2PV-") for i in ids)
    assert any(i.startswith("3PV-") for i in ids)
    assert len(ids) == len(set(ids)), "ID de painel duplicado"

    com_kit = [p for p in rom.paineis if p.kits]
    assert com_kit, "nenhum kit de corte gerado"
    kit = com_kit[0].kits[0]
    assert kit.n_pecas > 0 and kit.kg > 0 and kit.barras > 0


def test_romaneio_csv_tem_fabrica_e_obra(con, projeto_109):
    from lsf.geradores.panelizador import romaneio_projeto
    from lsf.relatorios import romaneio_csv

    rom = romaneio_projeto(con, projeto_109["projeto_id"])
    csv_texto = romaneio_csv(rom)
    assert "FABRICA" in csv_texto and "OBRA" in csv_texto
    assert "1PV-P01" in csv_texto
    assert ";" in csv_texto            # padrão pt-BR da casa
