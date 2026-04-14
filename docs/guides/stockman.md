# Stockman — Estoque e Reservas

## Visão Geral

O app `shopman.stockman` é um ledger imutável de estoque com coordenadas espaço-tempo, sistema de holds (reservas) e planejamento de produção. A interface pública unificada é a classe `StockService` (exposta como `stock`).

**Conceito central:** Estoque existe numa coordenada `(position, target_date, batch)`. `target_date=None` significa estoque físico (agora); datas futuras representam produção planejada.

```python
from shopman.stockman import stock, StockError
```

## Conceitos

### Coordenadas Espaço-Tempo
Todo estoque vive numa coordenada tridimensional:
- **Posição** (`Position`) — Onde: vitrine, depósito, forno
- **Data-alvo** (`target_date`) — Quando: None=agora, futuro=planejado
- **Lote** (`batch`) — Rastreabilidade: "CRO-20260319-M"

### Quant
Cache de quantidade numa coordenada. O campo `_quantity` é O(1) — atualizado atomicamente por cada Move.

### Move (Imutável)
Registro de alteração de quantidade. **Nunca** se atualiza ou deleta um Move. Correções são novos Moves com delta inverso.

### Hold (Reserva)
Reserva de quantidade com ciclo de vida: `PENDING → CONFIRMED → FULFILLED` ou `RELEASED`.

Dois modos:
- **Reserva** (`quant != None`) — estoque existe, quantidade reservada
- **Demanda** (`quant == None`) — estoque não existe, pré-encomenda aceita

### Política de Disponibilidade
Definida no Product (`shopman.offerman`), respeitada pelo Stockman:
- `stock_only` — só estoque físico
- `planned_ok` — aceita produção planejada
- `demand_ok` — aceita holds sem estoque (demanda)

## Modelos

### Position

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | SlugField(unique) | Identificador ("vitrine", "deposito") |
| `name` | CharField(100) | Nome legível |
| `kind` | CharField(choices) | PHYSICAL, PROCESS, VIRTUAL |
| `is_saleable` | BooleanField | Estoque aqui pode ser vendido? |
| `is_default` | BooleanField | Posição padrão |
| `metadata` | JSONField | Dados customizados |

**PositionKind:**
- `PHYSICAL` — Local real (Vitrine, Depósito)
- `PROCESS` — Etapa de produção (Forno, Fermentação)
- `VIRTUAL` — Conceito contábil (Perdas, Ajustes)

### Quant

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sku` | CharField(100) | SKU do produto |
| `position` | FK(Position, null, PROTECT) | Onde |
| `target_date` | DateField(null) | Quando (null=físico) |
| `batch` | CharField(50) | Referência de lote |
| `_quantity` | DecimalField(12,3) | Cache de quantidade (O(1)) |
| `metadata` | JSONField | Dados customizados |

**Constraint único:** `(sku, position, target_date, batch)`

**Propriedades:**
- `quantity` — Retorna `_quantity`
- `held` — Soma de holds ativos (não expirados)
- `available` — `quantity - held`
- `is_future` — `target_date > today`

**Manager:**
- `Quant.objects.for_sku(sku)` — Filtra por SKU
- `Quant.objects.physical()` — Só estoque físico
- `Quant.objects.planned()` — Só planejado (futuro)
- `Quant.objects.at_position(position)` — Filtra por posição

### Move (Imutável)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `quant` | FK(Quant, PROTECT) | Coordenada alterada |
| `delta` | DecimalField(12,3) | +n=entrada, -n=saída |
| `reason` | CharField(255) | Motivo obrigatório |
| `metadata` | JSONField | Dados extras |
| `timestamp` | DateTimeField | Quando |
| `user` | FK(User, SET_NULL, null) | Quem |

**Imutabilidade:** `save()` rejeita update (pk existente), `delete()` sempre rejeita.

### Hold

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sku` | CharField(100) | SKU do produto |
| `quant` | FK(Quant, PROTECT, null) | Estoque vinculado (None=demanda) |
| `quantity` | DecimalField(12,3) | Quantidade reservada |
| `target_date` | DateField | Data desejada |
| `status` | CharField(choices) | PENDING, CONFIRMED, FULFILLED, RELEASED |
| `expires_at` | DateTimeField(null) | Expiração opcional |
| `resolved_at` | DateTimeField(null) | Quando resolvido |
| `metadata` | JSONField | Dados extras |

**Propriedades:** `is_demand`, `is_reservation`, `is_active`, `is_expired`, `hold_id` ("hold:{pk}")

### Batch

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | CharField(50, unique) | Identificador do lote |
| `sku` | CharField(100) | SKU do produto |
| `production_date` | DateField(null) | Data de produção |
| `expiry_date` | DateField(null) | Data de validade |
| `supplier` | CharField(200) | Fornecedor |
| `notes` | TextField | Observações |

### StockAlert

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sku` | CharField(100) | SKU do produto |
| `position` | FK(Position, null) | Posição (null=todas) |
| `min_quantity` | DecimalField(12,3) | Limite mínimo |
| `is_active` | BooleanField | Ativo |
| `last_triggered_at` | DateTimeField(null) | Último disparo |

## Serviços

A classe `StockService` combina 4 mixins: `StockQueries`, `StockMovements`, `StockHolds`, `StockPlanning`.

### Consultas (StockQueries)

```python
from shopman.stockman import stock

