# -*- coding: utf-8 -*-
"""PONTE Rota A: staging AutoSINAPI (Postgres em prod; SQLite aqui) → lsf_base.db

Upstream: LAMP-LUCAS/AutoSINAPI · GPLv3 declarada no README (badge + §Licença; sem
arquivo LICENSE na raiz — pedir ao upstream) · PIN: commit 0020609 (main, 09/07/2026).
Nenhuma linha deles entra aqui: a fronteira é o banco de staging (política CLAUDE.md).

Nomes de staging conforme docs/DataModel.md do upstream: `insumos`,
`precos_insumos_mensal` (PK composta insumo+uf+data+regime), `composicao_insumos`.
O DataModel manda recarregar a estrutura das composições INTEIRA a cada mês — por
isso a ponte apaga e regrava a analítica de cada composição presente no staging
(DELETE+INSERT), e faz upsert de preços. Reexecutar a ponte é seguro (idempotente);
a versão anterior duplicava `composicao_item` e inflava o preço a cada execução.
"""
import pathlib
import sqlite3

TIPO_MAP = {"MAO_DE_OBRA": "MO", "MATERIAL": "MAT", "EQUIPAMENTO": "EQP"}

FIXTURE_INSUMOS = [  # códigos reais SINAPI, valores de fixture p/ teste da ponte
    (88278, "MONTADOR DE ESTRUTURA METÁLICA COM ENCARGOS", "H", "MAO_DE_OBRA"),
    (88316, "SERVENTE COM ENCARGOS COMPLEMENTARES", "H", "MAO_DE_OBRA"),
    (10774, "CHAPA DE GESSO DRYWALL ST 12,5MM", "M2", "MATERIAL"),
    (39443, "PARAFUSO DRYWALL LB 4,2X13MM", "UN", "MATERIAL"),
    (20111, "MASSA DE REJUNTE PARA DRYWALL", "KG", "MATERIAL"),
    (37595, "FITA PAPEL MICROPERFURADA P/ JUNTAS", "M", "MATERIAL"),
]
FIXTURE_PRECOS = [(88278, 26.90), (88316, 20.10), (10774, 29.80),
                  (39443, 0.31), (20111, 4.60), (37595, 0.38)]
FIXTURE_ANALITICA_96359 = [(88278, 0.606), (88316, 0.303), (10774, 2.10),
                           (39443, 30.0), (20111, 0.90), (37595, 3.00)]


def criar_staging_fixture(st):
    """Simula as tabelas que o ETL do AutoSINAPI popula (nomes do DataModel.md)."""
    st.executescript("""
    DROP TABLE IF EXISTS insumos;
    DROP TABLE IF EXISTS precos_insumos_mensal;
    DROP TABLE IF EXISTS composicao_insumos;
    CREATE TABLE insumos (codigo INTEGER PRIMARY KEY, descricao TEXT, unidade TEXT, classificacao TEXT);
    CREATE TABLE precos_insumos_mensal (
      insumo_codigo INTEGER, uf TEXT, data_referencia TEXT, regime TEXT, preco_mediano REAL,
      PRIMARY KEY (insumo_codigo, uf, data_referencia, regime));
    CREATE TABLE composicao_insumos (composicao_pai_codigo INTEGER, insumo_filho_codigo INTEGER, coeficiente REAL,
      PRIMARY KEY (composicao_pai_codigo, insumo_filho_codigo));
    DROP TABLE IF EXISTS composicao_subcomposicoes;
    CREATE TABLE composicao_subcomposicoes (composicao_pai_codigo INTEGER, composicao_filho_codigo INTEGER, coeficiente REAL,
      PRIMARY KEY (composicao_pai_codigo, composicao_filho_codigo));
    """)
    st.executemany("INSERT INTO insumos VALUES (?,?,?,?)", FIXTURE_INSUMOS)
    st.executemany(
        "INSERT INTO precos_insumos_mensal VALUES (?,?,?,?,?)",
        [(c, "SP", "2026-06-01", "NAO_DESONERADO", p) for c, p in FIXTURE_PRECOS],
    )
    st.executemany("INSERT INTO composicao_insumos VALUES (96359,?,?)", FIXTURE_ANALITICA_96359)
    # 96114 (forro drywall) aninha a 96359: é o caso que prova o item_tipo='COMPOSICAO'.
    st.execute("INSERT INTO composicao_subcomposicoes VALUES (96114, 96359, 1.0)")
    st.commit()


