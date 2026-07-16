-- seed.sql · Fase 0 — fontes reais, perfis do v7, pesos, solo, composições próprias exemplo
-- Tudo que é estimativa está marcado confianca='estimado' p/ calibração (R6/§6 do plano)
--
-- IDEMPOTENTE: este arquivo é conhecimento declarativo e é reaplicado a TODO build
-- (ver db/build_db.py). Cada INSERT usa ON CONFLICT ... DO UPDATE sobre a chave
-- natural única da tabela — nunca INSERT OR REPLACE (troca rowid, quebra FK) nem
-- INSERT OR IGNORE (engole erro real de dado).

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
 ('VEKS','Composições próprias Veks Engenharia','PROPRIA','AMBOS','SP',NULL)
ON CONFLICT (sigla) DO UPDATE SET
  nome=excluded.nome, tipo=excluded.tipo, papel=excluded.papel,
  abrangencia=excluded.abrangencia, url=excluded.url;

INSERT INTO data_base (fonte_id,referencia,uf,desonerado,publicado_em)
 SELECT id,'2026-06','SP',0,'2026-07-01' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,referencia,uf,desonerado) DO UPDATE SET
  publicado_em=excluded.publicado_em;

-- ---------- PERFIS (portados do LSF_DB v7) ----------
INSERT INTO perfil_lsf (codigo,familia,tipo,drywall,alma_mm,aba_mm,enrijecedor_mm,espessura_mm,massa_kg_m) VALUES
 ('Ue70#0.80','Ue70','montante',0,70,35,10,0.80,1.00),
 ('Ue90#0.80','Ue90','montante',0,90,40,12,0.80,1.22),
 ('Ue90#0.95','Ue90','montante',0,90,40,12,0.95,1.45),
 ('Ue90#1.25','Ue90','montante',0,90,40,12,1.25,1.90),
 ('Ue140#1.25','Ue140','montante',0,140,40,12,1.25,2.39),
 ('Ue200#1.25','Ue200','montante',0,200,40,12,1.25,2.98),
 ('Ue250#2.00','Ue250','montante',0,250,40,12,2.00,5.55),
 ('U72#0.80','U72','guia',0,72,34,NULL,0.80,0.90),
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
 ('G90#0.50','G90','guia',1,90,30,NULL,0.50,0.53),
 ('U202#0.95','U202','guia',0,202,40,NULL,0.95,2.10),
 ('U252#1.25','U252','guia',0,252,40,NULL,1.25,3.26),
 ('Ue140#0.80','Ue140','montante',0,140,40,12,0.80,1.53),
 ('U142#0.80','U142','guia',0,142,40,NULL,0.80,1.39),
 ('W310x32.7','W310','laminado',0,310,102,NULL,6.6,32.7),
 ('HSS100x100x4.8','HSS100','laminado',0,100,100,NULL,4.8,14.2)
ON CONFLICT (codigo) DO UPDATE SET
  familia=excluded.familia, tipo=excluded.tipo, drywall=excluded.drywall,
  alma_mm=excluded.alma_mm, aba_mm=excluded.aba_mm, enrijecedor_mm=excluded.enrijecedor_mm,
  espessura_mm=excluded.espessura_mm, massa_kg_m=excluded.massa_kg_m;

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
 ('largura_painel_min_m',0.60,'m','sem painel-lasca: mínimo 1 módulo de montante (600mm) — prática comercial, estimado')
ON CONFLICT (chave) DO UPDATE SET
  valor=excluded.valor, unidade=excluded.unidade, referencia=excluded.referencia;

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
 ('Peso próprio perfis parede (ref.)',9.0,'parametrico','v7 kg/m² típico','substituído por cálculo real por parede')
ON CONFLICT (material) DO UPDATE SET
  kg_m2=excluded.kg_m2, confianca=excluded.confianca, fonte=excluded.fonte,
  observacao=excluded.observacao;

-- ---------- CLASSES DE SOLO (tensão presumida — PRELIMINAR) ----------
INSERT INTO classe_solo (classe,descricao,spt_min,spt_max,tensao_adm_kpa,observacao) VALUES
 ('S1','Muito mole / aterro não controlado',0,2,40,'BLOQUEIA pré-dim.: exige sondagem+projeto'),
 ('S2','Argila mole',3,5,60,'presumido conservador — flag sondagem'),
 ('S3','Argila média / areia fofa',6,9,100,'presumido conservador — flag sondagem'),
 ('S4','Argila rija / areia med. compacta',10,18,180,'presumido — confirmar por sondagem'),
 ('S5','Solo resistente / areia compacta',19,40,280,'presumido — confirmar por sondagem')
