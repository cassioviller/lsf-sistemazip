-- ============================================================
-- 002 — Parâmetros globais (BDI decomposto TCU, e futuros encargos/contingência)
-- docs/01 §4. Valores do spike 3 (BDI 27,79%, dentro da faixa paradigma do
-- Acórdão TCU 2622/2013 p/ edificações). Tudo 'estimado' até calibração (R6).
-- ============================================================
PRAGMA foreign_keys = ON;

CREATE TABLE parametros_globais (
  id INTEGER PRIMARY KEY,
  chave TEXT NOT NULL UNIQUE,
  valor REAL NOT NULL,
  unidade TEXT,
  confianca TEXT NOT NULL DEFAULT 'estimado' CHECK (confianca IN ('real','estimado','parametrico')),
  fonte TEXT,
  observacao TEXT
);

INSERT INTO parametros_globais (chave, valor, unidade, confianca, fonte, observacao) VALUES
 ('bdi_ac', 0.0400, 'fração', 'estimado', 'Acórdão TCU 2622/2013', 'AC — administração central'),
 ('bdi_s',  0.0080, 'fração', 'estimado', 'Acórdão TCU 2622/2013', 'S — seguros'),
 ('bdi_r',  0.0127, 'fração', 'estimado', 'Acórdão TCU 2622/2013', 'R — riscos'),
 ('bdi_g',  0.0113, 'fração', 'estimado', 'Acórdão TCU 2622/2013', 'G — garantias'),
 ('bdi_df', 0.0139, 'fração', 'estimado', 'Acórdão TCU 2622/2013', 'DF — despesas financeiras'),
 ('bdi_l',  0.0740, 'fração', 'estimado', 'Acórdão TCU 2622/2013', 'L — lucro'),
 ('bdi_i',  0.0865, 'fração', 'estimado', 'Acórdão TCU 2622/2013', 'I — impostos s/ faturamento (PIS/COFINS/ISS)');
