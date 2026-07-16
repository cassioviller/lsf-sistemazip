-- Migração 010 — perfis do painel 1CB da cobertura.
--
-- A migração 008 deu à `cobertura` os perfis da TESOURA (banzo/guia/alma), mas o
-- v7 (gerarPecasCobertura) também monta o painel 1CB no plano inclinado, com par
-- próprio: REGRAS_SIS.cobertura.painelCB = {perfil:'Ue140#0.80', perfilPer:'U142#0.80'}
-- ["derivado carimbo 1CB-140#0.80 + COB-003/005"; 1CB p.56-77].
--
-- O DEFAULT carrega o par da 109.1506 (mesmo papel do 'auto' em laje.perfil_viga
-- na 008): projeto que use outro painel sobrescreve a coluna.

ALTER TABLE cobertura ADD COLUMN painel_cb_perfil TEXT NOT NULL DEFAULT 'Ue140#0.80';
ALTER TABLE cobertura ADD COLUMN painel_cb_perfil_per TEXT NOT NULL DEFAULT 'U142#0.80';
