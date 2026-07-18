-- Migração 012 — pendências de motor (Fase 2).
--
-- Uma pendência é um fato produzido por um MOTOR que diz "este número existe, mas
-- a solução por trás dele não fecha". Nasce em `gerar_estrutura` (vão que reprova
-- na verificação, furo em viga, peça fora do envelope) e precisa chegar ao gate de
-- publicação: alerta que morre no retorno é disclaimer morto, e o CLAUDE.md manda
-- gate BLOQUEAR, não avisar.
--
-- Por que bloquear e não carimbar (como a sondagem pendente faz): a própria 109
-- mostra o preço do erro. O gerador diz que as duas lajes exigem viga laminada 1VG
-- + pilares 1AL, a obra FOI construída com eles, e o orçamento de referência não
-- tem linha para nenhum dos dois. O kg que sai é PROVISÃO em perfil LSF; vender
-- isso como preço fechado é o "escopo vazado = prejuízo" do CLAUDE.md acontecendo
-- no projeto de referência.
--
-- `motor` permite re-derivar sem apagar pendência de outro motor (a fundação, na
-- Fase 3, escreverá aqui também).

CREATE TABLE pendencia (
  id INTEGER PRIMARY KEY,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id),
  motor TEXT NOT NULL,                 -- 'estrutura', 'fundacao'...
  mensagem TEXT NOT NULL,
  UNIQUE (projeto_id, motor, mensagem)
);

CREATE INDEX idx_pendencia_projeto ON pendencia (projeto_id);
