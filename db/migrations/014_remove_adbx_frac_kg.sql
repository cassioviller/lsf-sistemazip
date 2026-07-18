-- Migração 014 — remove a regra duplicada `adbx_frac_kg`.
--
-- Ela nasceu neste branch como chave nova para os 2% de perfis avulsos AD/BX,
-- sem perceber que `perda_perfil_pct` (2.0) já existia para exatamente isso — e,
-- pior, que a referência DELA carrega o aviso que a nova escondia:
--
--   'v7: adicionais AD/BX ±2% — ATENÇÃO: VK-C-001 já embute coef 1,02; não aplicar 2x'
--
-- A composição VK-C-001 consome 1,02 kg de perfil por kg de estrutura: os mesmos
-- 2%. Duas chaves para o mesmo coeficiente é como o aço infla 2% em silêncio no
-- dia em que alguém ligar acessório → EAP.
--
-- Sai por migração porque o seed é upsert idempotente: tirar a linha do seed.sql
-- não apaga a chave de um banco que já existe.

DELETE FROM regra_lsf WHERE chave = 'adbx_frac_kg';