ON CONFLICT (classe) DO UPDATE SET
  descricao=excluded.descricao, spt_min=excluded.spt_min, spt_max=excluded.spt_max,
  tensao_adm_kpa=excluded.tensao_adm_kpa, observacao=excluded.observacao;

-- ---------- INSUMOS PRÓPRIOS (preços de referência, TODOS estimados) ----------
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-001','Perfil aço galvanizado Z275 conformado a frio (Ue/U)','MAT','kg' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, tipo=excluded.tipo, unidade=excluded.unidade;
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-002','Parafuso estrutural autobrocante 4,8x19 ponta broca','MAT','un' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, tipo=excluded.tipo, unidade=excluded.unidade;
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-003','Chapa OSB 11,1mm 1,20x2,40m','MAT','m2' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, tipo=excluded.tipo, unidade=excluded.unidade;
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-004','Membrana hidrófuga (tipo Tyvek)','MAT','m2' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, tipo=excluded.tipo, unidade=excluded.unidade;
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-005','Placa cimentícia 10mm','MAT','m2' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, tipo=excluded.tipo, unidade=excluded.unidade;
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-101','Montador LSF (c/ encargos)','MO','h' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, tipo=excluded.tipo, unidade=excluded.unidade;
INSERT INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)
 SELECT id,'VK-I-102','Ajudante (c/ encargos)','MO','h' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, tipo=excluded.tipo, unidade=excluded.unidade;

-- D5.1: cada insumo é precificado na data-base da SUA fonte naquela referência. O join
-- em data_base precisa filtrar por fonte_id (via i.fonte_id), não só por referência —
-- sem isso, quando outra fonte (ex. SINAPI via bridge_autosinapi.py) ganhar uma
-- data_base própria na mesma referência '2026-06', este INSERT..SELECT vira um produto
-- cartesiano insumo×data_base e fabrica preço fantasma de VEKS sob a data-base errada.
WITH p(cod,preco) AS (VALUES ('VK-I-001',14.50),('VK-I-002',0.18),('VK-I-003',46.00),
              ('VK-I-004',6.50),('VK-I-005',58.00),('VK-I-101',34.00),('VK-I-102',23.00))
INSERT INTO insumo_preco (insumo_id,data_base_id,preco,confianca)
 SELECT i.id, db.id, p.preco, 'estimado'
 FROM p
 JOIN insumo i ON i.codigo_fonte=p.cod
 JOIN data_base db ON db.fonte_id=i.fonte_id AND db.referencia='2026-06'
ON CONFLICT (insumo_id,data_base_id) DO UPDATE SET
  preco=excluded.preco, confianca=excluded.confianca;

-- ---------- COMPOSIÇÕES PRÓPRIAS LSF (o que o SINAPI não cobre) ----------
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'VK-C-001','Montagem de estrutura LSF em painéis (perfis Ue/U), incl. fixações','kg','ESTRUTURA','estimado','coef. MO a calibrar em obra (R6)' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, unidade=excluded.unidade, grupo_eap=excluded.grupo_eap,
  confianca=excluded.confianca, observacao=excluded.observacao;
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'VK-C-002','Fechamento externo em OSB 11,1mm sobre estrutura LSF','m2','FECHAMENTO','estimado','' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, unidade=excluded.unidade, grupo_eap=excluded.grupo_eap,
  confianca=excluded.confianca, observacao=excluded.observacao;
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'VK-C-003','Membrana hidrófuga aplicada sobre OSB','m2','FECHAMENTO','estimado','' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, unidade=excluded.unidade, grupo_eap=excluded.grupo_eap,
  confianca=excluded.confianca, observacao=excluded.observacao;
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'VK-C-004','Fechamento externo em placa cimentícia 10mm (parafusada)','m2','FECHAMENTO','estimado','' FROM fonte WHERE sigla='VEKS'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, unidade=excluded.unidade, grupo_eap=excluded.grupo_eap,
  confianca=excluded.confianca, observacao=excluded.observacao;

-- receitas (coeficientes de referência CBCA/fabricante — calibrar)
-- UNIQUE (composicao_id,item_tipo,item_id) vem da migração 003; build_db.py aplica
-- migrações antes do seed, então o ON CONFLICT abaixo sempre encontra o índice.
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
 JOIN insumo i ON i.codigo_fonte=r.icod
