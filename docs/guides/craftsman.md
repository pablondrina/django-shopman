# Craftsman — Produção e Receitas

## Visão Geral

O app `shopman.craftsman` é um micro-MRP headless para gestão de produção. Gerencia receitas (Bill of Materials), ordens de trabalho (Work Orders) e execução de produção com controle de concorrência otimista e event sourcing.

```python
from shopman.craftsman import craft, CraftError
```

## Conceitos

### Receita (`Recipe`)
Define como produzir um produto: ingredientes (`RecipeItem`), quantidade por lote (`batch_size`) e passos de produção.

### Coeficiente Francês
Método de escala proporcional: `coeficiente = quantidade / batch_size`. Todos os ingredientes são escalados proporcionalmente.

### Ordem de Trabalho (`WorkOrder`)
Instância de produção com ciclo de vida: `PLANNED → STARTED → FINISHED` ou `PLANNED/STARTED → VOID`.

### 4 Tipos de Item (`WorkOrderItem`)
- **REQUIREMENT** — BOM planejado (receita × coeficiente)
- **CONSUMPTION** — Material realmente consumido
- **OUTPUT** — Produto produzido
- **WASTE** — Perda/refugo

### Snapshot de BOM
No momento do `plan()`, a receita é congelada em `meta._recipe_snapshot`. O `finish()` usa a receita como era, não como é agora.

### Concorrência Otimista
Campo `rev` com verificação opcional via `expected_rev`. Conflitos geram `StaleRevision`.

## Serviços

### Planejamento

**`craft.plan(recipe, quantity, date=None, **kwargs)`** — Criar ordem de trabalho.

**`craft.adjust(order, quantity, reason=None, expected_rev=None)`** — Ajustar quantidade.

### Execução

**`craft.start(order, quantity, expected_rev=None, operator_ref=None, position_ref=None, note=None)`** — Marcar quanto efetivamente entrou em produção.

**`craft.finish(order, finished, consumed=None, wasted=None, expected_rev=None, idempotency_key=None)`** — Finalizar a ordem com resultado real.

**`craft.void(order, reason, expected_rev=None)`** — Cancelar ordem.

### Consultas

**`craft.expected(output_ref, date)`** — Quantidade planejada para um produto/data.

**`craft.needs(date, expand=False)`** — Necessidades de material (explosão de BOM).

**`craft.suggest(date, output_refs=None)`** — Sugestões de produção baseadas em demanda.

## Protocols

### InventoryProtocol

Interface para integração com estoque (Stockman).

```python
class InventoryProtocol(Protocol):
    def available(self, materials: list[MaterialNeed]) -> AvailabilityResult: ...
    def reserve(self, materials: list[MaterialNeed], ref: str) -> ReserveResult: ...
    def consume(self, items: list[MaterialUsed], ref: str) -> ConsumeResult: ...
    def release(self, ref: str, reason: str) -> ReleaseResult: ...
    def receive(self, items: list[MaterialProduced], ref: str) -> ReceiveResult: ...
```

**Vocabulário Craftsman → Stockman:**

| Craftsman | Stockman |
|----------|----------|
| `reserve()` | `stock.hold()` |
| `consume()` | `stock.fulfill()` |
| `release()` | `stock.release()` |
| `receive()` | `stock.receive()` |

### DemandProtocol

Interface para dados de demanda histórica.

### CatalogProtocol

Interface para dados de catálogo.

## Configuração

Chave Django settings: `CRAFTSMAN`

| Setting | Default | Descrição |
|---------|---------|-----------|
| `INVENTORY_BACKEND` | None | Dotted path para InventoryProtocol |
| `CATALOG_BACKEND` | None | Dotted path para CatalogProtocol |
| `DEMAND_BACKEND` | None | Dotted path para DemandProtocol |
| `SAFETY_STOCK_PERCENT` | 0.20 | Margem de segurança (20%) |
| `HISTORICAL_DAYS` | 28 | Dias de histórico para sugestões |
| `SAME_WEEKDAY_ONLY` | True | Usar mesmo dia da semana no histórico |

## Nota sobre compatibilidade de nomes

Este guia substitui o antigo `guides/crafting.md` (nomenclatura anterior do pacote; arquivo removido).

