-- seed.sql · Fase 0 — fontes reais, perfis do v7, pesos, solo, composições próprias exemplo
-- Tudo que é estimativa está marcado confianca='estimado' p/ calibração (R6/§6 do plano)

INSERT INTO fonte (sigla,nome,tipo,papel,abrangencia,url) VALUES
 ('SINAPI','Sist. Nacional de Pesquisa de Custos e Índices — CEF/IBGE','OFICIAL','AMBOS','BR','https://www.caixa.gov.br/sinapi'),
 ('CDHU','Boletim CDHU (ex-CPOS) — Estado de SP','OFICIAL','AMBOS','SP','https://cdhu.sp.gov.br/licitacoes/tabelas-de-composicao'),
 ('SIURB','SIURB/EDIF — Prefeitura de São Paulo','OFICIAL','AMBOS','SP-capital',NULL),
 ('ORSE','Orçamento de Obras de Sergipe','OFICIAL','AMBOS','SE',NULL),
 ('SICRO','Sist. de Custos Referenciais de Obras — DNIT','OFICIAL','AMBOS','BR',NULL),
 ('EMOP','Empresa de Obras Públicas — RJ','OFICIAL','AMBOS','RJ',NULL),
 ('SEINFRA','SEINFRA — CE','OFICIAL','AMBOS','CE',NULL),
 ('FDE','Fundação p/ o Desenvolvimento da Educação — SP','OFICIAL','AMBOS','SP',NULL),
 ('TCPO','Tabela de Composição de Preços p/ Orçamentos — PINI','PRIVADA','COEFICIENTE','BR',NULL),
 ('CBCA','Centro Brasileiro da Construção em Aço — manuais LSF','NORMATIVA','COEFICIENTE','BR',NULL),
 ('FABR','Manuais de fabricante (Knauf/Placo/Brasilit/Barbieri/LP)','FABRICANTE','COEFICIENTE','BR',NULL),
 ('VEKS','Composições próprias Veks Engenharia','PROPRIA','AMBOS','SP',NULL);

INSERT INTO data_base (fonte_id,referencia,uf,desonerado,publicado_em)
 SELECT id,'2026-06','SP',0,'2026-07-01' FROM fonte WHERE sigla='VEKS';

-- ---------- PERFIS (portados do LSF_DB v7) ----------
INSERT INTO perfil_lsf (codigo,familia,tipo,drywall,alma_mm,aba_mm,enrijecedor_mm,espessura_mm,massa_kg_m) VALUES
 ('Ue70#0.80','Ue70','montante',0,70,40,12,0.80,1.09),
 ('Ue90#0.80','Ue90','montante',0,90,40,12,0.80,1.22),
 ('Ue90#0.95','Ue90','montante',0,90,40,12,0.95,1.45),
 ('Ue90#1.25','Ue90','montante',0,90,40,12,1.25,1.90),
 ('Ue140#1.25','Ue140','montante',0,140,40,12,1.25,2.39),
 ('Ue200#1.25','Ue200','montante',0,200,40,12,1.25,2.98),
 ('Ue250#2.00','Ue250','montante',0,250,40,12,2.00,5.55),
 ('U72#0.80','U72','guia',0,72,38,NULL,0.80,0.93),
 ('U92#0.80','U92','guia',0,92,38,NULL,0.80,1.06),
 ('U92#0.95','U92','guia',0,92,38,NULL,0.95,1.25),
 ('U92#1.25','U92','guia',0,92,38,NULL,1.25,1.65),
 ('U142#1.25','U142','guia',0,142,38,NULL,1.25,2.14),
 ('U202#1.25','U202','guia',0,202,38,NULL,1.25,2.73),
 ('U252#2.00','U252','guia',0,252,38,NULL,2.00,5.14),
 ('M48#0.50','M48','montante',1,48,35,5,0.50,0.44),
 ('M70#0.50','M70','montante',1,70,40,5,0.50,0.57),
 ('M90#0.50','M90','montante',1,90,40,5,0.50,0.66),
 ('G48#0.50','G48','guia',1,48,30,NULL,0.50,0.39),
 ('G70#0.50','G70','guia',1,70,30,NULL,0.50,0.46),
 ('G90#0.50','G90','guia',1,90,30,NULL,0.50,0.53);

