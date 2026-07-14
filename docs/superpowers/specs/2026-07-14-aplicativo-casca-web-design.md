# Aplicativo LSF — casca web sobre os motores (spec de design)

**Data:** 2026-07-14 · **Origem:** brainstorming "aplicativo inteiro"
**Status:** aprovado nas seções; aguarda revisão do documento escrito

---

## 1. Problema

O sistema tem motor (Fase 1 aceita, desvio 0,00% vs. orçamento v7 da 109.1506), banco de
conhecimento versionado e relatórios CSV/HTML — mas **não tem aplicativo**. Não existe servidor,
tela nem sessão: tudo é função pura invocada por teste. Um orçamentista não consegue cadastrar
uma obra, lançar quantitativos, rodar o orçamento e entregar uma proposta sem escrever Python.

Esta spec projeta a **casca**: a camada web que opera os motores existentes e publica a proposta
para o cliente final.

## 2. Decisões desta sessão

| Decisão | Escolha |
|---|---|
| Escopo da sessão | Norte do aplicativo inteiro + primeira spec implementável |
| Cliente final | **Vê link vivo** (portal read-only por token), não só arquivo enviado |
| Sequência | **Casca primeiro**; Fase 2 (cadeia paramétrica) fica em espera |
| Camada web | **FastAPI + Jinja + htmx** (sem SPA, sem build step) |
| Proposta v1 | **Escopo + preço + gates**. Sem cronograma/curva S (são Fase 4) |
| Auth/deploy | Login interno próprio (scrypt + cookie assinado) · Replit · SQLite |

## 3. O norte: o aplicativo inteiro, decomposto

Seis subsistemas, na ordem de construção:

| # | Subsistema | O que faz | Depende de |
|---|---|---|---|
| 1 | Casca + projetos | login interno; CRUD de projeto (referência/UF/desonerado, classe de solo, sondagem) | Fase 1 ✓ |
| 2 | Quantitativos + orçamento | lançar quantidade MANUAL na folha da EAP; rodar motor; analítico com faixas ±%, pendências e macroetapas zeradas | Fase 1 ✓ |
| 3 | Proposta publicada | congelar versão; publicar em `/p/<token>`; cliente abre read-only | 1, 2 |
| 4 | Planta + cadeia paramétrica | entrada de planta (croqui/DXF), takedown, quantitativos PARAMETRICO | **Fase 2/3** |
| 5 | Cronograma + curva S | CPM; curva S na proposta | **Fase 4** |
| 6 | Panelizador + romaneio | kits de corte, saída de fábrica | **Fase 5** |

**Esta spec constrói 1–3.** Os subsistemas 4–6 são plugues numa casca que já existirá e já terá
sido usada em obra. Nenhum deles é tocado aqui, e por isso a casca **não atravessa gate de fase**:
a Fase 2 continua sendo a próxima fase de *motor*, declarada aceita por critério numérico próprio
(kg de aço com desvio ≤ 10%), independentemente do estado do app.

## 4. Persistência: correção do `build_db.py` (bloqueante)

`db/build_db.py:5` executa `db_path.unlink()` — apaga o banco e reconstrói do `schema` + `seed` +
migrações. Hoje isso é inofensivo (o banco é descartável; os testes montam bancos temporários).
Com projetos reais e propostas publicadas no mesmo arquivo, é **destrutivo**: atualizar a base de
conhecimento — o gesto que o `CLAUDE.md` sanciona para nova referência SINAPI ou nova composição —
apagaria todos os projetos e todas as propostas entregues a clientes.

**Decisão: migrações versionadas, um banco só.**

- `build_db.py` deixa de apagar. Passa a aplicar apenas as migrações pendentes, controladas por uma
  tabela `schema_migrations` (nome do arquivo + `aplicada_em`).
- `seed.sql` torna-se idempotente (UPSERT), podendo ser reaplicado sem duplicar conhecimento.
- Um flag explícito `--recriar` preserva o rebuild-do-zero que os testes já usam.

**Alternativas rejeitadas:**

