-- ============================================================
-- 004 — planta_normalizada (Fase 2, estágio 1): níveis, nós, paredes, vãos
-- Estrutura de grafo: cantos são nós, paredes são arestas — conceito do
-- Raster-to-Graph (paper CVPR'24; repo SEM licença: zero código, só ideia)
-- e alvo comum das entradas DXF / croqui / manual (docs/02 §2, rotas duplas).
-- Todo registro carrega origem e confiança (D4).
-- ============================================================
PRAGMA foreign_keys = ON;

CREATE TABLE nivel (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  indice INTEGER NOT NULL,                      -- 0 = térreo
  nome TEXT NOT NULL,                           -- 'Térreo', '1º pavimento'
  pe_direito_m REAL NOT NULL CHECK (pe_direito_m > 0),
  cota_m REAL NOT NULL DEFAULT 0,
  UNIQUE (projeto_id, indice)
);

CREATE TABLE no_planta (
  id INTEGER PRIMARY KEY,
  nivel_id INTEGER NOT NULL REFERENCES nivel(id),
  x REAL NOT NULL,
  y REAL NOT NULL,
  confianca TEXT NOT NULL DEFAULT 'estimado'
    CHECK (confianca IN ('real','estimado','parametrico'))
);

CREATE TABLE parede (
  id INTEGER PRIMARY KEY,
  nivel_id INTEGER NOT NULL REFERENCES nivel(id),
  no_a INTEGER NOT NULL REFERENCES no_planta(id),
  no_b INTEGER NOT NULL REFERENCES no_planta(id),
  espessura_m REAL NOT NULL CHECK (espessura_m > 0),
  portante INTEGER NOT NULL DEFAULT 1 CHECK (portante IN (0,1)),
  externa INTEGER NOT NULL DEFAULT 0 CHECK (externa IN (0,1)),
  perfil_codigo TEXT REFERENCES perfil_lsf(codigo),  -- NULL até o gerador decidir
  origem TEXT NOT NULL CHECK (origem IN ('DXF','CROQUI','MANUAL')),
  confianca TEXT NOT NULL DEFAULT 'estimado'
    CHECK (confianca IN ('real','estimado','parametrico')),
  origem_regra TEXT,                            -- ex.: 'classificador portante v0'
  CHECK (no_a <> no_b)
);

-- nós da parede pertencem ao mesmo nível da parede (grafo por pavimento)
CREATE TRIGGER trg_parede_nos_mesmo_nivel
BEFORE INSERT ON parede
FOR EACH ROW
WHEN (SELECT nivel_id FROM no_planta WHERE id = NEW.no_a) IS NOT NEW.nivel_id
  OR (SELECT nivel_id FROM no_planta WHERE id = NEW.no_b) IS NOT NEW.nivel_id
BEGIN
  SELECT RAISE(ABORT, 'nós da parede devem pertencer ao mesmo nível da parede');
END;

CREATE TABLE vao (
  id INTEGER PRIMARY KEY,
  parede_id INTEGER NOT NULL REFERENCES parede(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('PORTA','JANELA','PORTA_JANELA')),
  posicao_m REAL NOT NULL CHECK (posicao_m >= 0),   -- distância do nó A à lateral esquerda
  largura_m REAL NOT NULL CHECK (largura_m > 0),
  altura_m REAL NOT NULL CHECK (altura_m > 0),
  peitoril_m REAL NOT NULL DEFAULT 0 CHECK (peitoril_m >= 0),
  confianca TEXT NOT NULL DEFAULT 'estimado'
    CHECK (confianca IN ('real','estimado','parametrico'))
);
