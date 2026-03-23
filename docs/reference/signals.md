# Referência de Sinais (Signals)

> Gerado a partir dos arquivos `signals.py`, `signals/`, `receivers.py` e `hooks.py` do código atual.

---

## Visão Geral

O projeto define **12 sinais custom** do Django. Destes, **3 estão ativamente conectados** a receivers, e **9 estão definidos** para uso por extensões e integrações futuras.

| Sinal | Módulo | Status | Receivers |
|-------|--------|--------|-----------|
| [`product_created`](#product_created) | offering | Disponível | — |
| [`price_changed`](#price_changed) | offering | Disponível | — |
| [`production_changed`](#production_changed) | crafting | **Ativo** | crafting→stocking |
| [`customer_created`](#customer_created) | attending | Disponível | — |
| [`customer_updated`](#customer_updated) | attending | Disponível | — |
| [`holds_materialized`](#holds_materialized) | stocking | **Ativo** | stock→ordering |
| [`order_changed`](#order_changed) | ordering | **Ativo** | confirmation hooks |
| [`customer_authenticated`](#customer_authenticated) | gating | Disponível | — |
| [`bridge_token_created`](#bridge_token_created) | gating | Disponível | — |
| [`magic_code_sent`](#magic_code_sent) | gating | Disponível | — |
| [`magic_code_verified`](#magic_code_verified) | gating | Disponível | — |
| [`device_trusted`](#device_trusted) | gating | Disponível | — |

Além dos sinais custom, o projeto usa **2 sinais built-in** do Django (`post_save`) para dispatch de directives e alertas de estoque.

---

## Sinais por Módulo

### Offering

**Arquivo:** `shopman-core/offering/shopman/offering/signals/__init__.py`

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
| **Payload** | `instance` (ListingItem), `listing_code` (str), `sku` (str), `old_price_q` (int), `new_price_q` (int) |
| **Receivers** | Nenhum conectado |

**Guia:** [offering.md](../guides/offering.md)

---

### Crafting

**Arquivo:** `shopman-core/crafting/shopman/crafting/signals/__init__.py`

#### production_changed

Emitido quando o estado de produção muda (planejar, ajustar, fechar, anular work order).

| Campo | Valor |
|-------|-------|
| **Sender** | `WorkOrder` |
| **Payload** | `product_ref` (str), `date` (date\|None), `action` (str), `work_order` (WorkOrder) |
| **Actions** | `"planned"`, `"adjusted"`, `"closed"`, `"voided"` |

**Receiver:** `handle_production_changed()` em `crafting/contrib/stocking/handlers.py`
Registrado por: `CraftingStockingConfig.ready()`

| Action | Efeito no Stocking |
|--------|-------------------|
| `planned` | Cria Quant planejado (`StockMovements.receive()`) |
| `adjusted` | Atualiza quantidade do Quant planejado |
| `voided` | Zera Quant planejado |
| `closed` | Realiza produção — move estoque para posição vendável (`StockPlanning.realize()`) |

**Guia:** [crafting.md](../guides/crafting.md)

---

### Stocking

**Arquivo:** `shopman-core/stocking/shopman/stocking/signals.py`

#### holds_materialized

Emitido quando holds planejados são materializados (produção concluída, estoque real disponível).

| Campo | Valor |
|-------|-------|
| **Sender** | *(evento de domínio)* |
| **Payload** | `hold_ids` (list[str]), `sku` (str), `target_date` (date), `to_position` (Position) |

**Receiver:** `_on_holds_materialized()` em `shopman-app/shopman/stock/receivers.py`
Registrado por: `StockConfig.ready()` via `connect_signals()`

**Efeito:** Auto-commit de sessões que estavam aguardando produção. Quando todos os holds de uma sessão são materializados, executa `CommitService.commit()` automaticamente.

**Guia:** [stocking.md](../guides/stocking.md), [orchestration.md](../guides/orchestration.md)

---

### Ordering

**Arquivo:** `shopman-core/ordering/shopman/ordering/signals.py`

#### order_changed

Emitido quando um `Order` é criado ou muda de status.

| Campo | Valor |
|-------|-------|
| **Sender** | `Order` |
| **Payload** | `order` (Order), `event_type` (str), `actor` (str) |
| **Event types** | `"created"`, `"status_changed"`, etc. |

**Receivers (via hooks):** Conectados em `ConfirmationConfig.ready()`

| Receiver | Filtro | Arquivo |
|----------|--------|---------|
| `on_order_status_changed()` | Todos os eventos | `confirmation/hooks.py` |
| `on_order_created()` | `event_type == "created"` | `confirmation/hooks.py` |

**Efeito `on_order_created`:**
- Canal com auto-confirm → transiciona pedido para CONFIRMED imediatamente
- Canal sem auto-confirm → cria directive `confirmation.timeout`

**Efeito `on_order_status_changed`:**
- Se canal requer prepayment PIX → cria directive `pix.generate`

**Guia:** [ordering.md](../guides/ordering.md), [orchestration.md](../guides/orchestration.md)

---

### Attending

**Arquivo:** `shopman-core/attending/shopman/attending/signals/__init__.py`

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

**Guia:** [attending.md](../guides/attending.md)

---

### Gating

**Arquivo:** `shopman-core/gating/shopman/gating/signals.py`

#### customer_authenticated

Emitido após autenticação bem-sucedida via Gating.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Gating)* |
| **Payload** | `customer` (GatingCustomerInfo), `user` (User), `method` (str), `request` (HttpRequest) |
| **Methods** | `"bridge_token"`, `"magic_code"` |
| **Receivers** | Nenhum conectado |

#### bridge_token_created

Emitido após criação de bridge token via `AuthBridgeService.create_token()`.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Gating)* |
| **Payload** | `token` (BridgeToken), `customer` (GatingCustomerInfo), `audience` (str), `source` (str) |
| **Audiences** | `"web_checkout"`, `"web_account"`, etc. |
| **Sources** | `"manychat"`, `"internal"`, `"api"` |
| **Receivers** | Nenhum conectado |

#### magic_code_sent

Emitido após envio de código de verificação via `VerificationService.request_code()`.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Gating)* |
| **Payload** | `code` (MagicCode), `target_value` (str), `delivery_method` (str) |
| **Delivery methods** | `"whatsapp"`, `"sms"`, `"email"` |
| **Receivers** | Nenhum conectado |

**Nota:** `code.code_hash` é HMAC — o código raw não é preservado no sinal.

#### magic_code_verified

Emitido após verificação bem-sucedida via `VerificationService.verify_for_login()`.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Gating)* |
| **Payload** | `code` (MagicCode), `customer` (GatingCustomerInfo), `purpose` (str) |
| **Purposes** | `"login"`, `"verify_contact"` |
| **Receivers** | Nenhum conectado |

#### device_trusted

Emitido após criação de dispositivo confiável via `DeviceTrustService.trust_device()`.

| Campo | Valor |
|-------|-------|
| **Sender** | *(contexto Gating)* |
| **Payload** | `device` (TrustedDevice), `customer_id` (UUID), `request` (HttpRequest) |
| **Receivers** | Nenhum conectado |

**Guia:** [gating.md](../guides/gating.md)

---

## Sinais Built-in do Django

### post_save — Directive Dispatch

**Arquivo:** `shopman-core/ordering/shopman/ordering/dispatch.py`
**Registrado por:** `OrderingConfig.ready()`
**dispatch_uid:** `"ordering.directive_dispatch"`

Quando uma `Directive` é criada (`created=True`), auto-despacha para o handler registrado. Inclui guard de reentrância para evitar cascata quando handlers criam child directives.

### post_save — Stock Alerts

**Arquivo:** `shopman-core/stocking/shopman/stocking/contrib/alerts/handlers.py`
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
  └→ production_changed (action="closed")
       └→ handle_production_changed()
            └→ StockPlanning.realize()
                 └→ holds_materialized
                      └→ _on_holds_materialized()
                           └→ CommitService.commit() (auto-commit)
```
