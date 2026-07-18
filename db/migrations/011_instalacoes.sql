-- Migração 011 — instalações (Fase 2): pontos hidráulicos/gás/elétrica e furos
-- críticos em viga. É input de PROJETO, como o solo: o arquitetônico não dá a
-- contagem de pontos, e ela governa furo de serviço, chapa de reforço e tubo-luva.
--
-- Sem esta tabela o gerador não emitia 4 acessórios que o v7 orça (furo de
-- serviço, chapa de reforço, parafusos das chapas, tubo-luva GLP) — item que
-- falta em preço fechado é escopo vazado (CLAUDE.md), não arredondamento.
--
-- `furo_critico` é o furo que passa do limite da REGRA HID-FURO-001/003 (12 cm ou
-- h/3, na zona de tração): cada um vira chapa de reforço + alerta ALTO. Furo em
-- viga é decisão estrutural, então nasce marcado, não silencioso.

CREATE TABLE instalacao (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  pontos_hidro INTEGER NOT NULL DEFAULT 0 CHECK (pontos_hidro >= 0),
  pontos_gas INTEGER NOT NULL DEFAULT 0 CHECK (pontos_gas >= 0),
  pontos_ele INTEGER NOT NULL DEFAULT 0 CHECK (pontos_ele >= 0),
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id)
);

CREATE TABLE furo_critico (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  onde_sistema TEXT NOT NULL,          -- 'laje', 'parede'...
  grupo TEXT NOT NULL,                 -- 1LJ, 2LJ...
  h_m REAL NOT NULL CHECK (h_m > 0),   -- altura da viga furada (entra no h/3)
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico'))
);
