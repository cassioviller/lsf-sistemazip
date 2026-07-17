"""MOTOR 3 — takedown de cargas por parede real (Fase 2, item 3).

Generaliza o spike 4, que tinha três coisas chumbadas no script: a lista de
camadas da parede, a área tributária (trib=2,0 m) e o empilhamento de pavimentos.
Aqui as camadas vêm da `camada_parede` (migração 013) e a tributária sai da
GEOMETRIA: cada viga de laje entrega metade da sua carga em cada apoio, e o apoio
é a parede que contém a ponta da viga.

O que o motor NÃO resolve, e por isso avisa: a laje do gerador vence o polígono
inteiro (o `scan` corta no contorno externo, não nas paredes internas), então a
carga da laje cai toda nas paredes EXTERNAS. É o mesmo buraco do `vao_ef =
max_span/2`: o apoio do meio (a viga laminada 1VG da obra) não está modelado.
"""
import pytest


def test_peso_proprio_da_parede_sai_das_camadas_do_banco(projeto_109_estrutura):
    """Externa: perfis+OSB+cimentícia+gesso+lã+membrana = 41,4 kg/m² — o "~41 kg/m²
    de parede típica" que o CLAUDE.md cita como física do LSF."""
    from lsf.motores.cargas import peso_parede_kn_m2

    con, _ = projeto_109_estrutura
    ext, conf = peso_parede_kn_m2(con, externa=True)
    # 9.0+6.8+14.5+9.5+1.4+0.2 = 41.4 kg/m² → ×9.81/1000
    assert ext == pytest.approx(41.4 * 9.81 / 1000, rel=1e-3)
    assert conf in ("estimado", "parametrico")


def test_parede_interna_leva_gesso_nas_duas_faces(projeto_109_estrutura):
    """Divisória não tem cimentícia nem membrana, mas tem gesso dos dois lados —
    `faces=2` na camada_parede. Sem isso a interna sairia leve demais."""
    from lsf.motores.cargas import peso_parede_kn_m2

    con, _ = projeto_109_estrutura
    interna, _ = peso_parede_kn_m2(con, externa=False)
    # 9.0 + 2*9.5 + 1.4 = 29.4 kg/m²
    assert interna == pytest.approx(29.4 * 9.81 / 1000, rel=1e-3)
    ext, _ = peso_parede_kn_m2(con, externa=True)
    assert interna < ext


def test_camada_ausente_e_erro_nao_parede_de_peso_zero(projeto_109_estrutura):
    """D4.1: sem camadas cadastradas a parede não pesa zero — isso viraria uma
    fundação subdimensionada, calada."""
    from lsf.motores.cargas import DadoIndisponivel, peso_parede_kn_m2

    con, _ = projeto_109_estrutura
    con.execute("DELETE FROM camada_parede WHERE tipo = 'externa'")
    with pytest.raises(DadoIndisponivel):
        peso_parede_kn_m2(con, externa=True)


def test_takedown_da_109_por_parede(projeto_109_estrutura):
    """Cada parede portante recebe uma carga linear; o térreo carrega mais que a
    cobertura porque acumula os pavimentos de cima (é o que 'takedown' quer dizer)."""
    from lsf.motores.cargas import takedown_por_parede

    con, pid = projeto_109_estrutura
    cargas = takedown_por_parede(con, pid)
    assert cargas

    por_nivel = {}
    for c in cargas:
        por_nivel.setdefault(c.nivel_indice, []).append(c.total_kn_m)
    assert set(por_nivel) == {0, 1, 2}

    # o térreo acumula: a maior carga do térreo > a maior do último pavimento
    assert max(por_nivel[0]) > max(por_nivel[2])
    assert all(v > 0 for vs in por_nivel.values() for v in vs)


def test_carga_da_parede_externa_no_terreo_esta_na_ordem_do_lsf(projeto_109_estrutura):
    """CLAUDE.md: "carga ~5 kN/m no térreo" para LSF; o spike 4 achou 3..25 kN/m.
    Se isto explodir (100 kN/m), a tributária ou o empilhamento quebraram — e a
    fundação sai errada sem avisar."""
    from lsf.motores.cargas import takedown_por_parede

    con, pid = projeto_109_estrutura
    ext = [c for c in takedown_por_parede(con, pid)
           if c.nivel_indice == 0 and c.externa]
    assert ext
    for c in ext:
        assert 1.0 < c.total_kn_m < 60.0, (
            f"parede {c.parede_id}: {c.total_kn_m:.1f} kN/m fora da ordem do LSF")