ON CONFLICT (composicao_id,item_tipo,item_id) DO UPDATE SET
  coeficiente=excluded.coeficiente;

-- ---------- MAPEAMENTO: itens derivados -> composições (SINAPI reais onde existem) ----------
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'96359','Parede drywall interno, 2 faces simples, guias simples, c/ vãos','m2','ACABAMENTO','real','composição oficial SINAPI (caderno drywall) — importar analítica' FROM fonte WHERE sigla='SINAPI'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, unidade=excluded.unidade, grupo_eap=excluded.grupo_eap,
  confianca=excluded.confianca, observacao=excluded.observacao;
INSERT INTO composicao (fonte_id,codigo_fonte,descricao,unidade,grupo_eap,confianca,observacao)
 SELECT id,'96114','Forro em drywall, ambientes comerciais, incl. estrutura','m2','ACABAMENTO','real','composição oficial SINAPI — importar analítica' FROM fonte WHERE sigla='SINAPI'
ON CONFLICT (fonte_id,codigo_fonte) DO UPDATE SET
  descricao=excluded.descricao, unidade=excluded.unidade, grupo_eap=excluded.grupo_eap,
  confianca=excluded.confianca, observacao=excluded.observacao;

INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'estrutura.aco_kg', id, 'kg de aço vindo do gerador de peças' FROM composicao WHERE codigo_fonte='VK-C-001'
ON CONFLICT (item_derivado) DO UPDATE SET
  composicao_id=excluded.composicao_id, observacao=excluded.observacao;
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'fechamento.osb_m2', id, NULL FROM composicao WHERE codigo_fonte='VK-C-002'
ON CONFLICT (item_derivado) DO UPDATE SET
  composicao_id=excluded.composicao_id, observacao=excluded.observacao;
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'fechamento.membrana_m2', id, NULL FROM composicao WHERE codigo_fonte='VK-C-003'
ON CONFLICT (item_derivado) DO UPDATE SET
  composicao_id=excluded.composicao_id, observacao=excluded.observacao;
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'fechamento.cimenticia_m2', id, NULL FROM composicao WHERE codigo_fonte='VK-C-004'
ON CONFLICT (item_derivado) DO UPDATE SET
  composicao_id=excluded.composicao_id, observacao=excluded.observacao;
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao)
 SELECT 'parede_interna.drywall_m2', id, 'SINAPI oficial' FROM composicao WHERE codigo_fonte='96359'
ON CONFLICT (item_derivado) DO UPDATE SET
  composicao_id=excluded.composicao_id, observacao=excluded.observacao;
INSERT INTO mapeamento_item (item_derivado,composicao_id,observacao) VALUES
 ('fundacao.concreto_fck30_m3', NULL, 'TODO: código SINAPI concreto usinado bombeado fck30 na importação'),
 ('fundacao.armadura_ca50_kg', NULL, 'TODO: código SINAPI armadura CA-50 na importação'),
 ('fundacao.escavacao_m3', NULL, 'TODO: SINAPI/SICRO na importação')
ON CONFLICT (item_derivado) DO UPDATE SET
  composicao_id=excluded.composicao_id, observacao=excluded.observacao;

-- ---------- FOLHAS DA EAP com composição cadastrada ----------
-- Migrado de db/migrations/001 (estrutural) para cá (conhecimento): estas linhas
-- dependem de `composicao`, que é seed, não schema. As demais folhas entram junto
-- com as composições dos 8 grupos que ainda faltam.
INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap, composicao_id)
 SELECT '03.01', (SELECT id FROM eap_item WHERE codigo='03'),
        'Montagem de estrutura LSF em painéis', 'kg', 'ESTRUTURA', id
 FROM composicao WHERE codigo_fonte = 'VK-C-001'
ON CONFLICT (codigo) DO UPDATE SET
  pai_id=excluded.pai_id, descricao=excluded.descricao, unidade=excluded.unidade,
  grupo_eap=excluded.grupo_eap, composicao_id=excluded.composicao_id;
INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap, composicao_id)
 SELECT '04.01', (SELECT id FROM eap_item WHERE codigo='04'),
        'Fechamento externo em OSB 11,1mm', 'm2', 'FECHAMENTO', id
 FROM composicao WHERE codigo_fonte = 'VK-C-002'
