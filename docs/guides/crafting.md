# Crafting — Produção e Receitas

## Visão Geral

O app `shopman.crafting` é um micro-MRP headless para gestão de produção. Gerencia receitas (Bill of Materials), ordens de trabalho (Work Orders) e execução de produção com controle de concorrência otimista e event sourcing.

```python
from shopman.crafting import craft, CraftError
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

## Modelos

### Recipe

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `code` | SlugField(50, unique) | Identificador (ex: "croissant-v1") |
| `name` | CharField(200) | Nome legível |
| `output_ref` | CharField(100) | Referência ao produto (string, agnóstica) |
| `batch_size` | DecimalField(12,3) | Unidades por lote |
| `steps` | JSONField | Passos de produção ["Mistura", "Modelagem", "Forno"] |
| `is_active` | BooleanField | Ativa |
| `meta` | JSONField | Metadados |

### RecipeItem

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `recipe` | FK(Recipe, CASCADE) | Receita pai |
| `input_ref` | CharField(100) | Referência do material (ex: "FARINHA-T55") |
| `quantity` | DecimalField(12,3) | Quantidade por batch_size |
| `unit` | CharField(20) | Unidade de medida |
| `sort_order` | PositiveSmallIntegerField | Ordem de exibição |
| `is_optional` | BooleanField | Permite substituição |

### WorkOrder

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `code` | CharField(20, unique) | Auto-gerado "WO-YYYY-NNNNN" |
| `recipe` | FK(Recipe, PROTECT) | Receita usada |
| `output_ref` | CharField(100) | Copiado da receita no plan |
| `quantity` | DecimalField(12,3) | Quantidade planejada (mutável via adjust enquanto planned) |
| `finished` | DecimalField(12,3, null) | Quantidade finalizada (set no finish, imutável) |
| `status` | CharField | PLANNED, STARTED, FINISHED, VOID |
| `rev` | PositiveIntegerField | Contador de concorrência otimista |
| `scheduled_date` | DateField(null) | Data de produção |
| `source_ref` | CharField(100) | Origem (ex: "order:789") |
| `position_ref` | CharField(100) | Posição no Stocking |
| `assigned_ref` | CharField(100) | Responsável (ex: "user:joao") |
| `meta` | JSONField | Inclui `_recipe_snapshot` |

**Propriedades:** `planned_qty`, `started_qty`, `finished_qty`, `loss`, `yield_rate`

### WorkOrderItem

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `work_order` | FK(WorkOrder, CASCADE) | Ordem de trabalho |
| `kind` | CharField(choices) | REQUIREMENT, CONSUMPTION, OUTPUT, WASTE |
| `item_ref` | CharField(100) | Referência do material/produto |
| `quantity` | DecimalField(12,3) | Quantidade |
| `unit` | CharField(20) | Unidade |
| `recorded_at` | DateTimeField | Quando registrado |
| `recorded_by` | CharField(100) | Quem registrou |
| `meta` | JSONField | Lote, validade, motivo, etc. |

### WorkOrderEvent

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `work_order` | FK(WorkOrder, CASCADE) | Ordem de trabalho |
| `seq` | PositiveIntegerField | Sequência incremental |
| `kind` | CharField(choices) | PLANNED, ADJUSTED, STARTED, FINISHED, VOIDED |
| `payload` | JSONField | Dados do evento |
| `actor` | CharField(100) | Quem disparou |
| `idempotency_key` | CharField(200, unique, null) | Prevenção de duplo-finish |

## Serviços

### Planejamento

**`craft.plan(recipe, quantity, date=None, **kwargs)`** — Criar ordem de trabalho.
```python
# Ordem única
wo = craft.plan(receita_croissant, 100, date=amanha, actor="user:pierre")

# Múltiplas ordens
ordens = craft.plan([
    (receita_croissant, 100),
    (receita_baguete, 45),
], date=amanha)
```

**`craft.adjust(order, quantity, reason=None, expected_rev=None)`** — Ajustar quantidade.
```python
craft.adjust(wo, quantity=97, reason="farinha insuficiente", expected_rev=0)
```

### Execução

**`craft.start(order, quantity, expected_rev=None, assigned_ref=None, position_ref=None, note=None)`** — Marcar quanto efetivamente entrou em produção.
```python
craft.start(
    wo,
    quantity=97,
    expected_rev=0,
    assigned_ref="user:joao",
    position_ref="station:forno-01",
    note="massa na bancada",
)
```

**`craft.finish(order, produced, consumed=None, wasted=None, expected_rev=None, idempotency_key=None)`** — Finalizar a ordem com resultado real.
```python
craft.finish(wo, produced=93)

# Completo: consumo explícito
craft.finish(wo, produced=93, consumed=[
    {"item_ref": "FARINHA-T55", "quantity": Decimal("7.5")},
    {"item_ref": "MANTEIGA", "quantity": Decimal("3.2")},
])

