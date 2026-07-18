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
