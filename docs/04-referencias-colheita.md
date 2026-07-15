# Referências e Colheita — regra de uso por item
(Consolidado do estudo de 08/07/2026. Regra geral na política de licenças do CLAUDE.md.)

| Item | Licença | Uso permitido | Fase |
|---|---|---|---|
| ezdxf | MIT | Código embutido — biblioteca do adaptador DXF (provada) | 2 |
| AutoSINAPI (+API) | GPLv3 | Serviço isolado em container populando staging; a ponte (tools/) é nossa. NUNCA embutir | 0 |
| opentakeoff | Apache-2.0 | Código reaproveitável: calibração de escala/medição sobre PDF | 5 |
| Raster-to-Graph | sem licença | Só conceito (paper): planta→grafo → moldou a planta_normalizada | 2 |
| WikiHouse Skylark | sem licença | Só conceito: biblioteca de blocos, nomenclatura, romaneio | 5 |
| bidwright / orama-core | sem licença | Só arquitetura (intake→takeoff→pricing→scheduling) | — |
| TF2DeepFloorplan | GPL-3.0 | Conceito; se usar código um dia, serviço isolado. ML é opcional por design | 5+ |
| FRAMECAD / Vertex BD / StrucSoft MWF / Scottsdale | comerciais | Zero código — requisitos/qualidade do panelizador; nosso diferencial: SINAPI/BDI + cronograma BR | 5 |
| ProjectLibre | open source | Oráculo de validação do CPM (mesmo projeto tem que bater) — não entra no produto | 4 |
| IfcOpenShell | LGPL | Export IFC 4D/5D futuro (IfcWorkSchedule/IfcCostSchedule), respeitando termos de biblioteca | 5+ |
| frappe-gantt / DHTMLX | verificar | UI Gantt: checar licença exata ANTES de instalar (DHTMLX é dual GPL/comercial) | 4 |
| CBCA / manuais fabricante (Knauf, Placo, Brasilit, Barbieri, LP) | — | Fonte de COEFICIENTES das composições próprias (entram como `estimado`) | 0-1 |
| Bases oficiais de PREÇO | públicas | SINAPI (BR, mensal) é a principal; CDHU ex-CPOS (SP) é a 2ª mais relevante regionalmente; ORSE (~9k composições) como fonte de coeficiente; SICRO p/ terraplenagem/infra; SIURB/EMOP/SEINFRA/FDE conforme necessidade | 0 |

Pendência RESOLVIDA em 09/07/2026: pin = commit `0020609` (main); licenças verificadas via API e correções registradas em docs/05-colheita-aplicada.md (augustogoncalves/sinapi é MIT; frappe-gantt MIT; Skylark confirmado sem licença).

## Dependências da casca web (verificadas em 2026-07-15)

| Pacote | Licença | Pode embutir? | Uso |
|---|---|---|---|
| FastAPI 0.139 | MIT | sim | rotas |
| Uvicorn 0.51 | BSD-3-Clause | sim | servidor ASGI |
| Jinja2 | BSD-3-Clause | sim | templates |
| itsdangerous | BSD-3-Clause | sim | assinatura do cookie de sessão |
| python-multipart | Apache-2.0 | sim | formulários |
| httpx | BSD-3-Clause | sim | só teste (TestClient) |
| htmx 2.0.4 | BSD-2-Clause | sim (vendored em `app/static/`) | interatividade sem build step |

Nenhuma GPL. Nenhuma sem licença. Todas permissivas → embutir é permitido.
