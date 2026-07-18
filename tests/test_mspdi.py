"""Saída MSPDI (XML do MS Project, importável no ProjectLibre) — a validação
cruzada automatizável: o XML é re-parseado e as datas/durações/vínculos têm que
bater com o CPM. A conferência visual no ProjectLibre é ação do usuário sobre o
arquivo (registrada no plano da fase)."""
import datetime
import xml.etree.ElementTree as ET

import pytest

from lsf.motores.cronograma import cronograma_projeto
from lsf.relatorios import exportar_mspdi

NS = {"p": "http://schemas.microsoft.com/project"}


@pytest.fixture
def crono_caixa(con, caixa_6x4):
    from lsf.geradores.estrutura import derivar_quantitativos
    from lsf.motores.fundacao import derivar_fundacao

    pid, _ = caixa_6x4
    con.execute(
        "UPDATE projeto SET classe_solo_id ="
        " (SELECT id FROM classe_solo WHERE classe='S3') WHERE id = ?", (pid,))
    con.commit()
    derivar_quantitativos(con, pid)
    derivar_fundacao(con, pid)
    return cronograma_projeto(con, pid)


def test_mspdi_reparseado_bate_com_o_cpm(crono_caixa):
    """FUNDACAO [0,1] e ESTRUTURA [4,7] com início em 2026-08-03:
    Start/Finish = início + ES/EF dias corridos; vínculo TI vira Type=1."""
    inicio = datetime.date(2026, 8, 3)
    xml = exportar_mspdi(crono_caixa, inicio)
    raiz = ET.fromstring(xml)

    tarefas = {t.findtext("p:Name", namespaces=NS): t
               for t in raiz.findall(".//p:Task", NS)}
    fundacao = tarefas["Fundação"]
    estrutura = tarefas["Estrutura LSF"]

    assert fundacao.findtext("p:Start", namespaces=NS).startswith("2026-08-03")
    assert fundacao.findtext("p:Finish", namespaces=NS).startswith("2026-08-04")
    assert estrutura.findtext("p:Start", namespaces=NS).startswith("2026-08-07")
    assert estrutura.findtext("p:Finish", namespaces=NS).startswith("2026-08-10")

    vinculo = estrutura.find("p:PredecessorLink", NS)
    assert vinculo is not None
    uid_fundacao = fundacao.findtext("p:UID", namespaces=NS)
    assert vinculo.findtext("p:PredecessorUID", namespaces=NS) == uid_fundacao
    assert vinculo.findtext("p:Type", namespaces=NS) == "1"      # TI = FS

    # duração em horas de jornada: 3 dias × 8h
    assert estrutura.findtext("p:Duration", namespaces=NS) == "PT24H0M0S"


def test_mspdi_marca_criticas_e_hammock_fora_dos_vinculos(crono_caixa):
    xml = exportar_mspdi(crono_caixa, datetime.date(2026, 8, 3))
    raiz = ET.fromstring(xml)
    criticas = [t.findtext("p:Name", namespaces=NS)
                for t in raiz.findall(".//p:Task", NS)
                if t.findtext("p:Critical", namespaces=NS) == "1"]
    assert "Fundação" in criticas and "Estrutura LSF" in criticas