# Quantidade disponível (física)
disponivel = stock.available("CROISSANT")

# Disponível numa posição e data
disponivel = stock.available("CROISSANT", target_date=date.today(), position=vitrine)

# Demanda pendente (holds sem estoque)
demanda = stock.demand("CROISSANT", target_date=date.today())

# Quantidade comprometida (holds ativos)
comprometido = stock.committed("CROISSANT")

# Buscar quant específico
quant = stock.get_quant("CROISSANT", position=vitrine)

# Listar quants
quants = stock.list_quants(sku="CROISSANT", include_future=True)
```

### Movimentações (StockMovements)

```python
# Entrada de estoque
quant = stock.receive(
    quantity=Decimal("100"),
    sku="CROISSANT",
    position=vitrine,
    reason="Produção manhã",
    user=usuario,
)

# Saída de estoque
move = stock.issue(
    quantity=Decimal("5"),
    quant=quant,
    reason="Venda #123",
    user=usuario,
)

# Ajuste de inventário (contagem física)
move = stock.adjust(
    quant=quant,
    new_quantity=Decimal("93"),
    reason="Contagem física",
    user=usuario,
)
```

### Holds (StockHolds)

```python
# Criar hold (reserva ou demanda)
hold_id = stock.hold(
    quantity=Decimal("5"),
    product=croissant,  # Product com availability_policy
    target_date=date.today(),
    expires_at=timezone.now() + timedelta(minutes=30),
)
# → "hold:42"

# Confirmar (PENDING → CONFIRMED)
hold = stock.confirm(hold_id)

# Efetivar (CONFIRMED → FULFILLED, cria Move negativo)
move = stock.fulfill(hold_id, user=usuario)

# Liberar (PENDING|CONFIRMED → RELEASED)
hold = stock.release(hold_id, reason="Pedido cancelado")

# Liberar todos expirados (batch processing)
liberados = stock.release_expired()
```

### Planejamento (StockPlanning)

```python
amanha = date.today() + timedelta(days=1)

# Planejar produção futura
quant = stock.plan(
    quantity=Decimal("100"),
    product=croissant,
    target_date=amanha,
    reason="Produção planejada",
)

# Replanejar (ajustar quantidade)
quant = stock.replan(
    quantity=Decimal("110"),
    product=croissant,
    target_date=amanha,
    reason="Demanda aumentou",
)

# Realizar produção (planejado → físico)
quant_fisico = stock.realize(
    product=croissant,
    target_date=amanha,
    actual_quantity=Decimal("93"),
    to_position=vitrine,
    reason="Produção realizada",
)
# → Transfere holds FIFO do planejado para o físico
# → Emite sinal holds_materialized
```

### Alertas

```python
from shopman.stockman.services.alerts import check_alerts

# Verificar alertas (todos os SKUs)
alertas = check_alerts()

# Verificar alertas de um SKU
alertas = check_alerts(sku="CROISSANT")
```

## Protocols

### SkuValidator

Interface para validar SKUs contra catálogo externo (ex: Offerman).

```python
class SkuValidator(Protocol):
    def validate_sku(self, sku: str) -> SkuValidationResult: ...
    def validate_skus(self, skus: list[str]) -> dict[str, SkuValidationResult]: ...
    def get_sku_info(self, sku: str) -> SkuInfo | None: ...
    def search_skus(self, query: str, limit=20) -> list[SkuInfo]: ...
```

### ProductionBackend

Interface para solicitar produção ao Craftsman.

```python
class ProductionBackend(Protocol):
    def request_production(self, request: ProductionRequest) -> ProductionResult: ...
    def check_status(self, request_id: str) -> ProductionStatus | None: ...
    def cancel_request(self, request_id: str, reason: str) -> ProductionResult: ...
    def list_pending(self, sku: str | None = None) -> list[ProductionStatus]: ...
```

## Configuração

Chave Django settings: `STOCKMAN`

| Setting | Default | Descrição |
|---------|---------|-----------|
| `SKU_VALIDATOR` | `""` | Dotted path para validador de SKU |
| `HOLD_TTL_MINUTES` | `0` | TTL padrão de holds (0=sem expiração) |
| `EXPIRED_BATCH_SIZE` | `200` | Batch para release_expired |
| `VALIDATE_INPUT_SKUS` | `True` | Validar SKUs antes de operações |

## Exceções

`StockError` com códigos estruturados:
- `INSUFFICIENT_AVAILABLE` — Quantidade indisponível
- `INSUFFICIENT_QUANTITY` — Estoque insuficiente para saída
- `INVALID_HOLD` — Hold não encontrado
- `INVALID_STATUS` — Transição de status inválida
- `INVALID_QUANTITY` — Quantidade ≤ 0
- `HOLD_IS_DEMAND` — Não pode fulfill hold de demanda
- `HOLD_EXPIRED` — Hold expirado
- `REASON_REQUIRED` — Motivo obrigatório
- `QUANT_NOT_FOUND` — Quant não encontrado

