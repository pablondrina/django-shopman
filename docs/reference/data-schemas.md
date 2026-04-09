# Data Schemas — JSONField Reference

> Inventário completo de chaves usadas nos JSONFields do Core e App.
> **Regra**: toda nova chave deve ser documentada aqui antes de ser usada.
> Ver também: [CLAUDE.md](../../CLAUDE.md) § "Core é Sagrado".

---

## Session.data

Unidade mutável pré-commit (carrinho/comanda). Populado pelo App (views, CartService, handlers).
O Core não impõe schema — a governança é por convenção documentada aqui.

### Chaves de negócio (populadas por views/services)

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `customer` | `dict` | CheckoutView, POS, API (`set_data`), iFood webhook | CommitService, handlers | Dados do cliente: `{name, phone, notes, ref, group, cpf, address}` |
| `fulfillment_type` | `string` | CheckoutView, POS, API, iFood webhook | CommitService, MinimumOrderValidator | `"pickup"` ou `"delivery"` |
| `delivery_address` | `string` | CheckoutView, API, iFood webhook | CommitService, CustomerIdentificationHandler | Endereço formatado (texto livre) |
| `delivery_date` | `string` | CheckoutView | CommitService | ISO date (`YYYY-MM-DD`). Se futuro, indica encomenda |
| `delivery_time_slot` | `string` | CheckoutView | CommitService | Faixa horária: `"manha"`, `"tarde"`, etc. |
| `order_notes` | `string` | CheckoutView, iFood webhook | CommitService | Observações do pedido |
| `origin_channel` | `string` | CartService, POS, iFood webhook | CommitService, hooks.py | Canal de origem: `"web"`, `"whatsapp"`, `"ifood"`, `"pos"`, `"instagram"` |
| `coupon_code` | `string` | CartService.apply_coupon | CouponModifier, CartService.get_cart_summary | Código do cupom aplicado (uppercase) |
| `availability` | `dict` | StockCheckHandler (via checks) | D1DiscountModifier | Mapa SKU → `{is_d1: bool}`. Flag D-1 por produto |
| `outside_business_hours` | `bool` | BusinessHoursRule (validation) | CheckoutView, CommitService | `True` se pedido feito fora do horário. Não bloqueia checkout — apenas flag informativa |
| `delivery_address_structured` | `dict` | CheckoutView (`set_data`) | CommitService | Endereço estruturado do Google Places: `{route, street_number, complement, neighborhood, city, state_code, postal_code, place_id, formatted_address, delivery_instructions, is_verified, latitude, longitude}` |
| `payment` | `dict` | CheckoutView (`set_data`), POS, API | CommitService, hooks, handlers | Dados de pagamento iniciais: `{method}`. Enriquecido por handlers pós-commit (intent_ref, status, etc.) |
| `delivery_fee_q` | `int` | DeliveryFeeModifier (via `session.save`) | CommitService, CartService, tracking view | Taxa de entrega em centavos. 0 = grátis. Só presente quando `fulfillment_type == "delivery"` e zona encontrada |
| `delivery_zone_error` | `bool` | DeliveryFeeModifier (via `session.save`) | DeliveryZoneRule validator | `True` quando endereço de entrega não está coberto por nenhuma DeliveryZone ativa. Bloqueia commit |
| `delivery_address_id` | `int` | `web/views/checkout.py` | `checkout_defaults.py` | FK para `CustomerAddress.pk`. Usada para inferir defaults na sessão. **Não propagada ao Order.data** — somente em Session.data |

### Chaves de sistema (geridas pelo Core)

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `checks` | `dict` | WriteCheckResultService, ModifyService (reset) | CommitService, StockReleaseHandler, CheckoutView | Resultados de checks: `{check_code: {rev, at, result}}` |
| `issues` | `list[dict]` | WriteCheckResultService, ModifyService (reset) | CommitService, ResolveIssueService, admin, CheckoutView | Issues de validação: `[{id, code, source, blocking, message, data}]` |

### Paths permitidos via `set_data` (OpSerializer)

O `ModifyService` aceita operações `set_data` nas seguintes paths:
`customer`, `delivery`, `payment`, `notes`, `meta`, `extra`, `custom`, `tags`,
`discounts`, `fees`, `tip`, `coupon`, `source`, `operator`, `table`, `tab`,
`fulfillment_type`, `delivery_address`, `delivery_address_structured`,
`delivery_date`, `delivery_time_slot`, `order_notes`.