ON CONFLICT (codigo) DO UPDATE SET
  pai_id=excluded.pai_id, descricao=excluded.descricao, unidade=excluded.unidade,
  grupo_eap=excluded.grupo_eap, composicao_id=excluded.composicao_id;
INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap, composicao_id)
 SELECT '04.02', (SELECT id FROM eap_item WHERE codigo='04'),
        'Membrana hidrófuga sobre OSB', 'm2', 'FECHAMENTO', id
 FROM composicao WHERE codigo_fonte = 'VK-C-003'
ON CONFLICT (codigo) DO UPDATE SET
  pai_id=excluded.pai_id, descricao=excluded.descricao, unidade=excluded.unidade,
  grupo_eap=excluded.grupo_eap, composicao_id=excluded.composicao_id;
INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap, composicao_id)
 SELECT '04.03', (SELECT id FROM eap_item WHERE codigo='04'),
        'Fechamento externo em placa cimentícia 10mm', 'm2', 'FECHAMENTO', id
 FROM composicao WHERE codigo_fonte = 'VK-C-004'
ON CONFLICT (codigo) DO UPDATE SET
  pai_id=excluded.pai_id, descricao=excluded.descricao, unidade=excluded.unidade,
  grupo_eap=excluded.grupo_eap, composicao_id=excluded.composicao_id;
INSERT INTO eap_item (codigo, pai_id, descricao, unidade, grupo_eap, composicao_id)
 SELECT '06.01', (SELECT id FROM eap_item WHERE codigo='06'),
        'Parede drywall interno, 2 faces', 'm2', 'ACABAMENTO', id
 FROM composicao WHERE codigo_fonte = '96359'
ON CONFLICT (codigo) DO UPDATE SET
  pai_id=excluded.pai_id, descricao=excluded.descricao, unidade=excluded.unidade,
  grupo_eap=excluded.grupo_eap, composicao_id=excluded.composicao_id;

-- ---------- Gerador de estrutura F2.1: guia correspondente (guiaDe v7) ----------
INSERT INTO guia_de (familia_montante, familia_guia) VALUES
 ('Ue70','U72'),('Ue90','U92'),('Ue140','U142'),('Ue200','U202'),('Ue250','U252'),
 ('M48','G48'),('M70','G70'),('M90','G90')
ON CONFLICT (familia_montante) DO UPDATE SET familia_guia=excluded.familia_guia;

-- ---------- Escalonamento de verga (vergaPorVao v7) ----------
INSERT INTO verga_escalonamento (faixa_ate_m, perfil_montante, perfil_guia, origem) VALUES
 (1.2, NULL, NULL, 'OBRA DX-11: até 1,2m verga no perfil da parede'),
 (2.0, 'Ue140#1.25', 'U142#1.25', 'OBRA DX-11 caso pesado; escalonamento pendente'),
 (9.9, 'Ue250#2.00', 'U252#2.00', 'OBRA DX-11 caso pesado; escalonamento pendente')
ON CONFLICT (faixa_ate_m) DO UPDATE SET
  perfil_montante=excluded.perfil_montante, perfil_guia=excluded.perfil_guia,
  origem=excluded.origem;

-- ---------- Escalonamento de perfil da laje (gerarPecasLaje v7) ----------
-- Pares reais das listas 1L da 109.1506; o limiar da faixa é a regra laje_vao_ue200.
INSERT INTO laje_escalonamento (faixa_ate_m, perfil_viga, perfil_bloqueador, origem) VALUES
 (4.0, 'Ue200#1.25', 'U202#0.95', 'v7 gerarPecasLaje: vão ef <= 4m [listas 1L: par real Ue200+U202#0.95]'),
 (99.0, 'Ue250#2.00', 'U252#1.25', 'v7 gerarPecasLaje: vão ef > 4m [listas 1L: par real Ue250+U252#1.25]')
ON CONFLICT (faixa_ate_m) DO UPDATE SET
  perfil_viga=excluded.perfil_viga, perfil_bloqueador=excluded.perfil_bloqueador,
  origem=excluded.origem;

