# Plano de Desenvolvimento — Sistema de Orçamento e Cronograma Físico-Financeiro para Obras Turn-Key em LSF

**Versão:** 1.0 · **Data:** 08/07/2026 · **Responsável:** Cássio (Veks Engenharia)

---

## 1. Visão e escopo

O sistema recebe como entrada mínima um projeto arquitetônico (DXF ou desenho de paredes em planta) e produz, de ponta a ponta: quantitativos derivados por cadeia de inferência física, orçamento com base SINAPI + composições próprias, cronograma físico com caminho crítico (CPM) e curva S físico-financeira. Ele opera em dois modos sobre a mesma estrutura — **paramétrico** (estimativa rápida para proposta) e **executivo** (quantitativo de takeoff para contrato) — e permite migração item a item entre eles.

**Está no escopo:** pré-dimensionamento para fins de orçamento (estrutura LSF, fechamentos, fundação), precificação com BDI decomposto (padrão TCU), sequenciamento e CPM, curva S, relatórios (proposta comercial, planilha analítica, dashboard).

**Está fora do escopo (e deve permanecer explícito no produto):** projeto estrutural executivo, verificação de vento/flambagem/ligações, projeto de fundação com sondagem, ART/RRT. O sistema emite *pré-dimensionamento*, nunca projeto — os gates da Fase 3 garantem que isso fique visível ao usuário e ao cliente final.

---

## 2. Decisões de arquitetura (travadas)

Estas decisões já foram tomadas e não devem ser reabertas sem motivo forte, pois todo o plano depende delas.

**D1 — EAP única como espinha dorsal.** Orçamento e cronograma leem a mesma EAP. Cada item carrega composição de custo (orçamento) e produtividade + precedências (cronograma). Isso garante que a curva S feche por construção.

**D2 — Tabela `quantitativo` como ponto de convergência.** Os modos paramétrico e executivo diferem apenas na *origem* da quantidade (`PARAMETRICO | TAKEOFF | MANUAL`). Todo o pipeline a jusante é idêntico. A migração proposta → contrato é a substituição gradual de linhas paramétricas por linhas de takeoff.

**D3 — Cadeia de inferência física para o modo paramétrico.** Arquitetônico → extração de paredes → geração de estrutura (peças, kg de aço, m² de fechamento) → takedown de cargas → pré-dimensionamento de fundação → mapeamento SINAPI. Cada estágio deriva o próximo por física + regras normativas (NBR 15758, NBR 6120).

**D4 — Confiança propagada.** Todo dado derivado carrega etiqueta de confiança (`real | estimado | parametrico`) e proveniência da regra (`origemRegra`). Cada estágio herda a pior confiança de seus inputs. Itens de baixa confiança são exibidos como faixa (±%), não valor seco.

**D5 — Base de conhecimento versionada por data-base.** Insumos, composições, produtividades e regras têm versão e data-base. Cada projeto trava uma versão. Orçamentos antigos nunca mudam sozinhos.

**D6 — Motores como funções puras.** Orçamento, cronograma e curva S são módulos que leem o banco e devolvem números, sem acoplamento ao framework web. Testáveis isoladamente.

**D7 — SINAPI como camada de mapeamento, não de lógica.** Onde o SINAPI não representa LSF (montagem de painel, parafusamento), entram composições próprias no mesmo esquema. A tabela de mapeamento `item_derivado → codigo_composicao` é dado, não código.

**D8 — Stack inicial.** Python (motores) + SQLite (migração para Postgres quando necessário) + saídas em HTML (dashboard), planilha e docx/PDF na identidade Veks. Reaproveitar padrões já existentes: leitor DXF (obra 109.1506), banco de regras versionado (calc-parede-lsf), `LSF_DB` e regras do v7 steel.

---

## 3. Riscos e obstáculos previsíveis — com mitigação