INSERT INTO regra_lsf (chave,valor,unidade,referencia) VALUES
 ('modulacao_m',0.60,'m','NBR 15758 §4.3 — 400mm p/ +carga'),
 ('paraf_duplo_mm',400,'mm','§6.4 montantes duplos aparafusados'),
 ('folga_chapa_mm',10,'mm','§6.5 chapa 10mm menor que pé-direito'),
 ('paraf_placa_campo_mm',300,'mm','prática/NBR'),
 ('paraf_placa_borda_mm',250,'mm','prática/NBR'),
 ('massa_junta_kg_m2',0.5,'kg/m²','ref. drywall'),
 ('fita_junta_ml_m2',2.0,'ml/m²','ref. drywall'),
 ('perda_perfil_pct',2.0,'%','v7: adicionais AD/BX ±2% — ATENÇÃO: VK-C-001 já embute coef 1,02; não aplicar 2x'),
 ('caixa_persiana_m',0.21,'m','GUIA SMART'),
 -- panelização (colheita 07/2026: régua comercial FRAMECAD/Vertex/StrucSoft/Scottsdale + v7; ver docs/05)
 ('largura_painel_max_m',3.6,'m','v7 REGRAS larguraPainelMaxM [OBRA layout 1PV: paredes divididas]'),
 ('painel_comp_max_transporte_m',6.0,'m','parâmetro transporte/manuseio (CLAUDE.md); barraM v7=6,0 é emenda de PERFIL, não painel'),
 ('junta_folga_vao_m',0.30,'m','junta nunca a <30cm da lateral de vão (montante duplo × emenda) — validar c/ eng. estrutural'),
 ('largura_painel_min_m',0.60,'m','sem painel-lasca: mínimo 1 módulo de montante (600mm) — prática comercial, estimado');

-- ---------- PESOS POR CAMADA (kg/m²) — takedown de cargas ----------
INSERT INTO peso_camada (material,kg_m2,confianca,fonte,observacao) VALUES
 ('OSB 11,1mm',6.8,'estimado','FABR (LP)','~610 kg/m³'),
 ('Placa cimentícia 10mm',14.5,'estimado','FABR (Brasilit)','calibrar c/ ficha técnica'),
 ('Gesso ST 12,5mm',9.5,'estimado','FABR (Knauf/Placo)',''),
 ('Gesso RU 12,5mm',10.0,'estimado','FABR',''),
 ('Lã de vidro 50mm',1.4,'estimado','FABR',''),
 ('Membrana hidrófuga',0.2,'estimado','FABR',''),
 ('Telha shingle + OSB',18.0,'estimado','FABR','inclui OSB de base'),
 ('Telha metálica trapezoidal',5.5,'estimado','FABR',''),
 ('Contrapiso seco (2x OSB/cimentícia)',22.0,'estimado','FABR','entrepiso seco'),
 ('Peso próprio perfis parede (ref.)',9.0,'parametrico','v7 kg/m² típico','substituído por cálculo real por parede');

-- ---------- CLASSES DE SOLO (tensão presumida — PRELIMINAR) ----------
INSERT INTO classe_solo (classe,descricao,spt_min,spt_max,tensao_adm_kpa,observacao) VALUES
 ('S1','Muito mole / aterro não controlado',0,2,40,'BLOQUEIA pré-dim.: exige sondagem+projeto'),
 ('S2','Argila mole',3,5,60,'presumido conservador — flag sondagem'),
 ('S3','Argila média / areia fofa',6,9,100,'presumido conservador — flag sondagem'),
 ('S4','Argila rija / areia med. compacta',10,18,180,'presumido — confirmar por sondagem'),
 ('S5','Solo resistente / areia compacta',19,40,280,'presumido — confirmar por sondagem');

-- ---------- INSUMOS PRÓPRIOS (preços de referência, TODOS estimados) ----------
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-001','Perfil aço galvanizado Z275 conformado a frio (Ue/U)','MAT','kg' FROM fonte WHERE sigla='VEKS';
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-002','Parafuso estrutural autobrocante 4,8x19 ponta broca','MAT','un' FROM fonte WHERE sigla='VEKS';
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-003','Chapa OSB 11,1mm 1,20x2,40m','MAT','m2' FROM fonte WHERE sigla='VEKS';
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-004','Membrana hidrófuga (tipo Tyvek)','MAT','m2' FROM fonte WHERE sigla='VEKS';
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-005','Placa cimentícia 10mm','MAT','m2' FROM fonte WHERE sigla='VEKS';
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-101','Montador LSF (c/ encargos)','MO','h' FROM fonte WHERE sigla='VEKS';
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-102','Ajudante (c/ encargos)','MO','h' FROM fonte WHERE sigla='VEKS';