def test_parede_interna_fica_so_com_o_peso_proprio_e_isso_e_a_pendencia(
        projeto_109_estrutura):
    """A verdade desconfortável do modelo, travada em teste para não ser esquecida:
    a laje vence o polígono inteiro, então NADA da laje chega às paredes internas —
    uma portante interna de 7 m num prédio de 3 pavimentos fica com ~0,9 kN/m, só o
    peso próprio dela. Contra a segurança.

    Não "conserto" afrouxando o intervalo: o número está errado por falta do apoio
    do meio (a 1VG da obra), e quem tem que gritar é a pendência. Este teste cai no
    dia em que o apoio real for modelado — e aí é notícia boa."""
    from lsf.motores.cargas import pendencias_do_takedown, takedown_por_parede

    con, pid = projeto_109_estrutura
    cargas = takedown_por_parede(con, pid)
    internas = [c for c in cargas if c.nivel_indice == 0 and not c.externa]
    assert internas

    sem_laje = [c for c in internas if c.g_laje_kn_m == 0 and c.q_laje_kn_m == 0]
    assert sem_laje, "se a laje passou a carregar as internas, remodele este teste"
    assert all(c.total_kn_m == pytest.approx(c.g_propria_kn_m + c.de_cima_kn_m)
               for c in sem_laje)
    assert pendencias_do_takedown(con, pid, cargas), (
        "parede interna sem carga de laje TEM que gerar pendência")


def test_viga_dupla_nao_dobra_a_carga_da_laje(projeto_109_estrutura):
    """A 2ª viga do par dá CAPACIDADE ao mesmo vão — não carrega outra faixa de
    laje. Contá-la inflava a tributária para 10,9 m num prédio de 15,8 m de
    largura (meio-vão máximo 7,9 m): carga impossível, e a favor de ninguém.

    Mesma armadilha da cantoneira DX-06: peça duplicada por resistência não é
    peça duplicada por área."""
    from lsf.motores.cargas import takedown_por_parede

    con, pid = projeto_109_estrutura
    q_uso = con.execute(
        "SELECT valor FROM regra_lsf WHERE chave = 'carga_sc'").fetchone()[0]
    ext = [c for c in takedown_por_parede(con, pid)
           if c.nivel_indice == 0 and c.externa and c.q_laje_kn_m > 0]
    assert ext
    for c in ext:
        tributaria = c.q_laje_kn_m / q_uso
        assert tributaria <= 7.9 + 0.5, (
            f"parede {c.parede_id}: tributária de {tributaria:.1f} m — maior que o"
            " meio-vão do prédio (15,8/2). Alguma peça está sendo contada duas vezes")


def test_takedown_escala_pelo_comprimento_da_parede(projeto_109_estrutura):
    """A carga da parede de cima é kN/m DELA. Somar direto faria uma parede de 3 m
    entregar seu kN/m inteiro numa de 10 m embaixo — carga inventada do nada.
    Converte para kN e redistribui: total_acima × comp_acima / comp_abaixo."""
    from lsf.motores.cargas import takedown_por_parede

    con, pid = projeto_109_estrutura
    cargas = takedown_por_parede(con, pid)
    por_nivel = {}
    for c in cargas:
        por_nivel.setdefault(c.nivel_indice, []).append(c)

    # o que desce do nível de cima, em kN, não pode ser maior que o que existe lá
    for nivel in (1, 2):
        acima_kn = sum(c.total_kn_m * c.comp_m for c in por_nivel.get(nivel, []))
        desce_kn = sum(c.de_cima_kn_m * c.comp_m for c in por_nivel[nivel - 1])
        assert desce_kn <= acima_kn + 1e-6, (
            f"nível {nivel-1} recebeu {desce_kn:.0f} kN de cima, mas o nível"
            f" {nivel} inteiro só tem {acima_kn:.0f} kN — o takedown criou carga")