| # | Risco / obstáculo | Impacto | Mitigação |
|---|---|---|---|
| R1 | SINAPI não cobre bem serviços LSF (montagem de painel, steel deck, fechamentos específicos) | Orçamento distorcido nos itens de maior peso | Composições próprias desde a Fase 1, calibradas contra obras reais da Veks (109.1506, Baias Kabod). SINAPI cobre o que cobre bem: fundação, instalações, acabamentos |
| R2 | Extração automática de paredes do DXF é frágil (camadas inconsistentes, blocos, escalas) | Estágio 1 da cadeia trava o resto | DXF é otimização, não pré-requisito: o caminho principal na Fase 2 é entrada manual/assistida de paredes (segmentos + vãos), como o v7 já modela. DXF entra como acelerador na Fase 5 |
| R3 | Solo desconhecido na fase de proposta | Fundação sub ou superdimensionada | Parâmetro de classe de solo (faixas SPT → tensão admissível) com default conservador + flag "sondagem pendente" que rebaixa a confiança de toda a fundação e aparece na proposta |
| R4 | Responsabilidade técnica: cliente tratar pré-dimensionamento como projeto | Risco jurídico e de execução | Gates formais: relatório sempre carrega o disclaimer e o checklist do que precisa virar projeto (sondagem, verificação estrutural, ART) antes de contrato. Alertas por severidade viram bloqueio de fase |
| R5 | Preços SINAPI mudam mensalmente; composições próprias evoluem | Orçamento antigo muda ao reabrir; perda de rastreabilidade | Versionamento por data-base (D5) + rotina mensal de importação SINAPI que cria nova versão sem tocar as anteriores |
| R6 | Produtividades próprias inexistentes ou chutadas | Cronograma irreal, caminho crítico errado | Começar com produtividades de referência de mercado marcadas `estimado`; instrumentar as obras em andamento para coletar rendimento real e substituir gradualmente (mesmo padrão de migração da D2) |
| R7 | Escopo vazado em turn-key (etapa esquecida no preço fechado) | Prejuízo direto | Gate de completude: checklist por macroetapa da EAP que alerta/bloqueia quando um grupo fica sem quantitativo ("cobertura zerada", "instalações ausentes") |
| R8 | Scope creep no desenvolvimento (querer tudo de uma vez) | Sistema nunca entra em produção | Fases com critério de aceite; cada fase entrega algo usável sozinho. Não iniciar fase N+1 sem aceite da fase N |
| R9 | Takedown de cargas sem validação | Fundação errada no orçamento | Validar o motor de cargas contra pelo menos 2 obras com projeto estrutural real (comparar carga por parede e consumo de fundação); tolerância-alvo ±15% no paramétrico |
| R10 | Duplicação com o SIGE (EnterpriseSync-1) | Retrabalho e dois cadastros | Sistema nasce standalone (decisão do usuário), mas com IDs e JSON de cronograma no formato já usado pelo SIGE, permitindo integração futura sem migração |

---

## 4. Modelo de dados (resumo de referência)

**Base de conhecimento (versionada):** `insumo` (código, tipo MAT/MO/EQP, unidade, custo, fonte SINAPI/próprio, data-base) · `composicao` + `composicao_item` (receita de insumos com coeficientes) · `eap_item` (hierarquia, unidade, composição) · `produtividade` (rendimento, equipe) · `precedencia` (tipo TI/II/TT, lag) · `regra_parametrica` (expressão quantidade = f(parâmetros)) · `peso_camada` (kg/m² por material de fechamento) · `classe_solo` (faixa SPT → tensão admissível) · `mapeamento_sinapi` (item derivado → código composição) · `parametros_globais` (BDI decomposto, encargos, contingência).

**Projeto (instância):** `projeto` (dados da obra, data-base travada) · `parede` (segmento, vãos, portante S/N, confiança) · `quantitativo` (eap_item, quantidade, **origem**, confiança) · `carga_parede` (kN/m, componentes) · `fundacao_predim` (tipo, dimensões, consumos) · `projeto_atividade` (duração, início, fim, folga, crítica) · `alerta` (severidade, mensagem, gate).

---

## 5. Fases de desenvolvimento

Cada fase tem entregável usável e critério de aceite. A ordem foi desenhada para gerar valor cedo e para que nenhuma fase dependa de algo ainda não construído.

### Fase 0 — Fundação de dados (a mais importante e a menos glamourosa)

Montar o esquema SQL completo, importador SINAPI (uma data-base de referência), cadastro das composições próprias LSF dos ~8 grupos da EAP e migração do `LSF_DB` do v7 (perfis, massas, regras NBR) para o banco de regras versionado.

**Entregável:** banco populado + script de importação SINAPI reproduzível.
**Aceite:** consultar o custo unitário de qualquer composição dos 8 grupos e obter valor com fonte e data-base rastreáveis.
**Cuidado:** resistir à tentação de começar pelos motores. Sem esta fase, tudo em cima vira número sem lastro.

### Fase 1 — Motor de orçamento (modo manual primeiro)

Motor puro: quantitativo (digitado manualmente) × custo unitário de composição → custo direto por item da EAP → agregação → BDI decomposto → preço de venda. Saída: planilha analítica + resumo por macroetapa.

