# Correções do code review do branch fase2-gerador-estrutura

**Data:** 2026-07-15
**Origem:** revisão multi-agente (8 ângulos × verificação individual) do diff `main...HEAD`.
22 candidatos verificados → 21 CONFIRMED, 1 REFUTED. Este plano corrige os 9 achados
mecânicos. **Fora de escopo (decisão humana pendente):** a junta de painel a 0,15 m da
lateral do vão (`_panelizar`, `estrutura.py:245`) é fiel ao v7 mas viola a regra de 30 cm
do CLAUDE.md e ignora `junta_folga_vao_m=0.30` do seed — corrigir quebra o oráculo do
aceite; manter viola a física declarada. Não tocar até o humano decidir.

## Global Constraints

> - **Licenças**: MIT/Apache/BSD → pode embutir. GPL (AutoSINAPI, TF2DeepFloorplan) → só em processo/container isolado, nenhuma linha no código proprietário. Sem licença (Raster-to-Graph, Skylark, bidwright) → código PROIBIDO, só conceitos. Dependência nova exige licença verificada e registrada em docs/04.
> - **Idioma**: nomes de domínio (tabelas, entidades, funções de negócio) em **português** — `parede`, `vao`, `custo_composicao`, `quantitativo`. Código de infraestrutura em inglês. Isto é convenção do projeto, não descuido.
> - **Confiança e ausência**: todo número derivado carrega `origem` e confiança (`real|estimado|parametrico`), propagada pela PIOR dos inputs via rank numérico, nunca por `MIN()` de string (D4). Dado ausente é `CustoIndisponivel`/pendência — nunca zero, nunca custo parcial (D4.1).
> - **Testes**: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/` — suíte inteira, verde, antes de cada commit. Os spikes em `tests/spikes_validacao.py` são regressão: spike quebrado = commit errado.
> - **Intocáveis**: não editar `assets/calc-...v7.html` (referência histórica) nem `db/lsf_base.db` na mão — schema/seed/migração + `db/build_db.py`.
> - **Regra de engenharia**: ao mexer em cargas/fundação/vento, anotar a referência normativa no código (`origemRegra`).

**Regra de execução deste plano:** as tasks rodam em agentes PARALELOS sobre a mesma
árvore. Nenhum agente commita; cada um roda apenas os testes dos arquivos que tocou
(`pytest tests/test_<área>.py`). O orquestrador roda a suíte inteira ao final e faz os
commits (suíte verde antes de cada um). Arquivos por task são DISJUNTOS — não tocar em
arquivo de outra task.

### Task 1: Parser pt-BR de quantidade + round-trip do formulário + origem_regra + árvore profunda

**Files:** `app/rotas/quantitativos.py`, `app/templates/_linha_quantitativo.html`, `tests/test_app_quantitativos.py`

Três achados no mesmo arquivo de rota (por isso uma task só):

**(a) `_numero_ptbr` corrompe entrada com ponto decimal (10× por dígito) e o re-salvar
sem editar multiplica por 10.** Hoje: `float(texto.replace('.','').replace(',','.'))` →
`'1500.5'`→15005.0; e o template renderiza `value="31345.0"`, que re-parseia como 313450.
Regra nova (validação por regex, ambos formatos aceitos, erro 400 no resto):
- `^\d{1,3}(\.\d{3})*(,\d+)?$` → pt-BR: remove pontos, vírgula→ponto (`'1.500,5'`→1500.5; `'1.500'`→1500).
- senão `^\d+(,\d+)?$` → vírgula decimal simples (`'31345,5'`).
- senão `^\d+(\.\d+)?$` → float puro (`'1500.5'`→1500.5; `'1.5'`→1.5).
- qualquer outra coisa → erro de formulário 400 (mesmo caminho do valor negativo).
Ambiguidade `'1.500'`: interpretação pt-BR ganha (UI é pt-BR) — documentar no docstring.
E o template passa a renderizar em pt-BR para o round-trip ser estável: filtro/format que
emite `31345` (inteiro sem casa morta) ou `31345,5` — NUNCA ponto decimal. Atenção ao
falsy-zero existente (`{{ item.quantidade or '' }}` esconde quantidade 0 legítima):
testar `quantidade is not none` no template.
Testes: round-trip salvar-sem-editar preserva o valor exato; `'1.500,5'`, `'1500.5'`,
`'1,5'`, `'1.5'`, `'1.500'` parseiam como especificado; lixo → 400; quantidade 0 renderiza `0`.

**(b) DO UPDATE não cobre `origem_regra`**: edição manual de linha derivada pelo gerador
mantém proveniência 'gerador de estrutura F2.1…' obsoleta. Acrescentar `origem_regra` ao
INSERT (valor NULL para lançamento manual) e ao DO UPDATE (`origem_regra=excluded.origem_regra`).
Teste: gravar linha com origem_regra de gerador direto no banco, editar via POST, conferir
origem='MANUAL' E origem_regra IS NULL.

**(c) `_arvore` só enxerga folha de profundidade 2**: folha `'03.01.02'` (formato
documentado na migração 001) fica invisível e inquantificável. Corrigir subindo a cadeia
`pai_id` até a macroetapa (raiz) para anexar QUALQUER folha, exibindo o código completo.
Teste: inserir folha de profundidade 3 no arranjo e conferir que aparece na tela e aceita
quantitativo.

### Task 2: Sessão expirada em requisição htmx — HX-Redirect em vez de página de login no <tr>

**Files:** `app/auth.py`, `tests/test_auth.py`

Hoje `redirecionar_ao_login` devolve 303→/login para tudo; o XHR do htmx segue o
redirect e faz outerHTML-swap da página de login inteira dentro do `<tr>`. Corrigir:
quando o request traz o header `HX-Request`, responder `401` (ou 200 vazio, conferir no
htmx.min.js vendored qual o comportamento com HX-Redirect em 401 — htmx 1.x processa
HX-Redirect em qualquer resposta) com header `HX-Redirect: /login`; sem o header,
comportamento atual (303). Teste: POST com header `HX-Request: true` e sessão ausente →
resposta carrega `HX-Redirect: /login` e o corpo NÃO contém o form de login; POST sem o
header → 303 como hoje.

### Task 3: Gerador — peitoril padrão da janela + guarda do derivar_quantitativos

**Files:** `src/lsf/geradores/estrutura.py`, `db/migrations/007_vao_peitoril_null.sql`, `tests/test_gerador_estrutura.py`, `tests/test_migracao_007.py` (novo)

**(a) Janela sem peitoril vira porta (sill=0) e subestima kg.** O v7 faz
`a.peitoril ?? R.peitorilPadrao` (nullish: 0 explícito é respeitado; ausente usa 1,0 m).
Nosso schema tem `peitoril_m REAL NOT NULL DEFAULT 0`, que confunde "não informado" com 0.
Migração 007: recriar `vao` com `peitoril_m REAL NULL DEFAULT NULL` (SQLite não altera
coluna: CREATE nova + INSERT SELECT + DROP + RENAME, dentro da disciplina do build —
`PRAGMA foreign_key_check` já é feito pelo `_aplicar`). ATENÇÃO: dados existentes com 0
viram... 0 mesmo (não há como distinguir retroativamente; anotar na migração). No gerador:
`peitoril is None → _regra(R, 'peitoril_padrao_m')` (a regra JÁ está no seed, linha ~298,
`origem_regra` v7 peitorilPadrao); 0 explícito continua 0. Testes: janela sem peitoril
gera peitoril a 1,0 m + cripples inferiores (comparar kg > kg da mesma janela sill=0);
janela com peitoril_m=0 explícito segue como hoje; regra ausente no banco → exceção
(dado ausente é erro), não default silencioso em código.

**(b) `derivar_quantitativos` sobrescreve MANUAL/'real' com PARAMETRICO/'estimado'.**
Guardar: o DO UPDATE só se aplica se a linha existente for PARAMETRICO —
`ON CONFLICT ... DO UPDATE SET ... WHERE quantitativo.origem = 'PARAMETRICO'`.
Se a linha existente é MANUAL/TAKEOFF, preservá-la e devolver
`{"kg_comprado": ..., "confianca": ..., "gravado": False, "preservado": "MANUAL"}`
(o chamador decide alertar). Testes: linha MANUAL preexistente não muda e o retorno
sinaliza `gravado=False`; linha PARAMETRICO é substituída como hoje; projeto sem linha
grava normal (`gravado=True`).

### Task 4: build_db — adoção não pode ledgerar script revertido pela metade

**Files:** `db/build_db.py`, `tests/test_build_db.py`

Hoje: se QUALQUER statement de um script estrutural falha com 'already exists', o script
INTEIRO é revertido e mesmo assim ledgerado como aplicado — os statements restantes nunca
executam (banco legado parcial fica permanentemente quebrado; só `--recriar` salva).
Corrigir a semântica de `_aplicar`/`_aplicar_ou_adotar` para tolerância POR STATEMENT:
statement que falha com estrutura-já-existente é PULADO e os demais EXECUTAM; qualquer
outro erro → rollback + exceção (comportamento atual). Ao final: `PRAGMA foreign_key_check`
(já existe), commit, ledger. "Adotar" passa a significar "todo statement ou aplicou ou já
existia". Testes: (1) banco que já tem UMA tabela de um script multi-objeto → build cria
as demais e ledgera; (2) erro que NÃO é 'already exists' no meio do script → rollback
completo, nada ledgerado, exceção propaga; (3) idempotência: rodar 2× continua ok;
(4) os testes existentes de adoção seguem verdes.

### Task 5: CLI carregar_orcamento_v7 — ordem schema → migrações → seed

**Files:** `tools/carregar_orcamento_v7.py`, `tests/test_carregar_v7_cli.py` (novo)

O `main()` ainda aplica seed ANTES das migrações (ordem antiga); o seed hoje depende das
migrações (perfil 'laminado' exige o CHECK relaxado da 006; ON CONFLICT da 003; tabelas
da 001/006) → o CLI documentado crasha com IntegrityError. Corrigir a ordem no `main()`
para a mesma do `db/build_db.py` e do fixture `con` (schema → migrações ordenadas → seed).
Melhor ainda: extrair/usar um helper único se isso não exigir tocar arquivo de outra task
(build_db é da Task 4 — NÃO tocar; duplicar a ordem correta aqui e deixar a unificação
para depois é aceitável). Teste novo: `main()`/a montagem in-memory do CLI constrói sem
exceção e a conferência roda contra a fixture.

### Task 6: Oráculo v7 — perfil desconhecido é erro, não 0 kg

**Files:** `tools/extrair_estrutura_v7.mjs`, `tests/test_fixture_estrutura.py`

`kg += p.comp * (LSF_DB.perfis[p.perfil]?.massaKgM || 0)` (linhas ~106 e ~124): perfil
fora de `LSF_DB.perfis` contribui 0 kg silenciosamente para a fixture do aceite. Trocar
por guarda fail-fast: perfil ausente → `throw new Error(...)` nomeando o perfil e a
parede. NÃO regenerar a fixture (verificação empírica já provou que a atual está íntegra:
kg 7737/11135 reproduzidos com guarda). Acrescentar em `tests/test_fixture_estrutura.py`
um teste que confere que todo perfil citado na fixture existe em `perfil_lsf` no banco
(guarda equivalente do lado Python).

## Critério de aceite do plano

1. Suíte inteira verde (incluindo spikes e os testes novos).
2. Achados 1–4 e 6–10 do review fechados; achado 5 (junta 0,15 m) documentado como
   decisão pendente — nenhuma linha de `_panelizar` alterada.
3. Aceite parcial F2.1 (`tests/test_aceite_estrutura_v7.py`) continua verde com a MESMA
   fixture (oráculo não regenerado).
4. Nenhum arquivo intocável alterado.
