import pytest
from lsf.geradores.estrutura import dimensionar_viga, DadoIndisponivel

# Limiares JÁ VERIFICADOS reproduzindo a aritmética exata de v7:636-642 com as
# constantes do seed (SEC_Ue250 A=708/Wx=46300/Ix=5.78e6; CARGAS sc=4.0/g=1.3/
# fy=230/gM=1.10/E=2.0e5/flecha=350) a trib=0,40 m:
#   simples até 4,88 m · dupla 4,89–6,15 m · laminada ≥ 6,16 m.
# Por isso vao 2.0 → simples, 5.0 → dupla, 8.0 → laminada. Se a implementação
# der outro modo nesses vãos, a aritmética/unidade do port divergiu do v7.
#
# O PERFIL agora é explícito. O v7 verificava tudo com a seção do Ue250, inclusive
# lajes de Ue200; hoje a seção sai da geometria do perfil informado (método linear,
# NBR 14762), e o Ue250 continua reproduzindo estes mesmos limiares.
UE250 = "Ue250#2.00"


def test_vao_curto_viga_simples(con):
    r = dimensionar_viga(con, vao_m=2.0, trib_m=0.40, perfil=UE250)
    assert r["modo"] == "simples"
    assert r["M"] <= r["MRd"] and r["delta"] <= r["dLim"]

def test_vao_medio_exige_viga_dupla(con):
    r = dimensionar_viga(con, vao_m=5.0, trib_m=0.40, perfil=UE250)
    assert r["modo"] == "dupla"

def test_vao_grande_exige_laminada(con):
    r = dimensionar_viga(con, vao_m=8.0, trib_m=0.40, perfil=UE250)
    assert r["modo"] == "laminada"

def test_carga_ausente_e_erro(con):
    con.execute("DELETE FROM regra_lsf WHERE chave='carga_sc'")
    with pytest.raises(DadoIndisponivel):
        dimensionar_viga(con, vao_m=2.0, trib_m=0.40, perfil=UE250)


def test_ue200_reprova_antes_do_ue250_no_mesmo_vao(con):
    """O bug que a assinatura antiga escondia: a 4,0 m o Ue250 passa simples, mas
    o Ue200 (Wx = 45% do Ue250) não — e o v7 aprovava os dois com a seção do 250."""
    assert dimensionar_viga(con, vao_m=4.0, trib_m=0.40, perfil=UE250)["modo"] == "simples"
    assert dimensionar_viga(con, vao_m=4.0, trib_m=0.40,
                            perfil="Ue200#1.25")["modo"] != "simples"
