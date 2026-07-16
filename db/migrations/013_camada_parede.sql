-- Migração 013 — composição de camadas por tipo de parede (Fase 2, estágio 3).
--
-- O peso próprio de uma parede é a soma das suas camadas. QUAIS camadas é
-- conhecimento de obra (parede externa leva cimentícia + membrana; interna leva
-- gesso dos dois lados), não algoritmo — então mora no banco, como o
-- verga_escalonamento e o laje_escalonamento.
--
-- O spike 4 tinha essa lista chumbada no meio do script: perfis + OSB +
-- cimentícia + gesso + lã + membrana. Generalizar o spike é, antes de tudo,
-- tirar a lista do código.

CREATE TABLE camada_parede (
  id INTEGER PRIMARY KEY,
  tipo TEXT NOT NULL CHECK (tipo IN ('externa','interna')),
  material TEXT NOT NULL REFERENCES peso_camada(material),
  faces INTEGER NOT NULL DEFAULT 1 CHECK (faces IN (1,2)),  -- gesso interno: 2 faces
  origem TEXT,
  UNIQUE (tipo, material)
);