# Co-produtos
craft.finish(wo, produced=[
    {"item_ref": "CROISSANT", "quantity": 93},
    {"item_ref": "MASSA-SOBRA", "quantity": Decimal("0.5")},
])
```

Pipeline do `finish()`:
1. Calcula coeficiente francês: `started_qty / batch_size` (ou `planned_qty` se não houver start explícito)
2. Materializa 4 tipos de WorkOrderItem
3. Se `consumed=None`, usa BOM × coeficiente
4. Se `wasted=None`, calcula `started_qty - produced`
5. Chama `InventoryProtocol.consume()` + `receive()` (se configurado)

**`craft.void(order, reason, expected_rev=None)`** — Cancelar ordem.
```python
craft.void(wo, reason="demanda insuficiente")
```

### Consultas

**`craft.expected(output_ref, date)`** — Quantidade planejada para um produto/data.
```python
qty = craft.expected("CROISSANT", date(2026, 3, 20))
```

**`craft.needs(date, expand=False)`** — Necessidades de material (explosão de BOM).
```python
necessidades = craft.needs(date.today())
# [Need("FARINHA-T55", Decimal("38.5"), "kg", has_recipe=False), ...]

# Com expansão recursiva (sub-receitas → matérias-primas)
necessidades = craft.needs(date.today(), expand=True)
```

**`craft.suggest(date, output_refs=None)`** — Sugestões de produção baseadas em demanda.
```python
sugestoes = craft.suggest(date.today())
# [Suggestion(recipe=<Recipe>, quantity=Decimal("110"), basis={...}), ...]
```

Algoritmo de sugestão:
1. Consulta histórico de demanda via `DemandProtocol`
2. Estima demanda real (extrapola se houve esgotamento)
3. Soma comprometido (`committed`)
4. Aplica margem de segurança (`SAFETY_STOCK_PERCENT`, default 20%)

## Protocols

### InventoryProtocol

Interface para integração com estoque (Stocking).

```python
class InventoryProtocol(Protocol):
    def available(self, materials: list[MaterialNeed]) -> AvailabilityResult: ...
    def reserve(self, materials: list[MaterialNeed], ref: str) -> ReserveResult: ...
    def consume(self, items: list[MaterialUsed], ref: str) -> ConsumeResult: ...
    def release(self, ref: str, reason: str) -> ReleaseResult: ...
    def receive(self, items: list[MaterialProduced], ref: str) -> ReceiveResult: ...
```

**Vocabulário Crafting → Stocking:**

| Crafting | Stocking |
|----------|----------|
| `reserve()` | `stock.hold()` |
| `consume()` | `stock.fulfill()` |
| `release()` | `stock.release()` |
| `receive()` | `stock.receive()` |

### DemandProtocol

Interface para dados de demanda histórica.

```python
class DemandProtocol(Protocol):
    def history(self, product_ref: str, days: int = 28, same_weekday: bool = True) -> list[DailyDemand]: ...
    def committed(self, product_ref: str, target_date: date) -> Decimal: ...
```

### CatalogProtocol

Interface para dados de catálogo.

```python
class CatalogProtocol(Protocol):
    def resolve(self, item_ref: str) -> ItemInfo | None: ...
```

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

**Degradação graceful:** Se `INVENTORY_BACKEND` não estiver configurado, Crafting funciona standalone. Erros de backend são logados mas não propagados.

## Exceções

`CraftError` com códigos estruturados:
- `INVALID_QUANTITY` — Quantidade ≤ 0
- `TERMINAL_STATUS` — Não pode modificar WO em status terminal
- `VOID_FROM_DONE` — Não pode cancelar WO concluída
- `STALE_REVISION` — WO modificada por outro processo
- `BOM_CYCLE` — Ciclo na expansão de BOM
- `RECIPE_NOT_FOUND` — Receita não encontrada

`StaleRevision` — Subclasse para conflitos de concorrência.

## Exemplos

### Dia completo de produção

```python
from shopman.crafting import craft
from datetime import date

hoje = date.today()

# 06:00 — Obter sugestões
sugestoes = craft.suggest(hoje)
# [Suggestion(croissant-v1, qty=110), Suggestion(baguete-v1, qty=45)]

# 06:05 — Planejar produção
wo_croissant = craft.plan(receita_croissant, 110, date=hoje, actor="user:pierre")
wo_baguete = craft.plan(receita_baguete, 45, date=hoje, actor="user:pierre")

# 06:10 — Verificar necessidades de material
necessidades = craft.needs(hoje)
# [Need("FARINHA-T55", 38.5, "kg"), Need("MANTEIGA", 15.4, "kg"), ...]

# 07:00 — Ajustar (farinha insuficiente)
craft.adjust(wo_croissant, quantity=100, reason="farinha insuficiente", expected_rev=0)

# 10:00 — Fechar (croissants prontos)
craft.close(wo_croissant, produced=93, actor="user:pierre")
# loss=7, yield_rate=0.93

# 11:00 — Cancelar baguetes (demanda baixa)
craft.void(wo_baguete, reason="demanda insuficiente")
```
