# Sistema de Orçamento e Cronograma LSF — Veks Engenharia

Pacote de partida gerado a partir da fase de planejamento validado (08/07/2026).
**Comece lendo o `CLAUDE.md`** — é a fonte de verdade; o Claude Code o lê automaticamente.

## Setup rápido
```bash
pip install ezdxf pytest            # deps atuais (MIT/livres)
python3 db/build_db.py              # constrói lsf_base.db do schema+seed
pytest tests/ -q                    # 6 spikes de regressão devem passar
```

## Primeira sessão no Claude Code
Abra esta pasta e use o conteúdo de `PROMPT_INICIAL.md` como primeira mensagem.

## Mapa
- `docs/01` plano v1 (fases, riscos R1-R10, modelo de dados)
- `docs/02` plano validado v2 (matriz de validação, impedimentos neutralizados)
- `docs/03` decisão Rota A do SINAPI (+ gate de 10 min pendente com arquivo real da Caixa)
- `docs/04` colheita de referências com regra de uso/licença
- `assets/` calculador v7 (referência read-only das regras já portadas ao banco)
