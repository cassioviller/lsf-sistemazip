-- Migração 009 — escalonamento de perfil da laje (par viga + bloqueador).
--
-- No v7 (gerarPecasLaje) o par era literal no código:
--   perfV = vaoEf > 4,0 ? 'Ue250#2.00' : 'Ue200#1.25'
--   perfB = perfV.startsWith('Ue250') ? 'U252#1.25' : 'U202#0.95'
-- com o comentário "derivado listas 1L: pares reais Ue200+U202#0.95 / Ue250+U252#1.25".
--
-- Isso é CONHECIMENTO de obra, não algoritmo: mora no banco, como o
-- verga_escalonamento. O par `guia_de` genérico (Ue250→U252) NÃO serve aqui —
-- ele elege U252#2.00 pela espessura do montante, e a lista 1L usa U252#1.25.
-- `faixa_ate_m` é o teto do vão efetivo da faixa (a última faixa cobre o resto).

CREATE TABLE laje_escalonamento (
  id INTEGER PRIMARY KEY,
  faixa_ate_m REAL NOT NULL UNIQUE,
  perfil_viga TEXT NOT NULL,
  perfil_bloqueador TEXT NOT NULL,
  origem TEXT
);
