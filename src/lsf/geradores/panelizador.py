"""Panelizador (Fase 5) — evolução do spike 5 sobre o gerador real.

As JUNTAS já são decididas pelo gerador (`_panelizar`: junta nunca a <30 cm da
lateral de um vão, largura máx. de painel por transporte); aqui elas viram
PAINÉIS nomeados no padrão do caderno da obra (1PV-P01, 2PV-P03...), com as
peças da parede atribuídas por posição. Peça que cruza a junta pertence ao
painel onde COMEÇA (menor x) — as guias já nascem segmentadas por painel no
gerador, então o caso relevante são diagonais e vergas de borda.

O invariante do módulo, travado em teste: Σ peças (e kg) dos painéis é IGUAL ao
da parede. Painel que perdesse peça viraria kit de corte incompleto na fábrica
— o pior defeito possível de um romaneio.
"""
from __future__ import annotations

from dataclasses import dataclass

from lsf.geradores.estrutura import EstruturaParede, Peca


@dataclass(frozen=True)
class Painel:
    id: str                    # '1PV-P01' — nível+1 como o v7
    parede_id: int
    x_ini: float
    x_fim: float
    pecas: list[Peca]
    kg: float                  # aproximado por massa média do perfil na parede


def panelizar_parede(estrutura: EstruturaParede, nivel_indice: int,
                     seq_inicial: int = 1) -> list[Painel]:
    limites = [0.0, *estrutura.juntas, float("inf")]
    massa_media = {
        perfil: kg / max(sum(p.comp for p in estrutura.pecas
                             if p.perfil == perfil), 1e-9)
        for perfil, kg in estrutura.kg_por_perfil.items()}

    paineis: list[Painel] = []
    for i in range(len(limites) - 1):
        x_ini, x_fim = limites[i], limites[i + 1]
        # partição de [0, comp): peça na junta exata pertence ao painel SEGUINTE
        # (>= x_ini) — cada peça cai em exatamente um intervalo
        pecas = [p for p in estrutura.pecas
                 if x_ini - 1e-6 <= min(p.x0, p.x1) < x_fim - 1e-6]
        kg = sum(p.comp * massa_media.get(p.perfil, 0.0) for p in pecas)
        paineis.append(Painel(
            id=f"{nivel_indice + 1}PV-P{seq_inicial + i:02d}",
            parede_id=estrutura.parede_id,
            x_ini=x_ini, x_fim=x_fim if x_fim != float("inf") else round(
                max((max(p.x0, p.x1) for p in estrutura.pecas), default=x_ini), 4),
            pecas=pecas, kg=round(kg, 2)))
    return paineis


@dataclass(frozen=True)
class PainelRomaneio:
    painel: Painel
    nivel_indice: int
    parede_id: int
    kits: list                 # PlanoCortePerfil por perfil (barras 6 m)


@dataclass(frozen=True)
class Romaneio:
    projeto_id: int
    paineis: list[PainelRomaneio]
    kg_total: float


def romaneio_projeto(con, projeto_id: int) -> Romaneio:
    """Romaneio fábrica/obra: todos os painéis de parede do projeto, na ordem de
    montagem (nível, parede), cada um com o kit de corte por perfil (first-fit
    em barras de 6 m — o mesmo `plano_de_corte` do aceite de kg).

    Só PAREDES viram painéis; laje/escada/cobertura/forro são sistemas montados
    in loco e saem no plano de corte geral do `gerar_estrutura`, não aqui."""
    from lsf.geradores.estrutura import (_regra, _regras, gerar_estrutura,
                                         plano_de_corte)

    est = gerar_estrutura(con, projeto_id)
    barra = _regra(_regras(con), "barra_m")
    nivel_de = dict(con.execute(
        "SELECT p.id, n.indice FROM parede p JOIN nivel n ON n.id = p.nivel_id"
        " WHERE n.projeto_id = ?", (projeto_id,)).fetchall())

    paineis: list[PainelRomaneio] = []
    seq_por_nivel: dict[int, int] = {}
    for ep in est.paredes:
        nivel = nivel_de[ep.parede_id]
        seq = seq_por_nivel.get(nivel, 1)
        for painel in panelizar_parede(ep, nivel, seq):
            paineis.append(PainelRomaneio(
                painel=painel, nivel_indice=nivel, parede_id=ep.parede_id,
                kits=plano_de_corte(con, painel.pecas, barra)))
        seq_por_nivel[nivel] = seq + len(ep.juntas) + 1

    paineis.sort(key=lambda p: (p.nivel_indice, p.painel.id))
    return Romaneio(projeto_id=projeto_id, paineis=paineis,
                    kg_total=round(sum(p.painel.kg for p in paineis), 1))