- **Dois bancos (`conhecimento.db` + `instancia.db`) via ATTACH.** Separação conceitual mais limpa,
  mas o SQLite **não aplica foreign key entre bancos anexados**: `quantitativo.eap_item_id →
  eap_item.id` deixaria de ser FK declarada e viraria validação manual. Num sistema cuja regra de
  ouro é "dado ausente é erro, nunca zero" (D4.1), trocar integridade declarada por disciplina de
  código é o negócio errado.
- **Postgres agora.** D8 prevê a migração "quando doer". Não doeu. Trocar de banco no mesmo
  movimento em que se cria a primeira UI é assumir dois riscos onde cabe um. Gatilho registrado
  para reabrir: concorrência de escrita real, ou o arquivo virar gargalo.

## 5. Arquitetura

```
src/lsf/motores/*.py     ← função pura sobre o banco. NÃO importa FastAPI. Intocado (D6).
src/lsf/relatorios.py    ← função pura. Fonte dos templates.
app/
  main.py                FastAPI + montagem de rotas
  db.py                  conexão (PRAGMA foreign_keys=ON), dependência de request
  auth.py                sessão em cookie assinado; senha com scrypt (stdlib)
  servicos/              orquestração: chama motor, monta view-model, aplica gate
  rotas/                 projetos · quantitativos · orcamento · proposta · publico
  templates/             Jinja — herda identidade dos previews em docs/previews/
  static/                css Veks, htmx (vendored)
```

**Invariante de fronteira: `app/` não contém regra de engenharia.** Nenhum cálculo de custo, BDI,
carga ou confiança nasce ali. `app/servicos/` chama `custo_direto_projeto()` → `aplicar_bdi()` e
traduz o resultado para a tela. **Um número na UI que não veio de um motor é bug de arquitetura.**
É esse limite que permite o subsistema 4 plugar depois sem reescrever a casca.

Contratos já existentes, consumidos sem alteração:

- `custo_direto_projeto(con, projeto_id) -> OrcamentoDireto` (linhas, subtotais por macroetapa,
  total, pendências, `macroetapas_zeradas`)
- `carregar_parametros_bdi(con) -> ParametrosBDI` · `aplicar_bdi(orcamento, params) -> OrcamentoVenda`
- `relatorio_html(venda, faixa_pct)` · `relatorio_csv(venda, faixa_pct)`

### Dependências novas (licenças verificadas — registrar em `docs/04`)

| Pacote | Licença | Uso |
|---|---|---|
| FastAPI | MIT | rotas |
| Uvicorn | BSD-3 | servidor ASGI |
| Jinja2 | BSD-3 | templates |
| itsdangerous | BSD-3 | assinatura do cookie de sessão |
| python-multipart | Apache-2.0 | formulários |
| htmx (vendored em `static/`) | BSD-2 | interatividade sem build step |

Todas permissivas → podem ser embutidas. Nenhuma GPL, nenhuma sem licença.

## 6. Modelo de dados novo (migração 005)

Apenas dado de **instância**. Nada da base de conhecimento muda.

**`usuario`** — `id`, `email` (UNIQUE), `senha_hash` (scrypt), `nome`, `ativo`, `criado_em`.
Sem cadastro aberto: usuário nasce por migração/CLI.

**`proposta`** — `id`, `projeto_id` (FK), `versao` (UNIQUE por projeto), `token`
(`secrets.token_urlsafe(32)`, UNIQUE), `publicada_em`, `publicada_por` (FK usuario),
`snapshot_json` (o `OrcamentoVenda` serializado), `html` (página renderizada), `total_venda`,
`bdi_pct`, `status` (`ativa` | `revogada`).

**O snapshot é o coração.** `GET /p/<token>` serve o HTML congelado; **não recalcula**. Preço de
insumo que mude amanhã, coeficiente corrigido por migração futura — nada disso reescreve o que o
cliente recebeu. É o D5 levado ao limite: orçamento antigo não muda sozinho, nem por baixo.

**Revogar não apaga**: marca `revogada`, e o link passa a exibir "esta versão foi superada" em vez
de um valor obsoleto se passando por vigente.

## 7. Telas e rotas

