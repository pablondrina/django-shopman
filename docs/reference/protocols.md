# Referência de Protocols e Adapters

> Inventário gerado a partir do código atual (2026-04-14). Para o padrão,
> ver [ADR-001](../decisions/adr-001-protocol-adapter.md).

---

## Visão geral

Na arquitetura atual:

- **Protocols vivem no core que publica o contrato.** `PaymentBackend` é
  propriedade do `payman`; `FiscalBackend` do `orderman`; `CatalogBackend` do
  `offerman`; etc.
- **Adapters vivem no framework** (`shopman/shop/adapters/`) ou em
  `contrib/` do próprio core quando a implementação depende de outro core.
- **Estilo dos adapters varia:**
  - **Módulo função-style** — para pontos simples (`stock`, `notification_*`,
    `payment_*`). Resolvidos via `get_adapter("nome", ...)`.
  - **Classe** — quando há estado ou múltiplas estratégias ativas ao mesmo
    tempo (`StorefrontPricingBackend`, `ManychatOTPSender`).

---

## Protocols por core

### payman — pagamentos

**Arquivo:** `packages/payman/shopman/payman/protocols.py`

| Protocol | Métodos | Motivo de substituição |
|---|---|---|
| `PaymentBackend` | `create_intent`, `authorize`, `capture`, `refund`, `cancel`, `get_status` | Gateway varia por método (PIX, cartão) e ambiente (mock/prod) |

**DTOs:** `GatewayIntent`, `CaptureResult`, `RefundResult`, `PaymentStatus`

**Adapters (framework):**
- `adapters/payment_mock.py` — testes e dev, fluxo simulado
- `adapters/payment_efi.py` — PIX via Efi (Gerencianet)
- `adapters/payment_stripe.py` — cartão via Stripe

---

### orderman — fiscal e contábil

**Arquivo:** `packages/orderman/shopman/orderman/protocols.py`

| Protocol | Métodos | Motivo de substituição |
|---|---|---|
| `FiscalBackend` | `emit`, `query_status`, `cancel` | Emissor fiscal varia por provedor (Focus, mock) |
| `AccountingBackend` | `get_cash_flow`, `get_accounts_summary`, `list_entries`, `create_payable`, `create_receivable`, `mark_as_paid` | ERP contábil varia por instância |

**Adapters:** atualmente mock-only em framework. Implementações reais
(Focus NFe, Conta Azul) são plugáveis via `SHOPMAN_FISCAL_BACKEND` /
`SHOPMAN_ACCOUNTING_BACKEND`.

---

### offerman — catálogo e preço

**Arquivo:** `packages/offerman/shopman/offerman/protocols/`

| Protocol | Arquivo | Motivo |
|---|---|---|
| `CatalogBackend` | `catalog.py` | Permite substituir fonte de produtos/preços |
| `PricingBackend` | `catalog.py` | Estratégia de precificação por canal |
| `CostBackend` | `cost.py` | Fonte de custo (integração com stockman ou externo) |
| `CatalogProjectionBackend` | `projection.py` | Projeção leve para storefront |

**Adapters:**
- `packages/offerman/shopman/offerman/adapters/` — `NoopCostBackend`,
  `NoopPricingBackend`, `NoopCatalogProjectionBackend`, `OffermanCatalogBackend`
- `shopman/shop/adapters/pricing.py` — `StorefrontPricingBackend`
- `shopman/shop/adapters/catalog.py` — composição para framework

---

### stockman — estoque

**Arquivos:**
- `packages/stockman/shopman/stockman/protocols/production.py` — `ProductionBackend`
- `packages/stockman/shopman/stockman/protocols/sku.py` — validação de SKU

**Estilo stock:** **não** há classe `StockBackend` pública. O ponto de
integração é o **módulo** `shopman/shop/adapters/stock.py` (função-style,
resolvido via `get_adapter("stock")`), que delega a `StockService` do stockman.
Ver nota em `shopman/shop/protocols.py`.

---

### craftsman — produção

**Arquivo:** `packages/craftsman/shopman/craftsman/protocols/`

| Protocol | Arquivo | Motivo |
|---|---|---|
| `CatalogProtocol` | `catalog.py` | Resolver `output_ref` → produto |
| `ProductInfoBackend` | `catalog.py` | Dados descritivos de insumos/produtos |
| `DemandProtocol` | `demand.py` | Origem de demanda (pedidos reais ou simulação) |
| `InventoryProtocol` | `inventory.py` | Consultar disponibilidade de insumos |

**Adapters (no próprio core via `contrib/`):**
- `craftsman/contrib/stockman/production.py` — `CraftingProductionBackend`
- `craftsman/contrib/demand/backend.py` — `OrderingDemandBackend`
- `craftsman/adapters/noop.py` — `NoopDemandBackend`
- `craftsman/adapters/stock.py` — `StockingBackend`

---

### guestman — clientes

**Arquivo:** `packages/guestman/shopman/guestman/protocols/`

| Protocol | Arquivo | Motivo |
|---|---|---|
| `CustomerBackend` | `customer.py` | Permite outra fonte de cliente além do guestman |
| `OrderHistoryBackend` | `orders.py` | Histórico vem do orderman em produção, mock em testes |

**Adapters:**
- `guestman/adapters/orderman.py` — `OrdermanOrderHistoryBackend`

---

### doorman — autenticação

**Arquivo:** `packages/doorman/shopman/doorman/senders.py`

| Protocol | Motivo |
|---|---|
| `MessageSenderProtocol` | Canal de envio de OTP varia (SMS, WhatsApp/Manychat) |

**Adapters:**
- `shopman/shop/adapters/otp_manychat.py` — `ManychatOTPSender`

---

## Adapters puramente do framework (sem classe de protocol correspondente)

Módulos função-style resolvidos via `get_adapter(nome, ...)`. O "protocol"
é o conjunto de funções esperado; não há uma classe `Protocol`.

| Adapter | Arquivo | Uso |
|---|---|---|
| Stock | `adapters/stock.py` | Delega a `stockman.StockService` |
| Notification (console) | `adapters/notification_console.py` | Dev / fallback |
| Notification (email) | `adapters/notification_email.py` | Django email |
| Notification (sms) | `adapters/notification_sms.py` | SMS genérico |
| Notification (manychat) | `adapters/notification_manychat.py` | WhatsApp via ManyChat |
| Production | `adapters/production.py` | Composição para produção em lote |
| Customer | `adapters/customer.py` | Compõe guestman services |
| Catalog | `adapters/catalog.py` | Compõe offerman services |

Routing entre adapters de notificação é feito por `ChannelConfig.notifications.routing`.

---

## Configuração via settings

| Setting | Default | Onde é lido |
|---|---|---|
| `SHOPMAN_PAYMENT_BACKEND` | `payment_mock` | `get_adapter("payment", method=...)` |
| `SHOPMAN_FISCAL_BACKEND` | ausente → handlers não registrados | `ShopmanConfig.ready()` |
| `SHOPMAN_ACCOUNTING_BACKEND` | ausente → handler não registrado | `ShopmanConfig.ready()` |
| `SHOPMAN_STOCK_BACKEND` | autodetect stockman | `ShopmanConfig.ready()` |

Ver [`settings.md`](settings.md) para detalhes.

---

## Manutenção desta referência

Esta página é mantida à mão, mas deve ser regenerada quando novos protocols
são adicionados ou adapters são renomeados. Checar `grep -r "class.*Protocol"
packages/ shopman/shop/` para validar.