def test_parede_de_cima_desce_por_trecho_nao_por_ponto_medio(projeto_109_estrutura):
    """Casar a parede de cima com a de baixo pelo PONTO MÉDIO entregava a carga
    inteira a cada parede que o médio tocasse. Na 109 isso era real e não teórico:
    a parede 37 do nível 2 é vertical em x=2,74 (z 4,60→18,50, médio z=11,55), e a
    interna 25 do nível 1 COMEÇA em (2,74; 11,60) — 0,05 m do médio, exatamente a
    tolerância. Uma perpendicular que só encosta em T levava os 13,90 m de carga
    outra vez (174 kN descendo de um nível que só tem 154 kN).

    Parede é carga LINEAR: quem está sob um trecho recebe o kN daquele trecho. Uma
    perpendicular se sobrepõe em 0 m, logo não recebe nada."""
    from lsf.motores.cargas import _sobreposicao_m

    # a colinear idêntica recebe o comprimento inteiro
    vertical = {"ax": 2.74, "az": 4.60, "bx": 2.74, "bz": 18.50}
    assert _sobreposicao_m(vertical, dict(vertical)) == pytest.approx(13.90)

    # a perpendicular que encosta em T no meio dela não é apoio de trecho nenhum
    em_t = {"ax": 2.74, "az": 11.60, "bx": 7.10, "bz": 11.60}
    assert _sobreposicao_m(vertical, em_t) == 0.0

    # colinear parcial: só o trecho comum
    metade = {"ax": 2.74, "az": 4.60, "bx": 2.74, "bz": 11.60}
    assert _sobreposicao_m(vertical, metade) == pytest.approx(7.00)


def test_parede_sem_apoio_embaixo_vira_orfa_e_nao_evapora(projeto_109_estrutura):
    """As plantas dos níveis da 109 são DIFERENTES (internas do térreo em x=9,60/
    5,90/8,30; as do nível 1 em 7,10/10,40/11,60): a parede de cima apoia na laje,
    que devolve a carga por um caminho que o modelo não tem. Essa carga não pode
    sair da conta calada — o térreo sairia leve e a fundação, subdimensionada."""
    from lsf.motores.cargas import pendencias_do_takedown, takedown_por_parede

    con, pid = projeto_109_estrutura
    r = takedown_por_parede(con, pid, com_resumo=True)
    assert r.orfa_takedown_kn > 0

    por_nivel = {}
    for c in r.cargas:
        por_nivel.setdefault(c.nivel_indice, []).append(c)
    # o que sobe + o que desce + o que ficou órfão fecha, nível a nível
    for nivel in (1, 2):
        acima = sum(c.total_kn_m * c.comp_m for c in por_nivel[nivel])
        desce = sum(c.de_cima_kn_m * c.comp_m for c in por_nivel[nivel - 1])
        assert desce <= acima + 1e-6

    pend = pendencias_do_takedown(con, pid)
    assert any("laje" in p.lower() and "portante" in p.lower() for p in pend)


def test_confianca_nunca_melhor_que_a_das_camadas(projeto_109_estrutura):
    """D4: os pesos de camada são `estimado`/`parametrico` (sem calibração) — a
    carga derivada não pode sair `real` por a geometria ser `real`."""
    from lsf.motores.cargas import takedown_por_parede

    con, pid = projeto_109_estrutura
    for c in takedown_por_parede(con, pid):
        assert c.confianca in ("estimado", "parametrico")


def test_apoio_do_meio_nao_modelado_vira_pendencia(projeto_109_estrutura):
    """A laje vence o polígono inteiro e descarrega tudo nas paredes externas: a
    1VG da obra não está no modelo. Isso NÃO pode passar calado — a carga das
    externas sai alta e a das internas, baixa."""
    from lsf.motores.cargas import takedown_por_parede, pendencias_do_takedown

    con, pid = projeto_109_estrutura
    cargas = takedown_por_parede(con, pid)
    pend = pendencias_do_takedown(con, pid, cargas)
    assert any("apoio" in p.lower() or "1vg" in p.lower() for p in pend)