PARAMSTYLE_POR_MODULO = {"sqlite3": "qmark", "psycopg": "pyformat",
                         "psycopg2": "pyformat"}


def _paramstyle_do_staging(st):
    """qmark (SQLite, o fixture e o dump) vs pyformat (psycopg, o staging real).

    Driver desconhecido é ERRO, não chute: adivinhar placeholder errado falha
    no meio do import mensal, com metade da analítica gravada.
    """
    declarado = getattr(st, "paramstyle", None)
    if declarado:
        return declarado
    modulo = type(st).__module__.split(".")[0]
    if modulo not in PARAMSTYLE_POR_MODULO:
        raise ValueError(
            f"driver de staging desconhecido ({modulo}): declare .paramstyle na"
            " conexão ou registre-o em PARAMSTYLE_POR_MODULO")
    return PARAMSTYLE_POR_MODULO[modulo]


def _adaptar(sql, paramstyle):
    """Consultas ao staging são escritas em qmark e traduzidas aqui.

    Em pyformat o '%' LITERAL precisa ser dobrado (o LIKE ?||'%' viraria
    placeholder para o psycopg) — por isso a ordem: escapa '%', depois troca '?'.
    """
    if paramstyle == "qmark":
        return sql
    return sql.replace("%", "%%").replace("?", "%s")


