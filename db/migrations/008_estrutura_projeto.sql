-- Migração 008 — inputs de projeto da estrutura (o que o arquitetônico não dá,
-- como o solo): esp de laje, inclinação de cobertura, vãos de escada, áreas
-- descobertas. O footprint NÃO é gravado — deriva das paredes externas (D3).
-- Instância da obra (109.1506) é seedada pelo teste a partir do oráculo, não aqui.

CREATE TABLE laje (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  id_laje TEXT NOT NULL,
  grupo TEXT NOT NULL,
  pav_base INTEGER NOT NULL,
  nivel REAL NOT NULL,
  esp_m REAL NOT NULL,
  perfil_viga TEXT NOT NULL DEFAULT 'auto',
  perfil_enrijecedor TEXT NOT NULL,
  bloqueador_max_m REAL NOT NULL,
  chapa_piso_tipo TEXT,
  chapa_piso_larg REAL,
  chapa_piso_alt REAL,
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id, id_laje)
);

CREATE TABLE laje_abertura (
  id INTEGER PRIMARY KEY,
  laje_id INTEGER NOT NULL REFERENCES laje(id),
  tipo TEXT NOT NULL,
  x REAL NOT NULL, z REAL NOT NULL, w REAL NOT NULL, d REAL NOT NULL
);

CREATE TABLE laje_extensao (
  id INTEGER PRIMARY KEY,
  laje_id INTEGER NOT NULL REFERENCES laje(id),
  x REAL NOT NULL, z REAL NOT NULL, w REAL NOT NULL, d REAL NOT NULL
);

CREATE TABLE escada (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  id_escada TEXT NOT NULL,
  grupo TEXT NOT NULL,
  vao_x REAL NOT NULL, vao_z REAL NOT NULL, vao_w REAL NOT NULL, vao_d REAL NOT NULL,
  altura REAL NOT NULL,
  nivel_inicial REAL NOT NULL,
  formato TEXT NOT NULL,
  longarina_perfil_a TEXT NOT NULL,
  longarina_perfil_b TEXT NOT NULL,
  degrau_perfil TEXT NOT NULL,
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id, id_escada)
);

CREATE TABLE cobertura (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  id_cobertura TEXT NOT NULL,
  grupo TEXT NOT NULL,
  grupo_tesouras TEXT NOT NULL,
  nivel_base REAL NOT NULL,
  beiral_m REAL NOT NULL,
  inclinacao REAL NOT NULL,
  banzo_perfil TEXT NOT NULL,
  guia_banzo_perfil TEXT NOT NULL,
  alma_perfil TEXT NOT NULL,
  telha_tipo TEXT NOT NULL,
  telha_perda_pct REAL NOT NULL,
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id, id_cobertura)
);

CREATE TABLE area_descoberta (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  nome TEXT NOT NULL,
  x REAL NOT NULL, z REAL NOT NULL, w REAL NOT NULL, d REAL NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('faixa','patio')),
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico'))
);

CREATE TABLE forro (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  perfil TEXT NOT NULL,
  perfil_borda TEXT NOT NULL,
  esp_m REAL NOT NULL,
  grupo TEXT NOT NULL,
  confianca TEXT NOT NULL CHECK (confianca IN ('real','estimado','parametrico')),
  UNIQUE (projeto_id)
);
