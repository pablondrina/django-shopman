# Análise crítica de `packages/craftsman/shopman/craftsman`

Data: 2026-04-18

## Escopo

Este relatório cobre exclusivamente `packages/craftsman/shopman/craftsman`, com foco em extração de SPECs a partir do código para reprodução por Spec-driven Development.

Base de validação reportada pelo agente dedicado:

- suíte do pacote: `236 passed, 2 skipped`

## Veredito

O `craftsman` já é um núcleo micro-MRP coerente e tecnicamente sério. O desenho central `WorkOrder` + `WorkOrderEvent` + `WorkOrderItem` + `CraftService` é sólido, bem testado e suficientemente expressivo para planejamento, execução, consumo, output, desperdício e integração com demanda/estoque.

O que ainda o impede de ser um standalone plenamente robusto e universal não é corretude básica, e sim maturidade de contrato:

- falta scoping explícito por tenant/domínio/canal
- faltam schemas formais para `payload` e `meta`
- integrações externas ainda podem falhar de forma ambígua
- a superfície é muito admin/API-first e pouco orientada a UX operacional

## SPECS percebidas

### Fachada pública

`CraftService` agrega a API pública do domínio:

- `plan`
- `adjust`
- `start`
- `finish`
- `void`
- `expected`
- `needs`
- `suggest`
- `queue`
- `summary`

Referências:

- [service.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/service.py:24)
- [__init__.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/__init__.py:25)

### Receita/BOM

`Recipe` é a BOM canônica:

- `ref`, `name`, `output_ref`
- `batch_size > 0`
- `steps` como lista de strings
- `meta` livre
- `is_active` como gate de publicação

`RecipeItem` define insumos por lote:

- unicidade por `(recipe, input_ref)`
- quantidade positiva

Referências:

- [models/recipe.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/recipe.py:19)
- [models/recipe.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/recipe.py:113)

### Ordem de produção

`WorkOrder` modela:

- estado
- revisão otimista
- `source_ref`, `position_ref`, `operator_ref`
- `quantity` planejada
- `finished` final
- `started_qty` derivado de eventos

`ref` é gerada por sequência atômica.

`loss` e `yield_rate` são projeções computadas, não colunas persistidas.

Referências:

- [models/work_order.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/work_order.py:20)
- [models/work_order.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/work_order.py:164)
- [models/sequence.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/sequence.py:12)

### Eventos e idempotência

`WorkOrderEvent` é o trilho semântico:

- `seq` incremental por WO
- `kind` em `{planned, adjusted, started, finished, voided}`
- `payload` JSON por evento
- `idempotency_key` globalmente única

Ponto forte: audit trail claro.

Ponto fraco: `payload` não tem schema formal.

Referência:

- [models/work_order_event.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/work_order_event.py:54)

### Ledger de materiais

`WorkOrderItem` registra:

- `requirement`
- `consumption`
- `output`
- `waste`

Essa é uma boa decisão: o pacote mantém trilha auditável e recomponível.

Referência:

- [models/work_order_item.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/work_order_item.py:22)

## Fluxos principais

### `plan()`

- congela a BOM em `meta._recipe_snapshot`
- cria evento `planned`
- dispara `production_changed` fora da transação

Referência:

- [services/scheduling.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/scheduling.py:58)

### `adjust()`

- válido apenas em `PLANNED`
- aceita `quantity=0` como `void`
- valida holds/estoque/deficit
- incrementa `rev`
- cria evento `adjusted`

Referência:

- [services/scheduling.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/scheduling.py:189)

### `start()`

- grava quantidade real iniciada em evento
- não persiste uma coluna direta de “start quantity”

Referência:

- [services/scheduling.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/scheduling.py:263)

### `finish()`

- pode auto-iniciar
- usa snapshot da receita ou receita viva
- grava `requirement`, `consumption`, `output`, `waste`
- integra com estoque quando configurado

Referência:

- [services/execution.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/execution.py:22)

## Queries públicas

As queries são projeções operacionais:

- `expected`
- `needs`
- `suggest`
- `queue`
- `summary`

`suggest()` combina:

- histórico de demanda
- comprometidos
- safety stock
- sazonalidade
- multiplicador de alta demanda