WITH p(cod,preco) AS (VALUES ('VK-I-001',14.50),('VK-I-002',0.18),('VK-I-003',46.00),
              ('VK-I-004',6.50),('VK-I-005',58.00),('VK-I-101',34.00),('VK-I-102',23.00))
INSERT INTO insumo_preco (insumo_id,data_base_id,preco,confianca)
 SELECT i.id, db.id, p.preco, 'estimado'
 FROM p
 JOIN insumo i ON i.codigo_fonte=p.cod
 JOIN data_base db ON db.referencia='2026-06';

-- ---------- COMPOSIÇÕES PRÓPRIAS LSF (o que o SINAPI não cobre) ----------
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'VK-C-001','Montagem de estrutura LSF em painéis (perfis Ue/U), incl. fixações','kg','ESTRUTURA','estimado','coef. MO a calibrar em obra (R6)' FROM fonte WHERE sigla='VEKS';
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'VK-C-002','Fechamento externo em OSB 11,1mm sobre estrutura LSF','m2','FECHAMENTO','estimado','' FROM fonte WHERE sigla='VEKS';
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'VK-C-003','Membrana hidrófuga aplicada sobre OSB','m2','FECHAMENTO','estimado','' FROM fonte WHERE sigla='VEKS';
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'VK-C-004','Fechamento externo em placa cimentícia 10mm (parafusada)','m2','FECHAMENTO','estimado','' FROM fonte WHERE sigla='VEKS';

-- receitas (coeficientes de referência CBCA/fabricante — calibrar)
WITH r(ccod,icod,coef) AS (VALUES
         ('VK-C-001','VK-I-001',1.02),('VK-C-001','VK-I-002',6.0),
         ('VK-C-001','VK-I-101',0.040),('VK-C-001','VK-I-102',0.040),
         ('VK-C-002','VK-I-003',1.05),('VK-C-002','VK-I-002',16.0),
         ('VK-C-002','VK-I-101',0.22),('VK-C-002','VK-I-102',0.22),
         ('VK-C-003','VK-I-004',1.10),('VK-C-003','VK-I-102',0.06),
         ('VK-C-004','VK-I-005',1.05),('VK-C-004','VK-I-002',18.0),
         ('VK-C-004','VK-I-101',0.35),('VK-C-004','VK-I-102',0.35))
INSERT INTO composicao_item (composicao_id,item_tipo,item_id,coeficiente)
 SELECT c.id,'INSUMO',i.id,r.coef
 FROM r
 JOIN composicao c ON c.codigo_fonte=r.ccod
 JOIN insumo i ON i.codigo_fonte=r.icod;

-- ---------- MAPEAMENTO: itens derivados -> composições (SINAPI reais onde existem) ----------
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'96359','Parede drywall interno, 2 faces simples, guias simples, c/ vãos','m2','ACABAMENTO','real','composição oficial SINAPI (caderno drywall) — importar analítica' FROM fonte WHERE sigla='SINAPI';
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'96114','Forro em drywall, ambientes comerciais, incl. estrutura','m2','ACABAMENTO','real','composição oficial SINAPI — importar analítica' FROM fonte WHERE sigla='SINAPI';

INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'estrutura.aco_kg', id, 'kg de aço vindo do gerador de peças' FROM composicao WHERE codigo_fonte='VK-C-001';
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'fechamento.osb_m2', id, NULL FROM composicao WHERE codigo_fonte='VK-C-002';
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'fechamento.membrana_m2', id, NULL FROM composicao WHERE codigo_fonte='VK-C-003';
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'fechamento.cimenticia_m2', id, NULL FROM composicao WHERE codigo_fonte='VK-C-004';
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'parede_interna.drywall_m2', id, 'SINAPI oficial' FROM composicao WHERE codigo_fonte='96359';
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao) VALUES
 ('fundacao.concreto_fck30_m3', NULL, 'TODO: código SINAPI concreto usinado bombeado fck30 na importação'),
 ('fundacao.armadura_ca50_kg', NULL, 'TODO: código SINAPI armadura CA-50 na importação'),
 ('fundacao.escavacao_m3', NULL, 'TODO: SINAPI/SICRO na importação');
