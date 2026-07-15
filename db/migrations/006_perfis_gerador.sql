-- ============================================================
-- 006 — Conhecimento do gerador de estrutura (F2.1)
-- Spec: docs/superpowers/specs/2026-07-15-gerador-estrutura-paredes-design.md
-- perfil_lsf ganha tipo 'laminado' (W310/HSS de laje/cobertura, do
-- Object.assign linha 645 do v7). SQLite não altera CHECK: rebuild.
-- ============================================================
PRAGMA foreign_keys = OFF;

CREATE TABLE perfil_lsf_novo (
  codigo TEXT PRIMARY KEY,
  familia TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('montante','guia','laminado')),
  drywall INTEGER NOT NULL DEFAULT 0,
  alma_mm REAL NOT NULL, aba_mm REAL NOT NULL,
  enrijecedor_mm REAL, espessura_mm REAL NOT NULL,
  massa_kg_m REAL NOT NULL,
  fonte TEXT NOT NULL DEFAULT 'LSF_DB v7 (obra ref. 484125)'
);
INSERT INTO perfil_lsf_novo SELECT * FROM perfil_lsf;
DROP TABLE perfil_lsf;
ALTER TABLE perfil_lsf_novo RENAME TO perfil_lsf;

PRAGMA foreign_keys = ON;

-- Correspondência montante→guia (DB.guiaDe do v7, linha 163)
CREATE TABLE guia_de (
  familia_montante TEXT PRIMARY KEY,
  familia_guia TEXT NOT NULL
);

-- Escalonamento de verga por vão (DB.regras.vergaPorVao do v7)
-- NULL = mesmo perfil da parede (faixa leve)
CREATE TABLE verga_escalonamento (
  faixa_ate_m REAL PRIMARY KEY,
  perfil_montante TEXT,
  perfil_guia TEXT,
  origem TEXT NOT NULL
);
