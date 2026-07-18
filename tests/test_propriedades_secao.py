"""`propriedades_secao`: A/Ix/Wx do perfil pela geometria (método linear, NBR 14762).

O v7 tinha as propriedades do Ue250 chumbadas (SEC_Ue250, v7:634) e verificava
TODA laje com elas, mesmo quando o escalonamento escolhia Ue200. Estes testes
travam o método linear contra aqueles mesmos valores — é o que autoriza calcular
em vez de chumbar — e travam a consequência: Ue200 não pode ser verificado com a
seção do Ue250.
"""
import pytest


def test_metodo_linear_reproduz_a_secao_ue250_do_v7(con):
    """Validação do método: os três valores seedados do v7 (A=708 mm²,
    Ix=5,78e6 mm⁴, Wx=46,3e3 mm³) têm que sair da geometria do perfil_lsf."""
    from lsf.geradores.estrutura import _regras, propriedades_secao

    s = propriedades_secao(con, "Ue250#2.00")
    R = _regras(con)
    assert s["A"] == pytest.approx(R["sec_ue250_a"], rel=0.005)
    assert s["Ix"] == pytest.approx(R["sec_ue250_ix"], rel=0.005)
    assert s["Wx"] == pytest.approx(R["sec_ue250_wx"], rel=0.005)


def test_ue200_tem_seção_muito_menor_que_ue250(con):
    """A razão que torna o bug grave: verificar Ue200 com a seção do Ue250
    superestima o momento resistente em ~2,2x."""
    from lsf.geradores.estrutura import propriedades_secao

    u200 = propriedades_secao(con, "Ue200#1.25")
    u250 = propriedades_secao(con, "Ue250#2.00")
    assert u200["Wx"] < 0.5 * u250["Wx"]


def test_secao_de_perfil_inexistente_e_erro(con):
    """D4.1: perfil sem geometria no banco não vira seção default."""
    from lsf.geradores.estrutura import DadoIndisponivel, propriedades_secao

    with pytest.raises(DadoIndisponivel):
        propriedades_secao(con, "Ue999#9.99")


def test_dimensionar_viga_usa_a_secao_do_perfil_informado(con):
    """O mesmo vão/tributária tem que reprovar mais cedo no perfil mais fraco.
    Antes, os dois davam o mesmo resultado (ambos liam sec_ue250_*)."""
    from lsf.geradores.estrutura import dimensionar_viga

    forte = dimensionar_viga(con, 4.0, 0.4, "Ue250#2.00")
    fraco = dimensionar_viga(con, 4.0, 0.4, "Ue200#1.25")
    assert fraco["MRd"] < forte["MRd"]
    assert fraco["VRd"] < forte["VRd"]  # VRd ~ t³/h, não mais fixo em t=2/h=250


def test_dimensionar_viga_exige_o_perfil(con):
    """Sem perfil não há verificação: a assinatura antiga escondia o Ue250."""
    from lsf.geradores.estrutura import dimensionar_viga

    with pytest.raises(TypeError):
        dimensionar_viga(con, 4.0, 0.4)
