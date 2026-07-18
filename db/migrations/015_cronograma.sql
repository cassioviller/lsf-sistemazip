-- Migração 015 — Cronograma (Fase 4): a rede de precedências LSF e as equipes
-- são DADO, não código. Motivo: é conhecimento de obra que muda com calibração
-- (R6) e por projeto no futuro; o motor CPM só executa o que está aqui.
--
-- Tipos de vínculo (contrato do stub do motor 2):
--   TI (término→início, o FS clássico) · II (início→início) · TT (término→término)
-- sempre com lag em dias corridos.
--
-- `hammock`: atividade que não entra no CPM — acompanha o projeto inteiro
-- (GERENCIAMENTO: canteiro, administração). Duração = makespan, custo diluído.

CREATE TABLE precedencia_macroetapa (
  id INTEGER PRIMARY KEY,
  grupo_pred TEXT NOT NULL,
  grupo_succ TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('TI','II','TT')),
  lag_dias REAL NOT NULL DEFAULT 0 CHECK (lag_dias >= 0),
  origem TEXT NOT NULL,                -- de onde veio o vínculo (anotado, D4)
  UNIQUE (grupo_pred, grupo_succ, tipo),
  CHECK (grupo_pred <> grupo_succ)
);

CREATE TABLE equipe_macroetapa (
  grupo_eap TEXT PRIMARY KEY,
  trabalhadores REAL NOT NULL CHECK (trabalhadores > 0),
  hammock INTEGER NOT NULL DEFAULT 0 CHECK (hammock IN (0,1)),
  origem TEXT NOT NULL
);
