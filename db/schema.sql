-- ============================================================
-- BASE DE CONHECIMENTO — Sistema Orçamento/Cronograma LSF Veks
-- schema.sql · v0.1 · Fase 0
-- Princípios: multi-fonte (D7), versionado por data-base (D5),
-- confiança em todo dado derivado ou estimado (D4)
-- ============================================================
PRAGMA foreign_keys = ON;

-- ---------- FONTES E DATA-BASES ----------
CREATE TABLE fonte (
  id INTEGER PRIMARY KEY,
  sigla TEXT NOT NULL UNIQUE,          -- SINAPI, CDHU, ORSE, PROPRIA...
  nome TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('OFICIAL','PRIVADA','FABRICANTE','NORMATIVA','PROPRIA')),
  papel TEXT NOT NULL CHECK (papel IN ('PRECO','COEFICIENTE','AMBOS')),
  abrangencia TEXT,                    -- BR, SP, SE...
  url TEXT
);

CREATE TABLE data_base (
  id INTEGER PRIMARY KEY,
  fonte_id INTEGER NOT NULL REFERENCES fonte(id),
  referencia TEXT NOT NULL,            -- 'YYYY-MM'
  uf TEXT,
  desonerado INTEGER NOT NULL DEFAULT 0,
  publicado_em TEXT,
  UNIQUE (fonte_id, referencia, uf, desonerado)
);

-- ---------- INSUMOS (identidade separada do preço) ----------
CREATE TABLE insumo (
  id INTEGER PRIMARY KEY,
  fonte_id INTEGER NOT NULL REFERENCES fonte(id),
  codigo_fonte TEXT NOT NULL,          -- código na fonte de origem
  descricao TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('MAT','MO','EQP')),
  unidade TEXT NOT NULL,
  UNIQUE (fonte_id, codigo_fonte)
);

CREATE TABLE insumo_preco (
  id INTEGER PRIMARY KEY,
  insumo_id INTEGER NOT NULL REFERENCES insumo(id),
  data_base_id INTEGER NOT NULL REFERENCES data_base(id),
  preco REAL NOT NULL,
  confianca TEXT NOT NULL DEFAULT 'real' CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (insumo_id, data_base_id)
);

-- mesmo material em fontes diferentes (troca de base sem retrabalho)
CREATE TABLE insumo_equivalencia (
  insumo_id_a INTEGER NOT NULL REFERENCES insumo(id),
  insumo_id_b INTEGER NOT NULL REFERENCES insumo(id),
  observacao TEXT,
  PRIMARY KEY (insumo_id_a, insumo_id_b)
);

-- ---------- COMPOSIÇÕES (receitas de serviço) ----------
CREATE TABLE composicao (
  id INTEGER PRIMARY KEY,
  fonte_id INTEGER NOT NULL REFERENCES fonte(id),
  codigo_fonte TEXT NOT NULL,
  descricao TEXT NOT NULL,
  unidade TEXT NOT NULL,
  grupo_eap TEXT,                      -- PRELIM|FUNDACAO|ESTRUTURA|FECHAMENTO|INSTALACOES|ACABAMENTO|COMPLEMENTO|GERENCIAMENTO
  confianca TEXT NOT NULL DEFAULT 'real' CHECK (confianca IN ('real','estimado','parametrico')),
  observacao TEXT,
  UNIQUE (fonte_id, codigo_fonte)
);

CREATE TABLE composicao_item (
  id INTEGER PRIMARY KEY,
  composicao_id INTEGER NOT NULL REFERENCES composicao(id),
  item_tipo TEXT NOT NULL CHECK (item_tipo IN ('INSUMO','COMPOSICAO')),
  item_id INTEGER NOT NULL,            -- FK lógica p/ insumo ou composicao
  coeficiente REAL NOT NULL
);

-- ---------- CONHECIMENTO LSF (portado do v7 / NBR 15758) ----------
CREATE TABLE perfil_lsf (
  codigo TEXT PRIMARY KEY,             -- 'Ue90#0.95'
  familia TEXT NOT NULL,               -- Ue90, U92, M70...
  tipo TEXT NOT NULL CHECK (tipo IN ('montante','guia')),
  drywall INTEGER NOT NULL DEFAULT 0,
  alma_mm REAL NOT NULL, aba_mm REAL NOT NULL,
  enrijecedor_mm REAL, espessura_mm REAL NOT NULL,
  massa_kg_m REAL NOT NULL,
  fonte TEXT NOT NULL DEFAULT 'LSF_DB v7 (obra ref. 484125)'
);

CREATE TABLE regra_lsf (
  chave TEXT PRIMARY KEY,              -- 'modulacao_m', 'folga_chapa_mm'...
  valor REAL NOT NULL,
  unidade TEXT,
  referencia TEXT                      -- 'NBR 15758 §4.3'
);

CREATE TABLE peso_camada (
  id INTEGER PRIMARY KEY,
  material TEXT NOT NULL UNIQUE,
  kg_m2 REAL NOT NULL,
  confianca TEXT NOT NULL DEFAULT 'estimado',
  fonte TEXT,
  observacao TEXT
);

CREATE TABLE classe_solo (
  id INTEGER PRIMARY KEY,
  classe TEXT NOT NULL UNIQUE,
  descricao TEXT NOT NULL,
  spt_min INTEGER, spt_max INTEGER,
  tensao_adm_kpa REAL NOT NULL,
  observacao TEXT
);

-- ---------- MAPEAMENTO item derivado -> composição ----------
CREATE TABLE mapeamento_item (
  id INTEGER PRIMARY KEY,
  item_derivado TEXT NOT NULL UNIQUE,  -- 'fechamento.osb_m2', 'fundacao.concreto_m3'
  composicao_id INTEGER REFERENCES composicao(id),
  observacao TEXT
);

-- ---------- VIEW: custo direto de composição (1 nível) ----------
-- Nesting composição-em-composição é resolvido pelo motor (recursão).
CREATE VIEW vw_custo_composicao AS
SELECT c.id AS composicao_id, c.codigo_fonte, c.descricao, c.unidade,
       db.referencia AS data_base, db.uf,
       SUM(ci.coeficiente * ip.preco) AS custo_unitario,
       MIN(CASE WHEN ip.confianca='real' AND c.confianca='real' THEN 'real' ELSE 'estimado' END) AS confianca
FROM composicao c
JOIN composicao_item ci ON ci.composicao_id = c.id AND ci.item_tipo = 'INSUMO'
JOIN insumo i  ON i.id  = ci.item_id
JOIN insumo_preco ip ON ip.insumo_id = i.id
JOIN data_base db ON db.id = ip.data_base_id
GROUP BY c.id, db.id;
