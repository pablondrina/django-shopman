# Referência de Sinais (Signals)

> Gerado a partir dos arquivos `signals.py`, `signals/`, `receivers.py` e `hooks.py` do código atual.

---

## Visão Geral

O projeto define **17 sinais custom** do Django. Destes, **5 estão ativamente conectados** a receivers no orquestrador (`shopman/`), e **12 estão definidos** para uso por extensões e integrações futuras.

| Sinal | Módulo | Status | Receivers |
|-------|--------|--------|-----------|
| [`product_created`](#product_created) | offerman | Disponível | — |
| [`price_changed`](#price_changed) | offerman | Disponível | — |
| [`production_changed`](#production_changed) | craftsman | **Ativo** | craftsman→stockman, channels→stock (voided) |
| [`customer_created`](#customer_created) | guestman | Disponível | — |
| [`customer_updated`](#customer_updated) | guestman | Disponível | — |
| [`holds_materialized`](#holds_materialized) | stockman | **Ativo** | channels→auto-commit |
| [`order_changed`](#order_changed) | orderman | **Ativo** | channels→lifecycle pipeline |
| [`customer_authenticated`](#customer_authenticated) | doorman | Disponível | — |
| [`access_link_created`](#access_link_created) | doorman | Disponível | — |
| [`verification_code_sent`](#verification_code_sent) | doorman | Disponível | — |
| [`verification_code_verified`](#verification_code_verified) | doorman | Disponível | — |
| [`device_trusted`](#device_trusted) | doorman | Disponível | — |
| [`payment_authorized`](#payment_authorized) | payman | Disponível | — |
| [`payment_captured`](#payment_captured) | payman | Disponível | — |
| [`payment_failed`](#payment_failed) | payman | Disponível | — |
| [`payment_cancelled`](#payment_cancelled) | payman | Disponível | — |
| [`payment_refunded`](#payment_refunded) | payman | Disponível | — |

Além dos sinais custom, o projeto usa **2 sinais built-in** do Django (`post_save`) para dispatch de directives e alertas de estoque.

### Conexões ativas (resumo)

| Signal | Conectado em | Receiver | Efeito |
|--------|-------------|----------|--------|
| `order_changed` | `ShopmanConfig.ready()` | `hooks.on_order_lifecycle` | Lê pipeline do canal, cria directives |
| `holds_materialized` | `setup._register_stock_signals()` | `_stock_receivers.on_holds_materialized` | Auto-commit de sessões aguardando produção |
| `production_changed` | `setup._register_stock_signals()` | `_stock_receivers.on_production_voided` | Libera demand holds quando produção é anulada |
| `production_changed` | `CraftingStockingConfig.ready()` | `craftsman.contrib.stockman.handlers` | Gerencia quants planejados/realizados |
| `post_save(Directive)` | `OrderingConfig.ready()` | `ordering.dispatch` | Auto-despacha directive para handler |
| `post_save(Move)` | `StockingAlertsConfig.ready()` | `alerts.handlers` | Verifica alertas de estoque baixo |

---

## Sinais por Módulo

### Offerman

**Arquivo:** `packages/offerman/shopman/offerman/signals/__init__.py`

#### product_created

Emitido quando um novo `Product` é salvo pela primeira vez.

| Campo | Valor |
|-------|-------|
| **Sender** | `Product` |
| **Payload** | `instance` (Product), `sku` (str) |
| **Receivers** | Nenhum conectado |

#### price_changed

Emitido quando o preço de um `ListingItem` muda.

| Campo | Valor |
|-------|-------|
| **Sender** | `ListingItem` |
| **Payload** | `instance` (ListingItem), `listing_ref` (str), `sku` (str), `old_price_q` (int), `new_price_q` (int) |
| **Receivers** | Nenhum conectado |

**Guia:** [offerman.md](../guides/offerman.md)

---

### Craftsman

**Arquivo:** `packages/craftsman/shopman/craftsman/signals/__init__.py`

#### production_changed

Emitido quando o estado de produção muda (planejar, ajustar, iniciar, finalizar, anular work order).

| Campo | Valor |
|-------|-------|
| **Sender** | `WorkOrder` |
| **Payload** | `product_ref` (str), `date` (date\|None), `action` (str), `work_order` (WorkOrder) |
| **Actions** | `"planned"`, `"adjusted"`, `"started"`, `"finished"`, `"voided"` |

**Receivers:**
1. `handle_production_changed()` em `craftsman/contrib/stockman/handlers.py` — Registrado por `CraftingStockingConfig.ready()`
2. `on_production_voided()` em `shopman/handlers/_stock_receivers.py` — Registrado por `setup.register_all()`. Libera demand holds quando produção é anulada

| Action | Efeito no Stockman |
|--------|-------------------|
| `planned` | Cria Quant planejado (`StockMovements.receive()`) |
| `adjusted` | Atualiza quantidade do Quant planejado |
| `started` | Marca o início operacional da ordem com `started_qty` |
| `finished` | Realiza produção com `finished_qty` e move estoque para posição vendável (`StockPlanning.realize()`) |
| `voided` | Zera Quant planejado |

**Guia:** [craftsman.md](../guides/craftsman.md)

---

### Stockman

**Arquivo:** `packages/stockman/shopman/stockman/signals.py`

#### holds_materialized

Emitido quando holds planejados são materializados (produção concluída, estoque real disponível).

| Campo | Valor |
|-------|-------|
| **Sender** | *(evento de domínio)* |
| **Payload** | `hold_ids` (list[str]), `sku` (str), `target_date` (date), `to_position` (Position) |

**Receiver:** `on_holds_materialized()` em `shopman/shop/handlers/_stock_receivers.py`
Registrado por: `ShopmanConfig.ready()` via `setup.register_all()` → `_register_stock_signals()`

**Efeito:** Auto-commit de sessões que estavam aguardando produção. Quando todos os holds de uma sessão são materializados, executa `CommitService.commit()` automaticamente.

**Guia:** [stockman.md](../guides/stockman.md), [flows.md](../guides/flows.md)

---

### Orderman

**Arquivo:** `packages/orderman/shopman/orderman/signals.py`

#### order_changed

Emitido quando um `Order` é criado ou muda de status.

| Campo | Valor |
|-------|-------|
| **Sender** | `Order` |
| **Payload** | `order` (Order), `event_type` (str), `actor` (str) |
| **Event types** | `"created"`, `"status_changed"`, etc. |

**Receivers:** Conectados em `ShopmanConfig.ready()`

| Receiver | Arquivo |
|----------|---------|
| `on_order_changed()` | `shopman/apps.py` → `flows.dispatch()` — resolve Flow class e chama `on_<phase>()` |

**Efeitos por `event_type`:**
- `"created"` → `dispatch(order, "on_commit")` → `Flow.on_commit()` (customer.ensure, stock.hold, confirmation)
  - Se `confirmation_mode == "immediate"` → auto-confirma
  - Se `confirmation_mode == "auto_confirm"` → cria directive `confirmation.timeout` (action=confirm)
  - Se `confirmation_mode == "auto_cancel"` → cria directive `confirmation.timeout` (action=cancel)
- `"status_changed"` → `dispatch(order, f"on_{status}")` → Flow method correspondente

**Guia:** [orderman.md](../guides/orderman.md), [flows.md](../guides/flows.md)

---

### Guestman

**Arquivo:** `packages/guestman/shopman/guestman/signals/__init__.py`

#### customer_created

Emitido por `CustomerService.create()` após criação de novo cliente.

| Campo | Valor |
|-------|-------|
| **Sender** | `Customer` |
| **Payload** | `instance` (Customer) |
| **Receivers** | Nenhum conectado |

#### customer_updated

Emitido por `CustomerService.update()` após atualização de cliente.

| Campo | Valor |
|-------|-------|
| **Sender** | `Customer` |
| **Payload** | `instance` (Customer), `changes` (dict) |
| **Receivers** | Nenhum conectado |

**Guia:** [guestman.md](../guides/guestman.md)

---

### Doorman

**Arquivo:** `packages/doorman/shopman/doorman/signals.py`

#### customer_authenticated

Emitido após autenticação bem-sucedida via Doorman.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Doorman)* |
| **Payload** | `customer` (AuthCustomerInfo), `user` (User), `method` (str), `request` (HttpRequest) |
| **Methods** | `"access_link"`, `"verification_code"` |
| **Receivers** | Nenhum conectado |

#### access_link_created

Emitido após criação de access link via `AccessLinkService.create_token()`.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Doorman)* |
| **Payload** | `token` (AccessLink), `customer` (AuthCustomerInfo), `audience` (str), `source` (str) |
| **Audiences** | `"web_checkout"`, `"web_account"`, etc. |
| **Sources** | `"manychat"`, `"internal"`, `"api"` |
| **Receivers** | Nenhum conectado |

#### verification_code_sent

Emitido após envio de código de verificação via `AuthService.request_code()`.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Doorman)* |
| **Payload** | `code` (VerificationCode), `target_value` (str), `delivery_method` (str) |
| **Delivery methods** | `"whatsapp"`, `"sms"`, `"email"` |
| **Receivers** | Nenhum conectado |

**Nota:** `code.code_hash` é HMAC — o código raw não é preservado no sinal.

#### verification_code_verified

Emitido após verificação bem-sucedida via `AuthService.verify_for_login()`.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Doorman)* |
| **Payload** | `code` (VerificationCode), `customer` (AuthCustomerInfo), `purpose` (str) |
| **Purposes** | `"login"`, `"verify_contact"` |
| **Receivers** | Nenhum conectado |

#### device_trusted

Emitido após criação de dispositivo confiável via `DeviceTrustService.trust_device()`.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Doorman)* |
| **Payload** | `device` (TrustedDevice), `customer_id` (UUID), `request` (HttpRequest) |
| **Receivers** | Nenhum conectado |

**Guia:** [doorman.md](../guides/doorman.md)

---

### Payman

**Arquivo:** `packages/payman/shopman/payman/signals/__init__.py`

#### payment_authorized

Emitido quando um `PaymentIntent` é autorizado (pending → authorized).

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Payman)* |
| **Payload** | `intent` (PaymentIntent), `order_ref` (str), `amount_q` (int), `method` (str) |
| **Receivers** | Nenhum conectado |

#### payment_captured

Emitido quando um `PaymentIntent` é capturado (authorized → captured).

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Payman)* |
| **Payload** | `intent` (PaymentIntent), `order_ref` (str), `amount_q` (int), `transaction` (PaymentTransaction) |
| **Receivers** | Nenhum conectado |

#### payment_failed

Emitido quando um `PaymentIntent` falha.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Payman)* |
| **Payload** | `intent` (PaymentIntent), `order_ref` (str), `error_code` (str), `message` (str) |
| **Receivers** | Nenhum conectado |

#### payment_cancelled

Emitido quando um `PaymentIntent` é cancelado.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Payman)* |
| **Payload** | `intent` (PaymentIntent), `order_ref` (str) |
| **Receivers** | Nenhum conectado |

#### payment_refunded

Emitido quando um reembolso é registrado.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Payman)* |
| **Payload** | `intent` (PaymentIntent), `order_ref` (str), `amount_q` (int), `transaction` (PaymentTransaction) |
| **Receivers** | Nenhum conectado |

---

## Sinais Built-in do Django

### post_save — Directive Dispatch

**Arquivo:** `packages/orderman/shopman/orderman/dispatch.py`
**Registrado por:** `OrderingConfig.ready()`
**dispatch_uid:** `"ordering.directive_dispatch"`

Quando uma `Directive` é criada (`created=True`), auto-despacha para o handler registrado. Inclui guard de reentrância para evitar cascata quando handlers criam child directives.

### post_save — Stock Alerts

**Arquivo:** `packages/stockman/shopman/stockman/contrib/alerts/handlers.py`
**Registrado por:** `StockingAlertsConfig.ready()`
**Sender:** `Move`

Quando um `Move` é criado, agenda verificação de alerta via `transaction.on_commit()`. Verifica se o nível de estoque caiu abaixo do mínimo configurado.

---

## Fluxo de Sinais — Exemplo Completo

```
Pedido criado
  └→ order_changed (event_type="created")
       └→ on_order_created()
            ├→ [auto-confirm] → Order → CONFIRMED
            │    └→ order_changed (event_type="status_changed")
            │         └→ on_order_status_changed()
            │              └→ directive: pix.generate (se PIX)
            └→ [manual] → directive: confirmation.timeout

Produção concluída
  └→ production_changed (action="finished")
       └→ handle_production_changed()
            └→ StockPlanning.realize()
                 └→ holds_materialized
                      └→ _on_holds_materialized()
                           └→ CommitService.commit() (auto-commit)
```