Paths **proibidas** (geridas pelo sistema): `checks`, `issues`, `state`, `status`,
`rev`, `session_key`, `channel`, `items`, `pricing`, `pricing_trace`, `__`.

### Exemplo completo

```json
{
  "customer": {"name": "João Silva", "phone": "5543999990001", "notes": "Alergia a nozes"},
  "fulfillment_type": "delivery",
  "delivery_address": "Rua das Flores 123 - Centro - Londrina",
  "delivery_date": "2026-04-01",
  "delivery_time_slot": "manha",
  "order_notes": "Sem cebola",
  "origin_channel": "whatsapp",
  "coupon_code": "WELCOME10",
  "availability": {"CROIS-01": {"is_d1": true}},
  "checks": {
    "stock": {
      "rev": 3,
      "at": "2026-03-30T10:00:00Z",
      "result": {
        "holds": [{"hold_id": "H-1", "expires_at": "2026-03-30T10:30:00Z"}]
      }
    }
  },
  "issues": []
}
```

---

## Order.data

Pedido canônico (selado). Populado pelo CommitService (cópia de Session.data) e por handlers pós-commit.

### Chaves copiadas de Session.data (CommitService._do_commit)

A lista de chaves propagadas está explícita em `commit.py`, método `_do_commit()`:

```python
for key in (
    "customer", "fulfillment_type", "delivery_address",
    "delivery_address_structured", "delivery_date",
    "delivery_time_slot", "order_notes",
    "origin_channel", "payment",
    "delivery_fee_q",
):
```

**Para adicionar uma nova chave ao fluxo Session→Order, adicione-a nessa lista.**

### Chaves adicionadas por modifiers pré-commit (Session.data → Order.data)

| Chave | Tipo | Escrito por | Descrição |
|-------|------|-------------|-----------|
| `delivery_fee_q` | `int` | DeliveryFeeModifier | Taxa de entrega em centavos. 0 = grátis |

### Chaves computadas pelo CommitService

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `is_preorder` | `bool` | `True` se `delivery_date > hoje`. Calculado no commit |

### Chaves adicionadas por handlers pós-commit

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `payment` | `dict` | CommitService (propagado de Session.data), PaymentHandler, webhooks, hooks | Muitos (ver abaixo) | Dados de pagamento (ver detalhamento). `{method}` propagado pelo CommitService; enriquecido por handlers pós-commit (intent_ref, status, etc.) |
| `customer_ref` | `string` | CustomerIdentificationHandler | CheckoutInferDefaultsHandler | Ref do Customer criado/encontrado |
| `fulfillment_created` | `bool` | FulfillmentCreateHandler | FulfillmentCreateHandler (idempotência) | Flag: Fulfillment object criado |
| `cancellation_reason` | `string` | PixTimeoutHandler, PaymentTimeoutHandler, ConfirmationTimeoutHandler, OrderCancelView, GestorOrderRejectView | hooks._on_cancelled | Motivo: `"pix_timeout"`, `"card_timeout"`, `"confirmation_timeout"`, `"customer_requested"`, texto livre |
| `rejected_by` | `string` | GestorOrderRejectView | — | Username do operador que rejeitou |
| `internal_notes` | `string` | PedidoNotesView | PedidoDetailView | Notas internas do operador |
| `returns` | `list[dict]` | ReturnService | ReturnHandler | Histórico de devoluções (ver detalhamento) |
| `nfce_access_key` | `string` | NFCeEmitHandler | NFCeEmitHandler (idempotência), ReturnService | Chave de acesso NFCe |
| `nfce_number` | `int` | NFCeEmitHandler | — | Número do documento |
| `nfce_danfe_url` | `string` | NFCeEmitHandler | — | URL do DANFE PDF |
| `nfce_qrcode_url` | `string` | NFCeEmitHandler | — | URL do QR code |
| `nfce_cancelled` | `bool` | NFCeCancelHandler | NFCeCancelHandler (idempotência) | NFCe cancelada |
| `nfce_cancellation_protocol` | `string` | NFCeCancelHandler | — | Protocolo de cancelamento |
| `session_key` | `string` | hooks._on_cancelled | hooks._on_cancelled | Chave de sessão original (referência para release holds) |
| `hold_ids` | `list[str]` | `StockService.hold(order)` | `StockService.fulfill(order)`, `StockService.release(order)` | IDs dos holds do Stockman adotados no momento do commit |
| `loyalty` | `dict` | `LoyaltyRedeemModifier` | `services/loyalty.py` | Dados de resgate de pontos: `{redeem_points_q: int}` |