Referências:

- [services/queries.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/queries.py:66)
- [services/queries.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/queries.py:119)

## Protocolos e integrações

Protocolos principais:

- `InventoryProtocol`
- `DemandProtocol`
- `CatalogProtocol`
- `ProductInfoBackend`

Adapters relevantes:

- `StockingBackend`
- `OrderingDemandBackend`
- `CraftsmanProductionBackend`

O desenho é bom: fronteiras claras, com degradação controlada quando dependências faltam.

Referências:

- [protocols/inventory.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/protocols/inventory.py:1)
- [protocols/demand.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/protocols/demand.py:1)
- [protocols/catalog.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/protocols/catalog.py:1)
- [adapters/stock.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/adapters/stock.py:48)
- [contrib/demand/backend.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/contrib/demand/backend.py:22)
- [contrib/stockman/production.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/contrib/stockman/production.py:30)

## API e UX

A superfície HTTP é previsível e claramente backoffice/headless:

- auth obrigatória
- `plan` retorna `201/404/400`
- `finish`, `adjust`, `start`, `void` mapeiam `StaleRevision` para `409`

Mas a experiência continua muito admin/API-first:

- `views.py` vazio
- `urls.py` vazio
- sem web UX própria além de admin e template auxiliar

Referências:

- [api/views.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/api/views.py:43)
- [views.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/views.py:1)
- [urls.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/urls.py:1)
- [templates/crafting/daily_ingredients.html](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/templates/crafting/daily_ingredients.html:1)
- [admin.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/admin.py:11)

## Distância entre promessa e realizado

### 1. Falta scoping explícito

As refs são globais e não há `channel_ref`, `store_ref`, `tenant_id` ou equivalente no núcleo.

Isso reduz a segurança de uso como core compartilhado para múltiplos negócios.

Referências:

- [models/work_order.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/work_order.py:105)
- [models/work_order_event.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/work_order_event.py:96)

### 2. Side effects externos ainda são ambíguos

`finish()` dispara integração com estoque dentro da transação local.

Em `graceful`, o sistema pode aparentar sucesso mesmo com integração falhando.

Em `strict`, ainda existe o risco clássico de inconsistência entre efeito local e remoto.

Referências:

- [services/execution.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/execution.py:51)
- [services/execution.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/execution.py:313)

### 3. Payloads sem schema forte

`payload` e `meta` funcionam por convenção.

Isso é flexível, mas enfraquece reproducibilidade por SDD e permite deriva semântica.

Referências:

- [models/work_order_event.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/models/work_order_event.py:54)
- [api/serializers.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/api/serializers.py:208)

### 4. Heurísticas de déficit ainda são simplificadas

`_validate_downstream_deficit()` não prova shortage real; ela usa uma heurística conservadora.

`_expand_bom()` usa profundidade máxima, não detecção formal de ciclo.

Referências:

- [services/scheduling.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/scheduling.py:391)
- [services/queries.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/services/queries.py:352)

### 5. UX ainda não acompanha a ambição operacional

O pacote não entrega experiência omotenashi/mobile/WhatsApp-first própria.

Ele é um core bom para produção, mas não um produto operacional completo por si.

### 6. Autorização é curta demais

O pacote usa `IsAuthenticated`, mas não separa perfis de:

- planejar
- iniciar
- finalizar
- void
- visualizar

Referência:

- [api/views.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/craftsman/shopman/craftsman/api/views.py:51)

## Serve como standalone?

### Como micro-MRP interno

Sim.

O pacote já serve bem para:

- BOM
- ordem de produção
- rastreio
- sugestão de produção
- integração opcional com estoque e demanda

### Como solução standalone universal

Ainda não totalmente.

Faltam:

- scoping por domínio/canal/tenant
- schemas formais de evento/meta
- isolamento mais forte de integrações
- autorização mais granular
- superfícies operacionais mais completas

## Resumo curto

- O núcleo de produção é bom, coeso e bem testado.
- O principal gap não é correção, e sim formalização de contrato.
- O pacote ainda é mais “bom core interno do Shopman” do que “framework universal de micro-MRP”.
