-- ============================================================
-- 003 — Integridade de composicao_item
-- Motivada pela colheita AutoSINAPI (composicao_insumos tem PK composta
-- pai+filho) e pelo bug provado na análise: reinserir a mesma analítica
-- dobrava o custo em silêncio. Mesmo item 2x na mesma composição não é
-- modelagem válida — soma-se o coeficiente numa linha só.
-- ============================================================
CREATE UNIQUE INDEX ux_composicao_item_unico
  ON composicao_item (composicao_id, item_tipo, item_id);