-- ---------- Regras do gerador de paredes (REGRAS do v7, linhas 164-190) ----------
-- Coeficiente novo sem calibração de obra = estimado (referência anotada).
INSERT INTO regra_lsf (chave,valor,unidade,referencia) VALUES
 ('modulacao_lsf_m',0.40,'m','wallToP v7: passo de montante LSF estrutural (drywall usa modulacao_m)'),
 ('barra_m',6.0,'m','REGRA BOX-003 [mont. p.53]'),
 ('king_duplo_lim_m',2.0,'m','GATE2 painel 1P4: 1 king+1 jack por lado até 2m'),
 ('jack_duplo_lim_m',2.0,'m','CBCA/AISI, pendente'),
 ('apoio_verga_m',0.10,'m','OBRA aprox: apoio da verga sobre jack, por lado'),
 ('passo_hb_m',0.70,'m','OBRA-1P4, pendente: bloqueadores ~700mm'),
 ('peitoril_padrao_m',1.0,'m','v7 peitorilPadrao'),
 ('passo_trelica_m',0.28,'m','GATE2 1P4: passo vertical do zigzag (~21 diag)'),
 ('colunas_trelica_se_m',0.45,'m','v7: módulo > 0,45m → 2 colunas c/ montante curto'),
 ('diag_sobre_verga_min_m',1.0,'m','GATE2 1P4 BRR1-3: vão >= 1m → diagonais entre cripples'),
 ('alt_min_porta_giro_m',2.15,'m','GUIA SMART: vão mín. porta de giro'),
 ('alt_min_porta_correr_m',2.20,'m','GUIA SMART: vão mín. porta-janela de correr'),
 ('margem_abertura_m',0.10,'m','v7 gerarPecas: folga mínima da abertura à borda'),
 ('folga_entre_aberturas_m',0.15,'m','v7 gerarPecas: folga mínima entre aberturas'),
 ('passo_conex_painel_m',0.20,'m','OBRA DP-07: parafusos entre painéis, ziguezague'),
 ('ancor_esp_padrao_m',1.20,'m','OBRA "por modulação", pendente'),
 -- acessórios de nível de EDIFÍCIO (v7 montarProjeto), não da peça
 ('verga_paraf_passo_m',0.20,'m','A5/VERGA-002-003 [DX-11 p.40]: parafuso de verga @200mm'),
 ('laje_chapa_l_passo_m',3.00,'m','DX-06 [OBRA p.6/8]: 1 Chapa L de 3 m por 3 m de perímetro'),
 ('laje_cantoneira_por_viga',0.80,'un/viga','painel 1L8 p.28: 13 cantoneiras / 16 vigas'),
 ('impermeab_folga',1.10,'-','área descoberta [folha 102] + 10%'),
 -- instalações [HID R02 p.1-7 · CRI gás p.1]
 ('instal_furos_por_ponto',2,'un','DP-08: 2 furos de serviço por ponto'),
 ('instal_paraf_chapa_reforco',8,'un','DP-08: 8 parafusos por chapa de reforço'),
 ('instal_luva_gas_m',2.50,'m','CRI gás: tubo-luva PVC por ponto de GLP'),
 ('instal_furo_max_cm',12,'cm','HID-FURO-001: furo máx. 12cm na zona de tração'),
 ('instal_furo_max_h_frac',3,'-','HID-FURO-001: furo máx. h/3 da altura da viga'),
 ('instal_furo_espac_min_h',2,'-','HID R02: espaçamento entre furos >= 2h'),
 ('instal_furo_vert_max_mm',50,'mm','HID R02: furo vertical Ø <= 50mm'),
 ('instal_gas_afast_eletrica_cm',30,'cm','CRI gás p.1: GLP >= 30cm da elétrica'),
 ('instal_gas_ponto_alt_min_cm',60,'cm','CRI gás p.1: ponto de GLP >= 60cm do piso')
ON CONFLICT (chave) DO UPDATE SET
  valor=excluded.valor, unidade=excluded.unidade, referencia=excluded.referencia;