### Chaves lidas por views (convenience — fallback para vazio)

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `customer_name` | `string` | pedidos._enrich_order, kds._enrich_order | **Não escrito pela checkout padrão.** Falls back para `order.handle_ref`. Previsto para canais que achatam `customer.name` |
| `delivery_method` | `string` | pedidos._enrich_order, kds._enrich_order, PedidoAdvanceView | **Não escrito pela checkout padrão.** Falls back para `""`. Previsto para canais que usam `delivery_method` em vez de `fulfillment_type` |
| `customer_phone` | `string` | NotificationHandler._resolve_recipient | **Não escrito diretamente.** Fallback quando `customer.phone` não encontrado |

### payment — detalhamento

```json
{
  "method": "pix",
  "intent_ref": "INT-abc123",
  "status": "captured",
  "amount_q": 2500,
  "qr_code": "data:image/png;base64,...",
  "copy_paste": "00020126...",
  "expires_at": "2026-03-30T10:15:00Z",
  "e2e_id": "E123456789",
  "paid_amount_q": 2500,
  "captured_at": "2026-03-30T10:12:00Z",
  "client_secret": "pi_xxx_secret_yyy"
}
```

| Sub-chave | Tipo | Escrito por | Descrição |
|-----------|------|-------------|-----------|
| `method` | `string` | CheckoutView (via Session.data → CommitService), PixGenerateHandler, CardCreateHandler | `"pix"`, `"card"`, `"counter"`, `"external"` |
| `intent_ref` | `string` | PixGenerateHandler, CardCreateHandler | ID do intent no gateway |
| `status` | `string` | PixGenerateHandler, hooks.on_payment_confirmed | `"pending"`, `"captured"`, `"refunded"`, `"expired"`, `"failed"` |
| `amount_q` | `int` | PixGenerateHandler, CardCreateHandler | Valor em centavos |
| `qr_code` | `string` | PixGenerateHandler | QR code image (data URI) |
| `copy_paste` | `string` | PixGenerateHandler | Brcode PIX copia-e-cola |
| `expires_at` | `string` | PixGenerateHandler | ISO datetime de expiração do QR |
| `e2e_id` | `string` | EfiPixWebhook | End-to-end ID da transação PIX |
| `paid_amount_q` | `int` | EfiPixWebhook | Valor efetivamente pago |
| `captured_at` | `string` | MockPaymentConfirmView | ISO datetime de captura |
| `client_secret` | `string` | CardCreateHandler | Secret do Stripe PaymentIntent |

### returns — detalhamento

```json
[
  {
    "timestamp": "2026-04-01T14:30:00Z",
    "actor": "operador@loja.com",
    "reason": "Cliente insatisfeito",
    "type": "partial",
    "items": [
      {"line_id": "L1", "sku": "CROIS-01", "qty": 2, "refund_q": 1500}
    ],
    "refund_total_q": 1500,
    "refund_processed": true
  }
]
```

### Exemplo completo (Order.data)

```json
{
  "customer": {"name": "João Silva", "phone": "5543999990001"},
  "fulfillment_type": "delivery",
  "delivery_address": "Rua das Flores 123",
  "delivery_address_structured": {
    "route": "Rua das Flores",
    "street_number": "123",
    "neighborhood": "Centro",
    "city": "Londrina",
    "state_code": "PR",
    "postal_code": "86020-000",
    "formatted_address": "Rua das Flores 123, Centro, Londrina - PR",
    "latitude": -23.31,
    "longitude": -51.16,
    "is_verified": true
  },
  "delivery_date": "2026-04-02",
  "delivery_time_slot": "manha",
  "order_notes": "Sem cebola",
  "origin_channel": "web",
  "is_preorder": true,
  "payment": {
    "method": "pix",
    "intent_ref": "INT-abc123",
    "status": "captured",
    "amount_q": 2500,
    "e2e_id": "E123456789",
    "paid_amount_q": 2500
  },
  "customer_ref": "CUST-001",
  "fulfillment_created": true,
  "session_key": "sk_abc123"
}
```

