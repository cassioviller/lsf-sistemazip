-- ============================================================
-- 001 — Tabelas de projeto (instância) · Fase 1
-- Modelo: docs/01 §4. Decisões: D1 (EAP única), D2 (quantitativo é o ponto de
-- convergência; modos diferem só na `origem`), D4 (confiança em todo derivado),
-- D5 (projeto trava data-base).
-- ============================================================
PRAGMA foreign_keys = ON;

-- ---------- EAP (base de conhecimento; espinha dorsal de orçamento E cronograma) ----------
-- Necessária aqui porque `quantitativo` referencia item de EAP, e o contrato da Fase 1
-- pede agregação "por hierarquia da EAP". Agrupador não tem composição; folha tem.
CREATE TABLE eap_item (
  id INTEGER PRIMARY KEY,
  codigo TEXT NOT NULL UNIQUE,          -- '03', '03.01', '03.01.02'
  pai_id INTEGER REFERENCES eap_item(id),
  descricao TEXT NOT NULL,
  unidade TEXT,                         -- NULL em agrupador
  grupo_eap TEXT NOT NULL CHECK (grupo_eap IN
    ('PRELIM','FUNDACAO','ESTRUTURA','FECHAMENTO','INSTALACOES','ACABAMENTO','COMPLEMENTO','GERENCIAMENTO')),
  composicao_id INTEGER REFERENCES composicao(id),
  -- folha = tem composição e unidade; agrupador = nenhum dos dois
  CHECK ((composicao_id IS NULL AND unidade IS NULL) OR (composicao_id IS NOT NULL AND unidade IS NOT NULL)),
  CHECK (pai_id IS NULL OR pai_id <> id)
);
CREATE INDEX ix_eap_item_pai ON eap_item (pai_id);

-- ---------- PROJETO (D5: trava a REFERÊNCIA; orçamento antigo nunca muda sozinho) ----------
-- Trava referência+uf+desonerado, não `data_base_id`: cada insumo é precificado na data-base
-- da sua própria fonte naquela referência. É o que permite composição própria (D7) misturar
-- material VEKS com mão de obra SINAPI, que vivem em data-bases distintas.
CREATE TABLE projeto (
  id INTEGER PRIMARY KEY,
  codigo TEXT NOT NULL UNIQUE,          -- '109.1506'
  nome TEXT NOT NULL,
  cliente TEXT,
  referencia TEXT NOT NULL,             -- 'YYYY-MM'
  uf TEXT,
  desonerado INTEGER NOT NULL DEFAULT 0 CHECK (desonerado IN (0,1)),
  classe_solo_id INTEGER REFERENCES classe_solo(id),
  sondagem_pendente INTEGER NOT NULL DEFAULT 1 CHECK (sondagem_pendente IN (0,1)),  -- R3
  criado_em TEXT NOT NULL DEFAULT (datetime('now')),
  observacao TEXT
);

-- ---------- QUANTITATIVO (D2: paramétrico e executivo diferem só na `origem`) ----------
CREATE TABLE quantitativo (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  eap_item_id INTEGER NOT NULL REFERENCES eap_item(id),
  quantidade REAL NOT NULL CHECK (quantidade >= 0),
  origem TEXT NOT NULL CHECK (origem IN ('PARAMETRICO','TAKEOFF','MANUAL')),
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  origem_regra TEXT,                    -- proveniência da regra que derivou a quantidade
  criado_em TEXT NOT NULL DEFAULT (datetime('now')),
  -- uma linha ativa por item; a migração PARAMETRICO->TAKEOFF (D2) substitui a linha
  UNIQUE (projeto_id, eap_item_id)
);
CREATE INDEX ix_quantitativo_projeto ON quantitativo (projeto_id);

-- Quantitativo só se pendura em folha da EAP (agrupador recebe soma, não quantidade).
CREATE TRIGGER trg_quantitativo_so_em_folha
BEFORE INSERT ON quantitativo
FOR EACH ROW
WHEN (SELECT composicao_id FROM eap_item WHERE id = NEW.eap_item_id) IS NULL
BEGIN
  SELECT RAISE(ABORT, 'quantitativo só pode apontar para folha da EAP (item com composição)');
END;

-- ---------- Esqueleto da EAP: as 8 macroetapas turn-key (gate R7 conta sobre elas) ----------
-- Puramente estrutural (não depende de nenhuma linha do seed) — por isso mora na
-- migração. As folhas com composicao_id (03.01, 04.01...) dependem de `composicao`,
-- que é conhecimento declarativo do seed.sql; portanto vivem lá, não aqui (ver
-- "Modelo mental" no build_db.py: migração é estrutura, seed é conhecimento, e o
-- seed roda DEPOIS das migrações em todo build).
INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap, composicao_id) VALUES
 ('01', NULL, 'Serviços preliminares',      NULL, 'PRELIM',        NULL),
 ('02', NULL, 'Fundação',                   NULL, 'FUNDACAO',      NULL),
 ('03', NULL, 'Estrutura LSF',              NULL, 'ESTRUTURA',     NULL),
 ('04', NULL, 'Fechamentos',                NULL, 'FECHAMENTO',    NULL),
 ('05', NULL, 'Instalações',                NULL, 'INSTALACOES',   NULL),
 ('06', NULL, 'Acabamentos',                NULL, 'ACABAMENTO',    NULL),
 ('07', NULL, 'Serviços complementares',    NULL, 'COMPLEMENTO',   NULL),
 ('08', NULL, 'Gerenciamento e canteiro',   NULL, 'GERENCIAMENTO', NULL);
