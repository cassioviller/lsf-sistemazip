-- ============================================================
-- 005 — Instância do aplicativo: usuário e proposta publicada
-- Spec: docs/superpowers/specs/2026-07-14-aplicativo-casca-web-design.md
-- D5 levado ao limite: a proposta publicada CONGELA um snapshot. A rota pública
-- serve o HTML gravado e nunca recalcula — preço que mude amanhã não reescreve o
-- que o cliente recebeu.
-- ============================================================
PRAGMA foreign_keys = ON;

CREATE TABLE usuario (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  senha_hash TEXT NOT NULL,          -- scrypt$n$r$p$salt_hex$hash_hex
  nome TEXT NOT NULL,
  ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
  criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE proposta (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  versao INTEGER NOT NULL CHECK (versao >= 1),
  token TEXT NOT NULL UNIQUE,        -- secrets.token_urlsafe(32); não enumerável
  publicada_em TEXT NOT NULL DEFAULT (datetime('now')),
  publicada_por INTEGER NOT NULL REFERENCES usuario(id),
  snapshot_json TEXT NOT NULL,       -- OrcamentoVenda serializado (auditoria)
  html TEXT NOT NULL,                -- página congelada servida em /p/<token>
  -- D4.1: proposta sem preço não existe. O gate recusa antes de chegar aqui;
  -- o NOT NULL é a última linha de defesa.
  total_venda REAL NOT NULL,
  bdi_pct REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa','revogada')),
  UNIQUE (projeto_id, versao)
);
CREATE INDEX ix_proposta_projeto ON proposta (projeto_id);