---

## Order.snapshot

Snapshot selado do pedido no momento da criação. **Imutável** — nunca editado após o commit.
Escrito uma única vez por `CommitService._do_commit()`.

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `items` | `list[dict]` | hooks._build_directive_payload (stock.hold), customers.OrderingOrderHistoryBackend | Itens da sessão: `[{line_id, sku, name, qty, unit_price_q, line_total_q, meta, is_d1?}]` — `is_d1` opcional, setado na inclusão quando o estoque é só D-1 (alinhado à vitrine) |
| `data` | `dict` | handlers/customer.py (fallback), hooks (stock.commit holds) | Cópia integral de `session.data` no momento do commit |
| `pricing` | `dict` | customers.OrderingOrderHistoryBackend | Pricing da sessão: `{total_q, subtotal_q, discount_q, ...}` |
| `rev` | `int` | hooks._build_directive_payload (stock.hold) | Revisão da sessão no commit |

### Exemplo completo

```json
{
  "items": [
    {
      "line_id": "L1",
      "sku": "CROIS-01",
      "name": "Croissant Clássico",
      "qty": 2,
      "unit_price_q": 750,
      "line_total_q": 1500,
      "meta": {}
    }
  ],
  "data": {
    "customer": {"name": "João Silva", "phone": "5543999990001"},
    "fulfillment_type": "pickup",
    "origin_channel": "web",
    "checks": {"stock": {"rev": 1, "at": "...", "result": {"holds": []}}},
    "issues": []
  },
  "pricing": {
    "subtotal_q": 1500,
    "discount_q": 0,
    "total_q": 1500
  },
  "rev": 1
}
```

---

## Directive.payload

Payload da tarefa assíncrona. Schema varia por `topic`.

### Chaves comuns (presentes na maioria dos directives)

| Chave | Tipo | Presente em | Escrito por | Descrição |
|-------|------|-------------|-------------|-----------|
| `order_ref` | `string` | Todos exceto admin checks | hooks._build_directive_payload | Ref do pedido |
| `channel_ref` | `string` | stock.*, payment.capture | hooks._build_directive_payload | Ref do canal |
| `session_key` | `string` | stock.*, payment.capture, admin checks | hooks._build_directive_payload | Chave da sessão original |
| `origin_channel` | `string` | Directives gerados por hooks | hooks._build_directive_payload | Canal de origem (informativo) |

### Payloads por topic

#### `stock.hold`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | StockHoldHandler |
| `channel_ref` | `string` | hooks | StockHoldHandler |
| `session_key` | `string` | hooks | StockHoldHandler |
| `rev` | `int` | hooks | StockHoldHandler (stale check) |
| `items` | `list[dict]` | hooks | StockHoldHandler |

Write-back: `holds` (list de hold objects do backend)

#### `stock.commit`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | StockCommitHandler |
| `channel_ref` | `string` | hooks | StockCommitHandler |
| `holds` | `list[dict]` | hooks (from snapshot checks) | StockCommitHandler |

#### `confirmation.timeout`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks._on_order_created | ConfirmationTimeoutHandler |
| `expires_at` | `string` | hooks._on_order_created | ConfirmationTimeoutHandler |

#### `pix.generate`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | PixGenerateHandler |
| `amount_q` | `int` | hooks | PixGenerateHandler |
| `pix_timeout_minutes` | `int` | hooks (from channel config) | PixGenerateHandler (default 10) |

Write-back: spawns `pix.timeout` e `notification.send` (reminder)

#### `pix.timeout`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | PixGenerateHandler | PixTimeoutHandler |
| `intent_ref` | `string` | PixGenerateHandler | PixTimeoutHandler |
| `expires_at` | `string` | PixGenerateHandler | PixTimeoutHandler |