**Entregável:** orçamento executivo funcional com entrada manual de quantitativos.
**Aceite:** reproduzir um orçamento real já feito pela Veks com desvio ≤ 2% (diferenças explicáveis por arredondamento).
**Por que antes do paramétrico:** valida composições e BDI com quantitativos conhecidos, isolando erros. Se o paramétrico viesse primeiro, erro de regra e erro de preço ficariam indistinguíveis.

### Fase 2 — Cadeia de inferência paramétrica (estágios 1–3)

Extrator de paredes com **entrada manual/assistida** (segmentos, vãos, pé-direito, classificação portante por heurística), gerador de estrutura (porte do v7 para Python: peças, kg de aço por parede, m² de fechamento por camada) e o **motor de takedown de cargas** — o único elo que não existe em nenhum código atual. Escreve na tabela `quantitativo` com `origem=PARAMETRICO` e confiança propagada.

**Entregável:** do desenho de paredes ao quantitativo completo de estrutura + fechamentos, com cargas por parede.
**Aceite:** kg de aço e m² de fechamento da obra 109.1506 reproduzidos com desvio ≤ 10% em relação ao v7; cargas por parede validadas contra 1 obra com projeto estrutural (R9).

### Fase 3 — Fundação + gates

Motor de pré-dimensionamento de fundação (classe de solo + carga linear → radier vs. sapata corrida → volumes de concreto, aço CA, forma, escavação), mapeador SINAPI desses consumos e implantação dos gates: completude turn-key (R7) e checklist jurídico-técnico (R4), com a flag de sondagem pendente (R3).

**Entregável:** pré-orçamento paramétrico completo (estrutura + fechamento + fundação) a partir do arquitetônico, com faixas de confiança e gates visíveis.
**Aceite:** consumo de fundação validado contra obra real com tolerância ±15%; gate bloqueia geração de proposta com macroetapa zerada.

### Fase 4 — Motor de cronograma + curva S

Durações (quantidade ÷ produtividade × equipe), rede de precedências, CPM (passagem direta/inversa, folgas, caminho crítico), Gantt, distribuição financeira por item (linear e ponderada — aço adiantado na estrutura) e curva S física + financeira.

**Entregável:** cronograma físico-financeiro completo derivado do mesmo orçamento.
**Aceite:** caminho crítico coerente com a sequência LSF real (fundação → painéis → fechamento externo → instalações → isolamento + drywall → acabamento); curva S financeira fecha com o total do orçamento ao centavo.

### Fase 5 — Saídas, DXF e migração de modo

Relatórios finais (proposta comercial em docx/PDF na identidade Veks, dashboard HTML, planilha), leitor DXF como acelerador do estágio 1 (aproveitando o módulo da 109.1506) e o fluxo de migração item a item PARAMETRICO → TAKEOFF com histórico.

**Entregável:** ciclo completo proposta → contrato no sistema.
**Aceite:** uma obra real conduzida do arquitetônico à proposta assinável sem sair do sistema.

---

## 6. Validação e calibração contínua

O sistema só é confiável se for calibrado contra realidade. Rotina permanente: toda obra executada alimenta de volta (a) produtividades reais por serviço (substitui `estimado` por `real`), (b) desvio orçado × realizado por item da EAP e (c) ajuste de coeficientes das regras paramétricas. As obras 109.1506 (Máximo Tintas) e Baias Kabod são os primeiros casos de calibração, por já terem dados levantados.

## 7. Backlog imediato (primeiras 2 semanas)

1. Esquema SQL completo (base de conhecimento + projeto) com migrações.
2. Importador SINAPI (planilha oficial → tabelas `insumo`/`composicao`) para uma data-base.
3. Portar `LSF_DB` do v7 (perfis, massas kg/m, regras de modulação NBR 15758) para o banco.
4. Cadastrar tabela `peso_camada` (OSB, placa cimentícia, gesso, lã, telha) e `classe_solo`.
5. Levantar as composições próprias LSF que o SINAPI não cobre (lista + coeficientes de referência).
6. Motor de orçamento (Fase 1) com teste de reprodução de um orçamento Veks real.

---

*Regra de ouro do plano: nenhuma fase começa sem o aceite da anterior, e todo número derivado carrega origem e confiança. É isso que impede o sistema de "esbarrar" — os obstáculos foram movidos para dentro do modelo como flags, gates e faixas, em vez de ficarem escondidos até a obra.*
