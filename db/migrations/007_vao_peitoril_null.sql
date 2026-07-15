-- ============================================================
-- 007 — vao.peitoril_m NULLable: NULL = "não informado"
-- Semântica do v7 (linha 248: `a.peitoril ?? R.peitorilPadrao`, nullish):
-- ausente → o gerador usa a regra `regra_lsf.peitoril_padrao_m`;
-- 0 EXPLÍCITO é dado (porta-janela) e continua 0.
-- O schema da 004 tinha `NOT NULL DEFAULT 0`, que confundia os dois casos:
-- janela sem peitoril virava porta (sill=0) e subestimava kg.
--
-- ATENÇÃO (irreversível): linhas legadas gravadas com o DEFAULT 0 antigo
-- permanecem 0 — não há como distinguir retroativamente "0 explícito" de
-- "não informado". Quem quiser o padrão precisa reeditar o vão para NULL.
--
-- SQLite não altera coluna: CREATE nova + INSERT SELECT + DROP + RENAME
-- (mesma disciplina da 006). `db/build_db.py` liga/desliga PRAGMA foreign_keys
-- FORA da transação de migração e roda PRAGMA foreign_key_check pré-commit —
-- não repetir aqui.
-- ============================================================
CREATE TABLE vao_novo (
  id INTEGER PRIMARY KEY,
  parede_id INTEGER NOT NULL REFERENCES parede(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('PORTA','JANELA','PORTA_JANELA')),
  posicao_m REAL NOT NULL CHECK (posicao_m >= 0),   -- distância do nó A à lateral esquerda
  largura_m REAL NOT NULL CHECK (largura_m > 0),
  altura_m REAL NOT NULL CHECK (altura_m > 0),
  peitoril_m REAL NULL DEFAULT NULL                 -- NULL = não informado (regra decide)
    CHECK (peitoril_m IS NULL OR peitoril_m >= 0),
  confianca TEXT NOT NULL DEFAULT 'estimado'
    CHECK (confianca IN ('real','estimado','parametrico'))
);
INSERT INTO vao_novo SELECT * FROM vao;
DROP TABLE vao;
ALTER TABLE vao_novo RENAME TO vao;
