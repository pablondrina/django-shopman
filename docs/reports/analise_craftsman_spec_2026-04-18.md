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

- [service.py](../../packages/craftsman/shopman/craftsman/service.py#L24)
- [__init__.py](../../packages/craftsman/shopman/craftsman/__init__.py#L25)

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

- [models/recipe.py](../../packages/craftsman/shopman/craftsman/models/recipe.py#L19)
- [models/recipe.py](../../packages/craftsman/shopman/craftsman/models/recipe.py#L113)

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

- [models/work_order.py](../../packages/craftsman/shopman/craftsman/models/work_order.py#L20)
- [models/work_order.py](../../packages/craftsman/shopman/craftsman/models/work_order.py#L164)
- [models/sequence.py](../../packages/craftsman/shopman/craftsman/models/sequence.py#L12)

### Eventos e idempotência

`WorkOrderEvent` é o trilho semântico:

- `seq` incremental por WO
- `kind` em `{planned, adjusted, started, finished, voided}`
- `payload` JSON por evento
- `idempotency_key` globalmente única

Ponto forte: audit trail claro.

Ponto fraco: `payload` não tem schema formal.

Referência:

- [models/work_order_event.py](../../packages/craftsman/shopman/craftsman/models/work_order_event.py#L54)

### Ledger de materiais

`WorkOrderItem` registra:

- `requirement`
- `consumption`
- `output`
- `waste`

Essa é uma boa decisão: o pacote mantém trilha auditável e recomponível.

Referência:

- [models/work_order_item.py](../../packages/craftsman/shopman/craftsman/models/work_order_item.py#L22)

## Fluxos principais

### `plan()`

- congela a BOM em `meta._recipe_snapshot`
- cria evento `planned`
- dispara `production_changed` fora da transação

Referência:

- [services/scheduling.py](../../packages/craftsman/shopman/craftsman/services/scheduling.py#L58)

### `adjust()`

- válido apenas em `PLANNED`
- aceita `quantity=0` como `void`
- valida holds/estoque/deficit
- incrementa `rev`
- cria evento `adjusted`

Referência:

- [services/scheduling.py](../../packages/craftsman/shopman/craftsman/services/scheduling.py#L189)

### `start()`

- grava quantidade real iniciada em evento
- não persiste uma coluna direta de “start quantity”

Referência:

- [services/scheduling.py](../../packages/craftsman/shopman/craftsman/services/scheduling.py#L263)

### `finish()`

- pode auto-iniciar
- usa snapshot da receita ou receita viva
- grava `requirement`, `consumption`, `output`, `waste`
- integra com estoque quando configurado

Referência:

- [services/execution.py](../../packages/craftsman/shopman/craftsman/services/execution.py#L22)

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

- [services/queries.py](../../packages/craftsman/shopman/craftsman/services/queries.py#L66)
- [services/queries.py](../../packages/craftsman/shopman/craftsman/services/queries.py#L119)

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

- [protocols/inventory.py](../../packages/craftsman/shopman/craftsman/protocols/inventory.py#L1)
- [protocols/demand.py](../../packages/craftsman/shopman/craftsman/protocols/demand.py#L1)
- [protocols/catalog.py](../../packages/craftsman/shopman/craftsman/protocols/catalog.py#L1)
- [adapters/stock.py](../../packages/craftsman/shopman/craftsman/adapters/stock.py#L48)
- [contrib/demand/backend.py](../../packages/craftsman/shopman/craftsman/contrib/demand/backend.py#L22)
- [contrib/stockman/production.py](../../packages/craftsman/shopman/craftsman/contrib/stockman/production.py#L30)

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

- [api/views.py](../../packages/craftsman/shopman/craftsman/api/views.py#L43)
- [views.py](../../packages/craftsman/shopman/craftsman/views.py#L1)
- [urls.py](../../packages/craftsman/shopman/craftsman/urls.py#L1)
- [templates/crafting/daily_ingredients.html](../../packages/craftsman/shopman/craftsman/templates/crafting/daily_ingredients.html#L1)
- [admin.py](../../packages/craftsman/shopman/craftsman/admin.py#L11)

## Distância entre promessa e realizado

### 1. Falta scoping explícito

As refs são globais e não há `channel_ref`, `store_ref`, `tenant_id` ou equivalente no núcleo.

Isso reduz a segurança de uso como core compartilhado para múltiplos negócios.

Referências:

- [models/work_order.py](../../packages/craftsman/shopman/craftsman/models/work_order.py#L105)
- [models/work_order_event.py](../../packages/craftsman/shopman/craftsman/models/work_order_event.py#L96)

### 2. Side effects externos ainda são ambíguos

`finish()` dispara integração com estoque dentro da transação local.

Em `graceful`, o sistema pode aparentar sucesso mesmo com integração falhando.

Em `strict`, ainda existe o risco clássico de inconsistência entre efeito local e remoto.

Referências:

- [services/execution.py](../../packages/craftsman/shopman/craftsman/services/execution.py#L51)
- [services/execution.py](../../packages/craftsman/shopman/craftsman/services/execution.py#L313)

### 3. Payloads sem schema forte

`payload` e `meta` funcionam por convenção.

Isso é flexível, mas enfraquece reproducibilidade por SDD e permite deriva semântica.

Referências:

- [models/work_order_event.py](../../packages/craftsman/shopman/craftsman/models/work_order_event.py#L54)
- [api/serializers.py](../../packages/craftsman/shopman/craftsman/api/serializers.py#L208)

### 4. Heurísticas de déficit ainda são simplificadas

`_validate_downstream_deficit()` não prova shortage real; ela usa uma heurística conservadora.

`_expand_bom()` usa profundidade máxima, não detecção formal de ciclo.

Referências:

- [services/scheduling.py](../../packages/craftsman/shopman/craftsman/services/scheduling.py#L391)
- [services/queries.py](../../packages/craftsman/shopman/craftsman/services/queries.py#L352)

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

- [api/views.py](../../packages/craftsman/shopman/craftsman/api/views.py#L51)

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
