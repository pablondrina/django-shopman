# Offerman 4.7 Fechado / Craftsman 4.8 Iniciado

Data: 2026-04-13

## 1. Fechamento de 4.7 `offerman`

`offerman` foi consolidado como domínio de oferta comercial publicável e sincronizável.

Estado final desta etapa:

- linguagem canônica estabilizada em `listed`, `published`, `sellable`
- contrato formal de projeção por canal via `CatalogProjectionBackend`
- `CatalogService.get_projection_items(...)` como payload canônico de oferta por listing
- `CatalogService.project_listing(...)` como operação formal de sync/retract
- preço contextual consolidado sob a pergunta canônica `get_price(...)`
- retorno rico formalizado em `ContextualPrice`
- `framework` storefront ligado ao contrato canônico de preço contextual

Decisão semântica preservada:

- `offerman` declara oferta comercial
- `stockman` continua decidindo prometibilidade operacional
- `projection` permanece como termo transversal da suite

## 2. Abertura de 4.8 `craftsman`

`craftsman` já tinha o core semântico correto (`planned`, `started`, `finished`, `void`), mas ainda faltava explicitar melhor a leitura operacional de chão.

Primeiro passo executado nesta etapa:

- criação de projeções operacionais em `craftsman.services.queries`
  - `craft.queue(...)`
  - `craft.summary(...)`

Essas projeções:

- não introduzem novos estados
- derivam a leitura operacional do estado e dos eventos já existentes
- tornam explícito o desvio entre `planned_qty`, `started_qty` e `finished_qty`
- expõem perda (`loss_qty`) e rendimento (`yield_rate`) para coordenação do chão

## 3. Próxima trilha natural de 4.8

Depois desta abertura, os próximos passos naturais de `craftsman` são:

1. levar `queue` e `summary` para superfícies de UI/admin/API
2. separar leituras por posto, responsável e turno
3. explicitar backlog `planned` vs execução `started`
4. usar o desvio `planned -> started -> finished` como base para sugestão futura de produção

### Roadmap imediato anotado

- aprofundar a leitura operacional por turno, posto e responsável
- expor desvio e rendimento com mais destaque para coordenação do chão
- manter isso como projeção operacional, sem criar novos estados no core

## 4. Validação

- `pytest packages/offerman/shopman/offerman/tests/test_service.py packages/offerman/shopman/offerman/tests/test_api.py` → `107 passed`
- `pytest framework/shopman/tests/web/test_web_catalog.py framework/shopman/tests/api/test_availability.py framework/shopman/tests/integration/test_crafting_offering.py` → `44 passed`
- `pytest packages/craftsman/shopman/craftsman/tests/test_vnext.py packages/craftsman/shopman/craftsman/tests/test_api_integration.py` → `127 passed`