#### `payment.capture`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks / web view | PaymentCaptureHandler |
| `intent_ref` | `string` | hooks / web view | PaymentCaptureHandler |
| `amount_q` | `int` | hooks / web view | PaymentCaptureHandler |
| `session_key` | `string` | hooks (opcional) | PaymentCaptureHandler (fallback lookup) |
| `channel_ref` | `string` | hooks (opcional) | PaymentCaptureHandler (fallback lookup) |
| `method` | `string` | web view (opcional) | PaymentCaptureHandler |

Write-back: `transaction_id` (string)

#### `payment.timeout`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | PaymentTimeoutHandler |
| `intent_ref` | `string` | hooks | PaymentTimeoutHandler |
| `expires_at` | `string` | hooks | PaymentTimeoutHandler |
| `method` | `string` | hooks | PaymentTimeoutHandler (default `"card"`) |

#### `payment.refund`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks.on_payment_confirmed | PaymentRefundHandler |
| `intent_ref` | `string` | hooks.on_payment_confirmed | PaymentRefundHandler |
| `amount_q` | `int` | hooks.on_payment_confirmed | PaymentRefundHandler |
| `reason` | `string` | hooks.on_payment_confirmed | PaymentRefundHandler |

Write-back: `refund_id` (string)

#### `card.create`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | CardCreateHandler |
| `amount_q` | `int` | hooks | CardCreateHandler |

Write-back: `intent_ref` (string)

#### `notification.send` (order notification)

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks, handlers | NotificationSendHandler |
| `template` | `string` | hooks (pipeline `topic:template`), handlers | NotificationSendHandler (default `"generic"`) |
| `origin_channel` | `string` | hooks | NotificationSendHandler (informativo) |
| `reason` | `string` | handlers (cancelamento) | NotificationSendHandler._build_context |
| `amount_q` | `int` | PixGenerateHandler (reminder) | NotificationSendHandler (informativo) |
| `copy_paste` | `string` | PixGenerateHandler (reminder) | Template (não handler) |
| `tracking` | `dict` | FulfillmentUpdateHandler | Template (não handler) |
| `context` | `dict` | CommitService (preorder reminder) | Template (não handler) |

Templates de notificação: `"order_confirmed"`, `"order_cancelled"`, `"order_cancelled_by_customer"`,
`"order_rejected"`, `"order_processing"`, `"order_ready"`, `"order_dispatched"`, `"order_delivered"`,
`"payment_confirmed"`, `"payment_expired"`, `"payment.reminder"`, `"preorder_reminder"`,
`"production_cancelled"`, `"generic"`.

#### `notification.send` (system notification)

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `event` | `string` | stock alerts, _stock_receivers | NotificationSendHandler |
| `context` | `dict` | stock alerts, _stock_receivers | NotificationSendHandler |

Valores de `event`: `"stock.alert.triggered"`, `"system"`.

#### `fiscal.emit_nfce`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | NFCeEmitHandler |
| `items` | `list[dict]` | hooks | NFCeEmitHandler |
| `payment` | `dict` | hooks | NFCeEmitHandler |
| `customer` | `dict` | hooks (opcional) | NFCeEmitHandler |
| `additional_info` | `string` | hooks (opcional) | NFCeEmitHandler |

#### `fiscal.cancel_nfce`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | NFCeCancelHandler |
| `reason` | `string` | hooks | NFCeCancelHandler |

#### `return.process`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | ReturnService | ReturnHandler |
| `items` | `list[dict]` | ReturnService | ReturnHandler |
| `refund_total_q` | `int` | ReturnService | ReturnHandler |
| `return_index` | `int` | ReturnService | ReturnHandler (default 0) |

#### `fulfillment.create`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | FulfillmentCreateHandler |
| `channel_ref` | `string` | hooks | FulfillmentCreateHandler |

#### `fulfillment.update`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | FulfillmentUpdateHandler |
| `fulfillment_id` | `string` | hooks | FulfillmentUpdateHandler |
| `new_status` | `string` | hooks | FulfillmentUpdateHandler |
| `tracking_code` | `string` | hooks (opcional) | FulfillmentUpdateHandler |
| `carrier` | `string` | hooks (opcional) | FulfillmentUpdateHandler |

#### `loyalty.earn`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | LoyaltyEarnHandler |

#### `customer.ensure`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | CustomerEnsureHandler |
| `channel_ref` | `string` | hooks | CustomerEnsureHandler |

