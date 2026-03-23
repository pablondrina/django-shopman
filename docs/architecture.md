# Arquitetura — Django Shopman

## Visao Geral

Django Shopman e composto por **7 apps core** independentes e um **orquestrador** que os conecta para cenarios de negocio concretos. Cada app e um pacote pip instalavel separadamente.

## Diagrama de Camadas

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PROJETO DJANGO                              │
│                     (shopman-app/project/)                           │
│                   settings.py · urls.py · wsgi                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                   ORQUESTRADOR (shopman-app/shopman/)         │  │
│  │                                                               │  │
│  │  orchestration.py    presets.py    channels.py    config.py   │  │
│  │                                                               │  │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────────┐ ┌─────────────┐  │  │
│  │  │  stock   │ │ payment  │ │notifications │ │  customer   │  │  │
│  │  │ handler  │ │ handler  │ │   handler    │ │  handler    │  │  │
│  │  │ adapter  │ │ adapter  │ │   backend    │ │  adapter    │  │  │
│  │  └────┬─────┘ └────┬─────┘ └──────┬───────┘ └──────┬──────┘  │  │
│  │       │             │              │                │          │  │
│  │  ┌────┴──┐ ┌───────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │  │
│  │  │pricing│ │fiscal │ │accounting│ │  returns │ │ webhook  │ │  │
│  │  └───────┘ └───────┘ └──────────┘ └──────────┘ └──────────┘ │  │
│  └───────────────────────────────────────────────────────────────┘  │
│         │            │            │            │            │        │
│     Protocol     Protocol     Protocol     Protocol     Protocol    │
│         │            │            │            │            │        │
├─────────┴────────────┴────────────┴────────────┴────────────┴───────┤
│                                                                     │
│  ┌─────────────────────── CORE APPS ─────────────────────────────┐  │
│  │                    (shopman-core/*)                            │  │
│  │                                                               │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            │  │
│  │  │offering │ │stocking │ │crafting │ │ordering │            │  │
│  │  │catalogo │ │estoque  │ │producao │ │pedidos  │            │  │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘            │  │
│  │                                                               │  │
│  │  ┌──────────┐ ┌─────────┐ ┌─────────┐                       │  │
│  │  │attending │ │ gating  │ │  utils  │                       │  │
│  │  │clientes  │ │  auth   │ │ comum   │                       │  │
│  │  └──────────┘ └─────────┘ └─────────┘                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│              CANAIS DE VENDA (shopman-app/channels/)                 │
│                    web · (futuros: pos, api)                        │
├─────────────────────────────────────────────────────────────────────┤
│              APP DEMO (shopman-app/nelson/)                          │
│              Nelson Boulangerie — seed, modifiers, validators       │
└─────────────────────────────────────────────────────────────────────┘
```

## Protocol/Adapter Pattern

Toda comunicacao entre apps usa `typing.Protocol` (PEP 544) com `@runtime_checkable`. Nenhum app importa outro diretamente.

### Como funciona

1. O app **consumidor** define o Protocol (contrato) no seu codigo
2. O app **provedor** implementa um Adapter
3. A ligacao e feita via settings (dotted path) ou registry (`AppConfig.ready()`)

### Exemplo: Stock

```python
# shopman-app/shopman/stock/protocols.py — consumidor define o contrato
@runtime_checkable
class StockBackend(Protocol):
    def check_availability(self, sku: str, quantity: Decimal, ...) -> AvailabilityResult: ...
    def create_hold(self, sku: str, quantity: Decimal, ...) -> HoldResult: ...
    def release_hold(self, hold_id: str) -> bool: ...
    def fulfill_hold(self, hold_id: str) -> bool: ...

# shopman-app/shopman/stock/adapters/stockman.py — adapter que conecta ao stocking
class StockmanAdapter:
    def check_availability(self, sku, quantity, ...):
        # Delega para shopman.stocking.service
        ...

# settings.py — ligacao via config
SHOPMAN_STOCK_BACKEND = "shopman.stock.adapters.stockman.StockmanAdapter"
```

### Protocols existentes

| Protocol | Definido em | Adapters |
|----------|-------------|----------|
| `StockBackend` | `shopman.stock.protocols` | `adapters/stockman.py` (stocking), `noop` |
| `PaymentBackend` | `shopman.ordering.protocols` | (configuravel) |
| `FiscalBackend` | `shopman.ordering.protocols` | (configuravel) |
| `AccountingBackend` | `shopman.ordering.protocols` | (configuravel) |
| `NotificationBackend` | `shopman.notifications.protocols` | `console`, `manychat` |
| `CustomerBackend` | `shopman.customer.protocols` | (configuravel) |
| `PricingBackend` | `shopman.pricing.protocols` | (configuravel) |

### Vantagens

- **Deploy independente:** cada app pode ser instalado e testado isoladamente
- **Substituibilidade:** trocar o sistema de estoque requer apenas um novo adapter
- **Testabilidade:** mocks implementam o mesmo Protocol, sem dependencias externas
- **Sem dependencias circulares:** cada app depende apenas de `utils`

## Mapa de Dependencias

```
utils ← offering
utils ← stocking
utils ← crafting  ← (protocols: stocking, offering)
utils ← ordering
utils ← attending ← (protocols: ordering)
utils ← gating    ← (protocols: attending)
```

Setas indicam dependencia de pacote. Dependencias via Protocol (runtime) sao indicadas entre parenteses — nao criam acoplamento de pacote.

## Orquestrador — Fluxo de um Pedido

```
1. Session criada (modify_session)
   │
2. Modifiers rodam (pricing, taxes)
   │
3. Validators de draft rodam
   │
4. Commit (commit_session)
   │
   ├── Validators de commit rodam (StockCheckValidator, etc.)
   ├── Order criada com snapshot dos itens
   ├── Directives enfileiradas:
   │     ├── stock.hold     → StockHoldHandler → StockBackend.create_hold()
   │     ├── notification.send → NotificationSendHandler → NotificationBackend.send()
   │     ├── payment.capture → PaymentHandler → PaymentBackend.capture()
   │     └── fiscal.emit    → FiscalHandler → FiscalBackend.emit()
   │
5. Directives processadas (sincrono ou via process_directives)
```

## Presets de Canal

Cada canal de venda tem um preset que configura o comportamento do pipeline:

| Preset | Confirmacao | Pagamento | Stock Hold TTL | Directives pos-commit |
|--------|-------------|-----------|----------------|----------------------|
| `pos()` | Auto (operador presente) | `counter` (sincrono) | 300s | stock.hold, notification.send |
| `remote()` | Auto (otimista, 10min timeout) | `pix` (assincrono) | sem expiracao | stock.hold, notification.send |
| `marketplace()` | Auto (ja confirmado) | `external` (ja pago) | sem expiracao | notification.send |

Presets sao definidos em `shopman-app/shopman/presets.py` e registrados em `shopman-app/shopman/orchestration.py`.

## Mapa de Nomes (suite antiga → repo novo)

Para quem conhece a suite antiga (`django-shopman-suite`):

| Suite Antiga | Repo Novo | App Label |
|-------------|-----------|-----------|
| commons | shopman.utils | utils |
| offerman | shopman.offering | offering |
| stockman | shopman.stocking | stocking |
| craftsman | shopman.crafting | crafting |
| omniman | shopman.ordering | ordering |
| guestman | shopman.attending | attending |
| doorman | shopman.gating | gating |
