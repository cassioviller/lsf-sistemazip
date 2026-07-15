"""Migração 006: conhecimento do gerador de estrutura (perfis pós-override do v7)."""


def test_perfis_corrigidos_pos_override(con):
    """O seed portou valores PRÉ-Object.assign do v7 (linha 645); agora tem que bater
    com o v7 PÓS-override — é com esses kg/m que o aceite fecha."""
    linhas = {c: (a, e, m) for c, a, e, m in con.execute(
        "SELECT codigo, aba_mm, enrijecedor_mm, massa_kg_m FROM perfil_lsf")}
    assert linhas["Ue70#0.80"] == (35, 10, 1.00)
    assert linhas["U72#0.80"] == (34, None, 0.90)


def test_perfis_novos_existem(con):
    codigos = {c for (c,) in con.execute("SELECT codigo FROM perfil_lsf")}
    assert {"U202#0.95", "U252#1.25", "Ue140#0.80", "U142#0.80",
            "W310x32.7", "HSS100x100x4.8"} <= codigos


def test_laminado_e_tipo_valido(con):
    tipo = con.execute(
        "SELECT tipo FROM perfil_lsf WHERE codigo='W310x32.7'").fetchone()[0]
    assert tipo == "laminado"


def test_guia_de_completo(con):
    mapa = dict(con.execute("SELECT familia_montante, familia_guia FROM guia_de"))
    assert mapa == {"Ue70": "U72", "Ue90": "U92", "Ue140": "U142",
                    "Ue200": "U202", "Ue250": "U252",
                    "M48": "G48", "M70": "G70", "M90": "G90"}


def test_verga_escalonamento(con):
    faixas = con.execute(
        "SELECT faixa_ate_m, perfil_montante, perfil_guia FROM verga_escalonamento"
        " ORDER BY faixa_ate_m").fetchall()
    assert [tuple(f) for f in faixas] == [
        (1.2, None, None),
        (2.0, "Ue140#1.25", "U142#1.25"),
        (9.9, "Ue250#2.00", "U252#2.00"),
    ]


def test_regras_do_gerador_presentes(con):
    chaves = {c for (c,) in con.execute("SELECT chave FROM regra_lsf")}
    assert {"modulacao_lsf_m", "barra_m", "king_duplo_lim_m", "jack_duplo_lim_m",
            "apoio_verga_m", "passo_hb_m", "peitoril_padrao_m", "passo_trelica_m",
            "colunas_trelica_se_m", "diag_sobre_verga_min_m", "alt_min_porta_giro_m",
            "alt_min_porta_correr_m", "margem_abertura_m", "folga_entre_aberturas_m",
            "passo_conex_painel_m", "ancor_esp_padrao_m"} <= chaves
    valores = dict(con.execute("SELECT chave, valor FROM regra_lsf"))
    assert valores["modulacao_lsf_m"] == 0.40
    assert valores["barra_m"] == 6.0