#### `checkout.infer_defaults`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | CheckoutInferDefaultsHandler |

#### `accounting.create_payable`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `reference` | `string` | externo (opcional) | PurchaseToPayableHandler |
| `description` | `string` | externo | PurchaseToPayableHandler |
| `amount_q` | `int` | externo | PurchaseToPayableHandler |
| `due_date` | `string` | externo | PurchaseToPayableHandler |
| `category` | `string` | externo | PurchaseToPayableHandler |
| `supplier_name` | `string` | externo (opcional) | PurchaseToPayableHandler |
| `notes` | `string` | externo (opcional) | PurchaseToPayableHandler |

Write-back: `entry_id` (string)

---

## Channel.config

Configuração do canal. Schema formal via `ChannelConfig` dataclass (7 aspectos) em `shopman/config.py`.

### Cascata de configuração

```
ChannelConfig.defaults() ← Shop.defaults ← Channel.config
```

O método `ChannelConfig.effective(channel)` faz o merge profundo (deep_merge).
Chave ausente no override = herda. Chave presente (mesmo None) = sobreescreve.

### 1. Confirmation — como o pedido é aceito?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `mode` | `string` | `"immediate"` | `"immediate"` (auto-confirma), `"optimistic"` (auto-confirma após timeout), `"pessimistic"` (cancela após timeout), `"manual"` (aguarda) |
| `timeout_minutes` | `int` | `5` | Timeout para modes optimistic/pessimistic |

Lido por: `hooks._on_order_created`, `ConfirmationTimeoutHandler`, `confirmation.py` helpers, `CheckoutView`, `TrackingView`.

### 2. Payment — como o cliente paga?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `method` | `string \| list[str]` | `"counter"` | `"counter"`, `"pix"`, `"card"`, `"external"`, ou lista |
| `timeout_minutes` | `int` | `15` | Timeout para PIX/card. Card timeout = `timeout_minutes * 2` |

Property: `available_methods` → sempre retorna lista.

Lido por: `hooks._build_directive_payload`, `hooks._maybe_schedule_card_timeout`, `confirmation.py` helpers, `CheckoutView._get_payment_methods`.

### 3. Stock — comportamento de reserva de estoque

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `hold_ttl_minutes` | `int \| None` | `None` | TTL das reservas. None = sem expiração |
| `safety_margin` | `int` | `0` | Margem de segurança (unidades a subtrair do disponível) |
| `planned_hold_ttl_hours` | `int` | `48` | TTL para holds planejados (fermata) |
| `allowed_positions` | `list[str] \| None` | `None` | Posições de estoque aceitas. None = todas vendáveis |

Lido por: `StockHoldHandler`, `confirmation.py` helpers, `apps._validate_hold_ttl`.

### 4. Pipeline — o que acontece em cada fase?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `on_commit` | `list[str]` | `[]` | Directives ao criar pedido |
| `on_confirmed` | `list[str]` | `[]` | Directives ao confirmar |
| `on_processing` | `list[str]` | `[]` | Directives ao iniciar preparo |
| `on_ready` | `list[str]` | `[]` | Directives ao ficar pronto |
| `on_dispatched` | `list[str]` | `[]` | Directives ao despachar |
| `on_delivered` | `list[str]` | `[]` | Directives ao entregar |
| `on_completed` | `list[str]` | `[]` | Directives ao completar |
| `on_cancelled` | `list[str]` | `[]` | Directives ao cancelar |
| `on_returned` | `list[str]` | `[]` | Directives ao devolver |
| `on_payment_confirmed` | `list[str]` | `[]` | Directives ao confirmar pagamento |

Notação: `"topic:template"` para notificações com template (ex: `"notification.send:order_confirmed"`).

Lido por: `hooks.on_order_lifecycle`, `hooks._on_order_created`, `hooks.on_payment_confirmed`.

### 5. Notifications — por onde avisamos?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `backend` | `string` | `"manychat"` | Backend primário: `"manychat"`, `"email"`, `"console"`, `"sms"`, `"webhook"`, `"whatsapp"`, `"none"` |
| `fallback_chain` | `list[str]` | `["sms", "email"]` | Cadeia de fallback se primário falhar |
| `routing` | `dict \| None` | `None` | Roteamento por tipo de notificação (reservado) |