```
/login
/projetos                      lista
/projetos/novo                 código, nome, cliente, referência, UF, desonerado,
                               classe de solo, sondagem pendente
/projetos/{id}                 resumo + estado dos gates + ação "orçar"
/projetos/{id}/quantitativos   árvore da EAP; input na folha; htmx recalcula o
                               subtotal da macroetapa sem recarregar a página
/projetos/{id}/orcamento       analítico: KPIs, faixas ±% (D4), pendências (D4.1),
                               medidor de completude turn-key (R7)
/projetos/{id}/publicar        pré-flight dos gates → cria proposta v(N+1)
/projetos/{id}/propostas       histórico de versões publicadas
/p/{token}                     público, read-only: escopo + preço + gates
```

## 8. Gates: bloqueiam, não avisam

Pré-flight de publicação, que **recusa** (HTTP 409 + lista do que falta):

- **Pendência de custo** (total `None`, via `CustoIndisponivel`) → recusa. Nunca publica custo parcial (D4.1).
- **Macroetapa zerada** (R7) → recusa. Escopo vazado em preço fechado é prejuízo; a tela mostra
  quais das 8 macroetapas estão vazias.
- **Sondagem pendente** → **não** bloqueia a publicação, mas carimba a proposta: a fundação sai com
  confiança rebaixada e o gate aparece como item aberto na página do cliente.

Superfície pública: token não enumerável (32 bytes), `noindex`; cookie `httponly`/`secure`/
`samesite=lax` apenas na área interna; disclaimers de pré-dimensionamento como bloco de primeira
classe, não rodapé.

## 9. Testes (TDD — vermelho pelo motivo certo, depois verde)

Comando: `export LD_LIBRARY_PATH=/nix/store/0gnnf8s259nn28s41zs4rhpbfqm148rm-gcc-11.4.0-lib/lib && .venv/bin/python -m pytest tests/`
Suíte inteira verde antes de **cada** commit; os 6 spikes seguem como regressão.

Novos testes, via `starlette.testclient`:

1. Publicar com macroetapa zerada → recusado (gate R7).
2. Publicar com pendência de custo → recusado (D4.1).
3. **Proposta congelada não se mexe**: publica → altera preço de insumo no banco → re-abre
   `/p/<token>` → mesmo valor.
4. `build_db.py` rodado duas vezes **preserva** projeto e proposta (a correção do `unlink()`).
5. Rota interna sem sessão → redireciona ao login; token inválido → 404; token revogado → página
   "versão superada".
6. Lançar quantitativo em agrupador da EAP → recusado (trigger `trg_quantitativo_so_em_folha`
   aflora como erro de formulário, não 500).

## 10. Fora de escopo (deliberado)

- Planta e cadeia paramétrica (Fase 2/3), cronograma e curva S (Fase 4), panelizador (Fase 5).
- PDF: o HTML é imprimível; PDF entra quando doer.
- **Edição de composições/insumos pela UI.** A base de conhecimento continua em `seed`/`migração`
  versionados no git, como o `CLAUDE.md` manda. O app escreve **apenas dado de instância**
  (projeto, quantitativo, proposta, usuario).

## 11. Consequência honesta a aceitar

A EAP tem hoje **5 folhas com composição**, cobrindo 3 das 8 macroetapas. A casca não inventa
catálogo. No dia em que ela subir, orçar uma obra real **baterá no gate R7** — e isso é o
comportamento **correto**, não uma falha do app.

Completar as composições dos 8 grupos (backlog `docs/02` §6.3) é uma trilha de **dados**, paralela
e independente: não bloqueia a construção da casca nem é bloqueada por ela.

## 12. Critério de aceite

Um orçamentista, sem escrever Python:

1. entra com login;
2. cadastra a obra 109.1506 (referência, UF, desonerado, solo);
3. lança os quantitativos MANUAL nas folhas da EAP;
4. vê o orçamento analítico com BDI, faixas ±% e o medidor de completude;
5. tenta publicar com macroetapa zerada e **é bloqueado**;
6. completa o escopo, publica a v1 e abre `/p/<token>` numa janela anônima;
7. o valor no banco muda; a proposta publicada **continua idêntica**.

Suíte inteira verde. Nenhuma linha de regra de engenharia dentro de `app/`.