-- ============ Estrutura: regras de laje/escada/cobertura (v7:656-681) ============
INSERT INTO regra_lsf (chave,valor,unidade,referencia) VALUES
  ('laje_esp_m',0.40,'m','v7 REGRAS_SIS.laje.esp'),
  ('laje_bloqueador_max_m',2.40,'m','A4 [p.27 LAJE-005] bloqueador por vão'),
  ('laje_vao_ue200',4.0,'m','v7: vão ef >4m → Ue250'),
  ('laje_enrij_c_f200',0.176,'m','REGRA LAJE-009: C=176mm (laje 200) [p.27-38]'),
  ('laje_enrij_c_f250',0.226,'m','REGRA LAJE-010: C=226mm (laje 250) [p.39]'),
  ('laje_fix_mesa_paraf',4,'un','DP-01A: 2 paraf/ligação × 2 extremidades'),
  ('laje_fix_alma_paraf',5,'un','REGRA LAJE-007 [DL-01 p.21-39]'),
  ('escada_espelho_max',0.175,'m','v7 REGRAS_SIS.escada.espelhoMax'),
  ('escada_piso_min',0.28,'m','v7 REGRAS_SIS.escada.pisoMin'),
  ('escada_piso_abs_min',0.24,'m','v7 gerarPecasEscada: piso nunca abaixo de 0,24m mesmo em poço curto (abaixo disso vira alerta)'),
  ('escada_fix_lateral_mm',150,'mm','1ES1: reforço 140 @150mm'),
  ('cobertura_esp_tesoura',1.20,'m','v7 REGRAS_SIS.cobertura.espTesoura'),
  ('cobertura_passo_mont',0.40,'m','1TS41-46: ~10 montantes/3,77m [p.44-49]'),
  ('cobertura_beiral_m',0.30,'m','v7 PROJECT.cobertura.beiral'),
  ('cobertura_gusset_paraf',4,'un','1TS41/42: gusset por nó'),
  ('cobertura_box_paraf_mm',200,'mm','DX-09: box @200mm'),
  ('cobertura_cb_passo',0.60,'m','1CB p.56-77: travessas 140#0.80 @0,60')
ON CONFLICT (chave) DO UPDATE SET
  valor=excluded.valor, unidade=excluded.unidade, referencia=excluded.referencia;

-- ============ Cargas e seção p/ dimensionar_viga (v7:633-642) — NBR ============
-- Valores e unidades EXATOS do v7 (CARGAS v7:633, SEC_Ue250 v7:634). A aritmética
-- de dimensionar_viga (Task 4) reproduz o v7 com os fatores de conversão (1e6/1e9/1e12),
-- então o seed guarda os números na unidade v7 — NÃO converter aqui.
INSERT INTO regra_lsf (chave,valor,unidade,referencia) VALUES
  ('carga_sc',4.0,'kN/m²','NBR 6120: sobrecarga (v7 CARGAS.sc=4.0)'),
  ('carga_g',1.3,'kN/m²','NBR 6120: permanente (v7 CARGAS.g=1.3)'),
  ('aco_fy',230,'MPa','NBR 14762: ZAR230 fy (v7 CARGAS.fy=230)'),
  ('aco_E',200000,'MPa','NBR 14762: módulo E (v7 CARGAS.E=2.0e5)'),
  ('coef_gm',1.10,'-','NBR 14762: γM (v7 CARGAS.gM=1.10)'),
  ('flecha_lim',350,'-','NBR 14762: L/350 (v7 CARGAS.flecha=350)'),
  ('sec_ue250_a',708,'mm²','NBR 14762 (entrada) · SEC_Ue250.A (v7:634)'),
  ('sec_ue250_wx',46300,'mm³','NBR 14762 (entrada) · SEC_Ue250.Wx=46.3e3 (v7:634)'),
  ('sec_ue250_ix',5780000,'mm⁴','NBR 14762 (entrada) · SEC_Ue250.Ix=5.78e6 (v7:634)')
ON CONFLICT (chave) DO UPDATE SET
  valor=excluded.valor, unidade=excluded.unidade, referencia=excluded.referencia;

-- ============================================================
-- Camadas por tipo de parede (migração 013) — o que o spike 4 tinha chumbado.
-- Externa: fechamento cimentício + membrana na face externa, gesso na interna.
-- Interna: gesso nas DUAS faces (faces=2), sem cimentícia nem membrana.
-- ============================================================
INSERT INTO camada_parede (tipo,material,faces,origem) VALUES
 ('externa','Peso próprio perfis parede (ref.)',1,'spike 4 / OBRA 1PV'),
 ('externa','OSB 11,1mm',1,'spike 4: diafragma/substrato'),
 ('externa','Placa cimentícia 10mm',1,'spike 4: face externa'),
 ('externa','Gesso ST 12,5mm',1,'spike 4: face interna'),
 ('externa','Lã de vidro 50mm',1,'spike 4: isolamento'),
 ('externa','Membrana hidrófuga',1,'spike 4: face externa'),
 ('interna','Peso próprio perfis parede (ref.)',1,'OBRA 1PV'),
 ('interna','Gesso ST 12,5mm',2,'divisória: gesso nas duas faces'),
 ('interna','Lã de vidro 50mm',1,'isolamento acústico')
ON CONFLICT (tipo,material) DO UPDATE SET
  faces=excluded.faces, origem=excluded.origem;