Lido por: `NotificationHandler._resolve_backend_chain`, `setup._check_registered_backends`.

### 6. Rules — quais validators/modifiers ativar?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `validators` | `list[str]` | `[]` | Validators ativos: `"business_hours"`, `"min_order"` |
| `modifiers` | `list[str]` | `[]` | Modifiers ativos: `"shop.discount"`, `"shop.employee_discount"`, `"shop.happy_hour"` |
| `checks` | `list[str]` | `[]` | Checks obrigatórios: `"stock"` |

Lido por: `setup.py` (registro), validators, modifiers.

### 7. Flow — como o pedido transita entre status?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `transitions` | `dict \| None` | `None` | Transições permitidas: `{status: [status, ...]}` |
| `terminal_statuses` | `list[str] \| None` | `None` | Status terminais (não transitam mais) |
| `auto_transitions` | `dict \| None` | `None` | Transições automáticas: `{"on_payment_confirm": "processing"}` |
| `auto_sync_fulfillment` | `bool` | `False` | Sync automático fulfillment → order status |

Lido por: `hooks.on_payment_confirmed`, `FulfillmentUpdateHandler`.

### Chaves legadas (fora do ChannelConfig schema)

Estas chaves são lidas diretamente de `channel.config` como dict bruto, sem passar pelo `ChannelConfig`:

| Chave | Lido por | Descrição |
|-------|----------|-----------|
| `pix.timeout_minutes` | hooks._build_directive_payload | Legado: agora via `payment.timeout_minutes` |
| `cutoff_hour` | CheckoutView._get_cutoff_info | Hora de corte para pedidos do dia (default 18) |
| `required_checks_on_commit` | StockCheckValidator, CommitService | Lista de checks obrigatórios no commit |
| `stock.checkout_hold_expiration_minutes` | StockHoldHandler._get_hold_ttl | Legado: agora via `stock.hold_ttl_minutes` |
| `rules.d1_discount_percent` | D1DiscountModifier, _helpers | Percentual de desconto D-1 |
| `rules.minimum_order_q` | _helpers._minimum_order_progress | Valor mínimo de pedido (centavos) |
| `notification_routing` | NotificationHandler | Legado: agora via `notifications` |
| `confirmation_flow.*` | confirmation.py helpers | Legado: agora via `confirmation.*` e `payment.*` |

### Presets

| Preset | Confirmation | Payment | Stock TTL | Notifications | Validators |
|--------|-------------|---------|-----------|---------------|------------|
| `pos()` | immediate | counter | 5 min | console | business_hours |
| `remote()` | optimistic/5min | [pix, card]/15min | 30 min | manychat | business_hours, min_order |
| `whatsapp()` | optimistic/5min | [pix, card]/15min | 30 min | whatsapp | business_hours, min_order |
| `marketplace()` | pessimistic/5min | external | None | none | (vazio) |

---

## Regras de Governança

1. **Toda nova chave** em qualquer JSONField deve ser adicionada a este documento antes do merge.
2. **CommitService** é o único caminho Session.data → Order.data. A lista de chaves é explícita em `_do_commit()`.
3. **Handlers** escrevem apenas nas chaves documentadas na sua seção.
4. **Nenhum handler lê chave de outro handler** sem contrato documentado aqui.
5. **Nome da chave**: snake_case, descritivo, sem prefixo redundante (ex: `origin_channel`, não `session_origin_channel`).
6. **Tipo**: consistente. Valores monetários sempre `_q` (int centavos). Datas sempre ISO string.
7. **CommitService propaga exatamente estas chaves**: `customer`, `fulfillment_type`, `delivery_address`, `delivery_address_structured`, `delivery_date`, `delivery_time_slot`, `order_notes`, `origin_channel`, `payment`, `delivery_fee_q`. Mais `is_preorder` (computado).
8. **Order.snapshot é imutável**. Nunca editar após o commit. Contém `items`, `data`, `pricing`, `rev`.
9. **Directive.payload varia por topic**. Cada handler documenta as chaves que lê e escreve na sua seção acima.
10. **Channel.config usa ChannelConfig dataclass**. Chaves fora do schema devem ser documentadas na seção "Chaves legadas".
