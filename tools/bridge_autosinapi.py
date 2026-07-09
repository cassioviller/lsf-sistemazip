# -*- coding: utf-8 -*-
"""PONTE Rota A: staging AutoSINAPI (Postgres em prod; SQLite aqui) → lsf_base.db
Prova: composição SINAPI 96359 (já cadastrada sem analítica) ganha itens+preços e passa a custar na view."""
import sqlite3

# ---- 1. STAGING: simula as tabelas que o ETL do AutoSINAPI popula (fixture) ----
st = sqlite3.connect("autosinapi_stage.db")
st.executescript("""
DROP TABLE IF EXISTS insumos; DROP TABLE IF EXISTS precos_insumos; DROP TABLE IF EXISTS composicao_insumos;
CREATE TABLE insumos (codigo INTEGER PRIMARY KEY, descricao TEXT, unidade TEXT, classificacao TEXT);
CREATE TABLE precos_insumos (insumo_codigo INTEGER, uf TEXT, data_referencia TEXT, regime TEXT, preco_mediano REAL);
CREATE TABLE composicao_insumos (composicao_pai_codigo INTEGER, insumo_filho_codigo INTEGER, coeficiente REAL);
""")
fixture_insumos = [  # códigos reais SINAPI, valores de fixture p/ teste da ponte
 (88278,'MONTADOR DE ESTRUTURA METÁLICA COM ENCARGOS','H','MAO_DE_OBRA'),
 (88316,'SERVENTE COM ENCARGOS COMPLEMENTARES','H','MAO_DE_OBRA'),
 (10774,'CHAPA DE GESSO DRYWALL ST 12,5MM','M2','MATERIAL'),
 (39443,'PARAFUSO DRYWALL LB 4,2X13MM','UN','MATERIAL'),
 (20111,'MASSA DE REJUNTE PARA DRYWALL','KG','MATERIAL'),
 (37595,'FITA PAPEL MICROPERFURADA P/ JUNTAS','M','MATERIAL')]
st.executemany("INSERT INTO insumos VALUES (?,?,?,?)", fixture_insumos)
st.executemany("INSERT INTO precos_insumos VALUES (?,?,?,?,?)",
 [(c,'SP','2026-06-01','NAO_DESONERADO',p) for c,p in
  [(88278,26.90),(88316,20.10),(10774,29.80),(39443,0.31),(20111,4.60),(37595,0.38)]])
st.executemany("INSERT INTO composicao_insumos VALUES (96359,?,?)",
 [(88278,0.606),(88316,0.303),(10774,2.10),(39443,30.0),(20111,0.90),(37595,3.00)])
st.commit()

# ---- 2. PONTE: staging → nosso schema (a parte que seria produção) ----
db = sqlite3.connect("lsf_base.db"); db.execute("PRAGMA foreign_keys=ON")
fonte_sinapi = db.execute("SELECT id FROM fonte WHERE sigla='SINAPI'").fetchone()[0]
db.execute("INSERT OR IGNORE INTO data_base (fonte_id,referencia,uf,desonerado,publicado_em) VALUES (?,?,?,?,?)",
           (fonte_sinapi,'2026-06','SP',0,'2026-06-15'))
db_id = db.execute("SELECT id FROM data_base WHERE fonte_id=? AND referencia='2026-06' AND uf='SP'",(fonte_sinapi,)).fetchone()[0]

tipo_map = {'MAO_DE_OBRA':'MO','MATERIAL':'MAT','EQUIPAMENTO':'EQP'}
for cod,desc,un,clas in st.execute("SELECT * FROM insumos"):
    db.execute("INSERT OR IGNORE INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade) VALUES (?,?,?,?,?)",
               (fonte_sinapi,str(cod),desc,tipo_map.get(clas,'MAT'),un))
for cod,uf,dt,reg,preco in st.execute("SELECT * FROM precos_insumos"):
    iid = db.execute("SELECT id FROM insumo WHERE fonte_id=? AND codigo_fonte=?",(fonte_sinapi,str(cod))).fetchone()[0]
    db.execute("INSERT OR IGNORE INTO insumo_preco (insumo_id,data_base_id,preco,confianca) VALUES (?,?,?,'real')",(iid,db_id,preco))
comp_id = db.execute("SELECT id FROM composicao WHERE fonte_id=? AND codigo_fonte='96359'",(fonte_sinapi,)).fetchone()[0]
for pai,filho,coef in st.execute("SELECT * FROM composicao_insumos"):
    iid = db.execute("SELECT id FROM insumo WHERE fonte_id=? AND codigo_fonte=?",(fonte_sinapi,str(filho))).fetchone()[0]
    db.execute("INSERT INTO composicao_item (composicao_id,item_tipo,item_id,coeficiente) VALUES (?,?,?,?)",(comp_id,'INSUMO',iid,coef))
db.commit()

# ---- 3. PROVA: a view agora precifica a composição SINAPI ----
r = db.execute("SELECT codigo_fonte,descricao,ROUND(custo_unitario,2),confianca FROM vw_custo_composicao WHERE composicao_id=?",(comp_id,)).fetchone()
assert r and r[2] and r[2]>50, r
print(f"PONTE OK ✓  SINAPI {r[0]} '{r[1][:45]}...' → R$ {r[2]}/m² [{r[3]}] via view")
n = db.execute("SELECT COUNT(*) FROM insumo WHERE fonte_id=?",(fonte_sinapi,)).fetchone()[0]
print(f"            {n} insumos SINAPI integrados, preços 'real' na data-base 2026-06/SP")