def executar_ponte(st, db, referencia="2026-06", uf="SP", regime="NAO_DESONERADO"):
    """staging → nosso schema. Idempotente: rodar N vezes = rodar 1 vez.

    - insumo: INSERT OR IGNORE (identidade estável por fonte+codigo)
    - insumo_preco: upsert (o upstream pode corrigir preço dentro do mesmo mês)
    - composicao_item: DELETE+INSERT da analítica de cada composição presente no
      staging, espelhando o reload mensal integral do DataModel.md do AutoSINAPI
    """
    paramstyle = _paramstyle_do_staging(st)

    def ler(sql, params=()):
        """Consulta o staging. Colunas SEMPRE nomeadas: o staging real traz
        sinapi_versao/etl_run_id além do que o fixture tem, e `SELECT *` com
        desempacotamento posicional estoura no primeiro arquivo da Caixa."""
        return st.execute(_adaptar(sql, paramstyle), params)

    db.execute("PRAGMA foreign_keys=ON")
    fonte_sinapi = db.execute("SELECT id FROM fonte WHERE sigla='SINAPI'").fetchone()[0]
    desonerado = 1 if regime == "DESONERADO" else 0
    db.execute(
        "INSERT OR IGNORE INTO data_base (fonte_id,referencia,uf,desonerado,publicado_em)"
        " VALUES (?,?,?,?,date('now'))",
        (fonte_sinapi, referencia, uf, desonerado),
    )
    db_id = db.execute(
        "SELECT id FROM data_base WHERE fonte_id=? AND referencia=? AND uf=? AND desonerado=?",
        (fonte_sinapi, referencia, uf, desonerado),
    ).fetchone()[0]

    def insumo_id(codigo):
        return db.execute(
            "SELECT id FROM insumo WHERE fonte_id=? AND codigo_fonte=?",
            (fonte_sinapi, str(codigo)),
        ).fetchone()[0]

    for cod, desc, un, clas in ler(
        "SELECT codigo, descricao, unidade, classificacao FROM insumos"
    ):
        db.execute(
            "INSERT OR IGNORE INTO insumo (fonte_id,codigo_fonte,descricao,tipo,unidade)"
            " VALUES (?,?,?,?,?)",
            (fonte_sinapi, str(cod), desc, TIPO_MAP.get(clas, "MAT"), un),
        )
    for cod, preco in ler(
        "SELECT insumo_codigo, preco_mediano FROM precos_insumos_mensal"
        " WHERE uf=? AND data_referencia LIKE ?||'%' AND regime=?",
        (uf, referencia, regime),
    ):
        db.execute(
            "INSERT INTO insumo_preco (insumo_id,data_base_id,preco,confianca)"
            " VALUES (?,?,?,'real')"
            " ON CONFLICT (insumo_id,data_base_id) DO UPDATE SET preco=excluded.preco",
            (insumo_id(cod), db_id, preco),
        )

    def composicao_id(codigo):
        """id da composição no NOSSO catálogo, ou None. Fora do catálogo é pulada,
        nunca inventada — vale igual para insumo-filho e composição-filha."""
        linha = db.execute(
            "SELECT id FROM composicao WHERE fonte_id=? AND codigo_fonte=?",
            (fonte_sinapi, str(codigo)),
        ).fetchone()
        return linha[0] if linha else None

    composicoes = sorted({r[0] for r in ler(
        "SELECT DISTINCT composicao_pai_codigo FROM composicao_insumos"
        " UNION SELECT DISTINCT composicao_pai_codigo FROM composicao_subcomposicoes")})
    for pai in composicoes:
        comp = composicao_id(pai)
        if comp is None:
            continue  # composição fora do nosso catálogo: pulada, não inventada
        # Reload mensal INTEGRAL da analítica (DataModel.md do upstream): apaga os
        # DOIS item_tipo. Filtrar só 'INSUMO' deixava o aninhamento acumular a cada
        # execução — o mesmo bug de duplicação que a ponte já corrigira p/ insumos.
        db.execute("DELETE FROM composicao_item WHERE composicao_id=?", (comp,))
        for filho, coef in ler(
            "SELECT insumo_filho_codigo, coeficiente FROM composicao_insumos"
            " WHERE composicao_pai_codigo=?", (pai,)
        ):
            db.execute(
                "INSERT INTO composicao_item (composicao_id,item_tipo,item_id,coeficiente)"
                " VALUES (?,'INSUMO',?,?)",
                (comp, insumo_id(filho), coef),
            )
        for filho, coef in ler(
            "SELECT composicao_filho_codigo, coeficiente FROM composicao_subcomposicoes"
            " WHERE composicao_pai_codigo=?", (pai,)
        ):
            filho_id = composicao_id(filho)
            if filho_id is None:
                continue  # subcomposição fora do catálogo: pulada, não inventada
            db.execute(
                "INSERT INTO composicao_item (composicao_id,item_tipo,item_id,coeficiente)"
                " VALUES (?,'COMPOSICAO',?,?)",
                (comp, filho_id, coef),
            )
    db.commit()
    return composicoes


def main():
    raiz = pathlib.Path(__file__).resolve().parents[1]
    st = sqlite3.connect(raiz / "db" / "autosinapi_stage.db")
    db = sqlite3.connect(raiz / "db" / "lsf_base.db")
    criar_staging_fixture(st)
    executar_ponte(st, db)
    executar_ponte(st, db)  # prova de idempotência no próprio CLI
    r = db.execute(
        "SELECT codigo_fonte, descricao, ROUND(custo_unitario,2), confianca"
        " FROM vw_custo_composicao WHERE codigo_fonte='96359'"
    ).fetchone()
    assert r and abs(r[2] - 99.55) < 0.01, f"custo divergente após 2 execuções: {r}"
    # Aninhamento: a view é de 1 nível e mentiria no pai — aqui basta provar que o
    # reload integral não duplicou o vínculo 96114→96359 nas 2 execuções.
    n = db.execute(
        "SELECT COUNT(*) FROM composicao_item ci JOIN composicao c ON c.id=ci.composicao_id"
        " WHERE c.codigo_fonte='96114' AND ci.item_tipo='COMPOSICAO'"
    ).fetchone()[0]
    assert n == 1, f"subcomposição duplicada no reload: {n} vínculos (esperado 1)"
    print(f"PONTE OK ✓ (2x, idempotente)  SINAPI {r[0]} '{r[1][:40]}...' → R$ {r[2]}/m² [{r[3]}]")
    print(f"  aninhamento ✓ 96114 → 96359 ({n} vínculo, item_tipo=COMPOSICAO)")


if __name__ == "__main__":
    main()
