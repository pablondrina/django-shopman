# Data Schemas — JSONField Reference

> Inventário completo de chaves usadas nos JSONFields do Core e App.
> **Regra**: toda nova chave deve ser documentada aqui antes de ser usada.
> Ver também: [CLAUDE.md](../../CLAUDE.md) § "Core é Sagrado".

---

## Session.data

Unidade mutável pré-commit (carrinho). Populado pelo App (views, CartService, handlers).
O Core não impõe schema — a governança é por convenção documentada aqui.

### Chaves de negócio (populadas por views/services)

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `customer` | `dict` | CheckoutView, POS, API (`set_data`), iFood webhook | CommitService, handlers | Dados do cliente: `{name, phone, notes, ref, group, cpf, address}` |
| `fulfillment_type` | `string` | CheckoutView, POS, API, iFood webhook | CommitService, MinimumOrderValidator | `"pickup"` ou `"delivery"` |
| `delivery_address` | `string` | CheckoutView, API, iFood webhook | CommitService, CustomerIdentificationHandler | Endereço formatado (texto livre) |
| `delivery_date` | `string` | CheckoutView | CommitService | ISO date (`YYYY-MM-DD`). Se futuro, indica encomenda |
| `delivery_time_slot` | `string` | CheckoutView | CommitService | Ref do slot configurado em `Shop.defaults["pickup_slots"]` (`"slot-09"`, `"slot-12"`, `"slot-15"`); o label ("A partir das 09h") resolve via `storefront.services.pickup_slots.slot_label` |
| `order_notes` | `string` | CheckoutView, iFood webhook | CommitService, KDS ticket (`customer_note`) | Observações do pedido escritas pelo **cliente** no checkout. Exibida no ticket do KDS (nota do cliente). Distinta da `kitchen_note` (nota do operador) |
| `origin_channel` | `string` | CartService, POS, iFood webhook | CommitService, hooks.py | Canal de origem: `"web"`, `"whatsapp"`, `"ifood"`, `"pos"`, `"instagram"` |
| `coupon_code` | `string` | CartService.apply_coupon | CouponModifier, CartService.get_cart_summary | Código do cupom aplicado (uppercase) |
| `availability` | `dict` | StockCheckHandler (via checks) | D1DiscountModifier | Mapa SKU → `{is_d1: bool}`. Flag D-1 por produto |
| `outside_business_hours` | `bool` | BusinessHoursRule (validation) | CheckoutView, CommitService | `True` se pedido feito fora do horário. Não bloqueia checkout — apenas flag informativa |
| `delivery_address_structured` | `dict` | CheckoutView (`set_data`) | CommitService | Endereço estruturado do Google Places: `{route, street_number, complement, neighborhood, city, state_code, postal_code, place_id, formatted_address, delivery_instructions, is_verified, latitude, longitude}` |
| `payment` | `dict` | CheckoutView (`set_data`), POS, API | CommitService, hooks, handlers | Dados de pagamento iniciais: `{method}` (+ `change_for_q` em centavos quando dinheiro **na entrega** e o cliente pediu troco). Enriquecido por handlers pós-commit (intent_ref, status, etc.) |
| `delivery_fee_q` | `int` | DeliveryFeeModifier (via `session.save`) | CommitService, CartService, tracking view | Taxa de entrega efetiva em centavos. 0 = grátis (faixa/zona grátis ou subtotal ≥ `rules.free_delivery_above_q`). Resolvida por **faixa de distância** (`DeliveryDistanceBand`, motor) com **zona** (`DeliveryZone` modo `override`) como exceção. Só presente quando `fulfillment_type == "delivery"` e há cobertura. Reavaliada a cada passagem dos modifiers (depende do subtotal). Mapeável a `vFrete` na NF-e — **nunca** vira OrderItem |
| `delivery_zone_error` | `bool` | DeliveryFeeModifier (via `session.save`) | DeliveryZoneRule validator | `True` quando o endereço está fora da área: sem faixa de distância que o cubra, ou zona `exclude` casada. Bloqueia commit |
| `delivery_distance_km` | `float` | DeliveryFeeModifier (via `session.save`) | checkout/tracking (transparência) | Distância loja→endereço em km (1 casa), quando calculável (lat/lng presentes). Exibida ao cliente p/ justificar a taxa. Ausente quando não há coordenada |
| `delivery_address_id` | `int` | `web/views/checkout.py` | `checkout_defaults.py` | FK para `CustomerAddress.pk`. Usada para inferir defaults na sessão. **Não propagada ao Order.data** — somente em Session.data |
| `stock_check_unavailable` | `list[dict]` | `lifecycle._check_availability` (via `check_on_commit`) | — | SKUs rejeitados por indisponibilidade durante check pré-commit. Cada entry: `{sku, error_code}`. Presente quando pedido é cancelado por `auto_reject_unavailable` |
| `manual_discount` | `dict` | POS `pos_close` view | `ModifyService` (via `set_data`) | Desconto manual do operador: `{type, value, discount_q, reason}`. `type`: `"percent"` ou `"fixed"` |
| `tab_ref` | `string` | POS tab service | POS tab service, projections | Referência canônica da comanda. Aceita texto curto alfanumérico; referências numéricas de até 8 dígitos continuam normalizadas com zeros. Ex: `"00001007"`, `"MESA ANA"` |
| `tab_display` | `string` | POS tab service | POS UI, Order.data | Rótulo curto para operador. Em numéricos, remove zeros à esquerda; em texto, preserva o rótulo informado. Ex: `"1007"`, `"mesa ana"` |
| `pos_operator` | `string` | POS tab service | POS projections, Order.data | Username do operador que abriu/tocou o POS tab |
| `last_touched_at` | `string` | POS tab service | POS projections | Timestamp ISO da última interação operacional |
| `fired_lines` | `list[str]` | POS `fire_pos_tab` (`session.save`) | `_tab_payload` (flag `fired` por item) | Marker UI de quais `line_id` da comanda já foram disparados à cozinha (KDS). Mirror do ledger autoritativo (tickets KDS por `session_key`, que sobrevive ao commit); escrito direto, sem re-pricing. Disparo progressivo curso-a-curso. **Não propagado ao Order.data** — o ledger pós-commit são os próprios `KDSTicket` |
| `fiscal` | `dict` | POS checkout | Order.data | Preferências fiscais capturadas no checkout: `{issue_document, tax_id}` |
| `receipt` | `dict` | POS checkout | Order.data | Preferência de recibo: `{mode, email}` |
| `is_gift` | `bool` | CheckoutView, API (`set_data`) | CommitService, KDS/expedição | `True` quando o pedido é presente (entrega para terceiro). Só presente quando é presente. Ver [GIFT-UX-PLAN](../plans/GIFT-UX-PLAN.md) |
| `recipient` | `dict` | CheckoutView, API (`set_data`) | CommitService, KDS/expedição | Destinatário do presente: `{name, phone}`. **Não** é identidade (não vira Customer) nem sobrescreve o comprador. Integridade garantida por `intents.gift.build_gift_data` (nunca parcial). **Obrigatório só na ENTREGA**; em retirada ("embalar para presente") é opcional/omitido |
| `gift_message` | `string` | CheckoutView, API (`set_data`) | CommitService | Mensagem do presente para o destinatário. **Separada** de `order_notes` (operacional/cozinha). Opcional; só presente quando informada |
| `gift_hide_values` | `bool` | CheckoutView, API (`set_data`) | CommitService, nota/etiqueta, KDS | `True` para ocultar valores na nota/etiqueta do presente. Só presente quando `True` (ausência = mostrar valores) |
| `customer_rating` | `dict` | `OrderRateView` (storefront tracking) | (futuro: agregação/relatórios) | Avaliação do pedido pelo cliente: `{rating, comment, submitted_at, source}`. Só presente após o cliente avaliar. Ver [[project_customer_rating_intent]] (sistema de avaliação é nice-to-have futuro) |

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
`delivery_date`, `delivery_time_slot`, `order_notes`,
`is_gift`, `recipient`, `gift_message`, `gift_hide_values`.

Paths **proibidas** (geridas pelo sistema): `checks`, `issues`, `state`, `status`,
`rev`, `session_key`, `channel`, `items`, `pricing`, `pricing_trace`, `__`.

### Exemplo completo

```json
{
  "customer": {"name": "João Silva", "phone": "5543999990001", "notes": "Alergia a nozes"},
  "fulfillment_type": "delivery",
  "delivery_address": "Rua das Flores 123 - Centro - Londrina",
  "delivery_date": "2026-04-01",
  "delivery_time_slot": "slot-09",
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
    "is_gift", "recipient", "gift_message", "gift_hide_values",
):
```

> `is_gift` / `recipient` / `gift_message` — presente (entrega para terceiro),
> ver [GIFT-UX-PLAN](../plans/GIFT-UX-PLAN.md). Só presentes quando o pedido é
> presente; a integridade (recipient nunca parcial) é garantida na escrita por
> `shopman.storefront.intents.gift.build_gift_data`.

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
| `payment` | `dict` | CommitService (propaga `{method}` de Session.data), `payment.initiate()`, webhooks | Muitos (ver abaixo) | Dados de pagamento. Contrato: `{intent_ref, method}`. Status de pagamento vive em Payman — nunca duplicado aqui. Ver detalhamento abaixo. |
| `customer_ref` | `string` | CustomerIdentificationHandler | CheckoutInferDefaultsHandler | Ref do Customer criado/encontrado |
| `fulfillment_created` | `bool` | FulfillmentCreateHandler | FulfillmentCreateHandler (idempotência) | Flag: Fulfillment object criado |
| `cancellation_reason` | `string` | PixTimeoutHandler, PaymentTimeoutHandler, ConfirmationTimeoutHandler, OrderCancelView, GestorOrderRejectView | hooks._on_cancelled | Motivo (auditoria): `"pix_timeout"`, `"card_timeout"`, `"confirmation_timeout"`, `"customer_requested"`, texto livre. **Pode conter código de máquina — nunca exibir ao cliente.** |
| `cancellation_note` | `string` | `operator_orders.cancel_order` (via OrderCancelView `customer_note`) | `lifecycle._on_cancelled` | Justificativa **voltada ao cliente**, escrita/escolhida pelo operador (preset). Só existe em cancelamento por operador com motivo informado; entra na notificação `order_cancelled` (`{reason_note}`). Ausente ⇒ mensagem genérica. Distinta de `cancellation_reason` (que carrega códigos de máquina) |
| `rejected_by` | `string` | GestorOrderRejectView | — | Username do operador que rejeitou |
| `kitchen_note` | `string` | OrderNotesView (`operator_orders.save_kitchen_note`) | OperatorOrderProjection (`kitchen_note`), KDS ticket (`kitchen_note`) | Nota da cozinha escrita pelo operador no gestor (tags pré-configuradas `Shop.kitchen_note_tags` anexadas + texto livre). **Exibida no ticket do KDS** para a produção. Distinta da `order_notes` (nota do cliente, do checkout) e dos `operator_comment` do histórico |
| `assignment` | `dict` | OrderAssignView (operator_orders.assign_order) | OrderCardProjection (`assigned_operator`) | Operador que assumiu o pedido ("estou atendendo"): `{operator_id, operator_name, at}`. Removido por OrderUnassignView |
| `returns` | `list[dict]` | ReturnService | ReturnHandler | Histórico de devoluções (ver detalhamento) |
| `nfce_access_key` | `string` | NFCeEmitHandler | NFCeEmitHandler (idempotência), ReturnService | Chave de acesso NFCe |
| `nfce_number` | `int` | NFCeEmitHandler | — | Número do documento |
| `nfce_danfe_url` | `string` | NFCeEmitHandler | — | URL do DANFE PDF |
| `nfce_qrcode_url` | `string` | NFCeEmitHandler | — | URL do QR code |
| `nfce_cancelled` | `bool` | NFCeCancelHandler | NFCeCancelHandler (idempotência) | NFCe cancelada |
| `nfce_cancellation_protocol` | `string` | NFCeCancelHandler | — | Protocolo de cancelamento |
| `nfce_series` | `string` | `shop/handlers/fiscal.py` (FocusNFe) | — | Série do documento NFC-e emitido via FocusNFe |
| `nfce_protocol` | `string` | `shop/handlers/fiscal.py` (FocusNFe) | — | Número do protocolo de autorização |
| `nfce_xml_url` | `string` | `shop/handlers/fiscal.py` (FocusNFe) | — | URL do XML autorizado |
| `nfce_status` | `string` | `shop/handlers/fiscal.py` (FocusNFe) | — | Status da emissão (ex.: `autorizado`, `erro`) |
| `availability_decision` | `dict` | `lifecycle.approve_with_adjustments()`, `lifecycle.approve_order()`, `lifecycle.reject_order()` | `lifecycle.has_availability_approval()`, `lifecycle.ensure_confirmable()`, `services/stock.py` | Decisão do operador sobre disponibilidade: `{approved: bool, decisions: [{sku, original_qty, approved_qty, action}], decided_at, decided_by}`. Guard para confirmação |
| `cancelled_by` | `string` | `services/cancellation.py` | `hooks._on_cancelled` | Identificador de quem cancelou: `"customer"` ou `"operator:<username>"` |
| `session_key` | `string` | hooks._on_cancelled | hooks._on_cancelled | Chave de sessão original (referência para release holds) |
| `hold_ids` | `list[dict]` | `StockService.hold(order)` | `StockService.fulfill(order)`, `StockService.release(order)` | Holds do Stockman adotados no commit. Cada entry: `{sku, hold_id, qty}` |
| `lifecycle` | `dict` | `lifecycle.dispatch()` (via `_mark_phase_complete`, fases em `DURABLE_PHASES`) | `sweep_stuck_orders`, `reconcile_payments`, `lifecycle.phase_complete()` | Marcador durável de conclusão de fase: `{on_commit: "done", on_confirmed: "done", on_paid: "done", on_cancelled: "done"}` (só as chaves das fases já completas). O dispatch roda pós-commit (não durável); um crash entre o COMMIT da transição e o fim do handler perde a fase (hold, fulfill, ticket KDS, notificação, estorno). O `dispatch()` grava o marcador APÓS o handler retornar; o sweeper re-despacha, idempotente, as fases sem marcador (NEW→`on_commit`, CONFIRMED→`on_confirmed`, pagos→`on_paid`, CANCELLED→`on_cancelled`) |
| `loyalty` | `dict` | `LoyaltyRedeemModifier` (via `CommitService`) | `services/loyalty.py` (redeem), `LoyaltyRedeemHandler` | Resgate de pontos: `{redeem_points_q: int, applied_discount_q: int}`. `redeem_points_q` = pedido pelo cliente; `applied_discount_q` = desconto efetivamente aplicado (clampado ao subtotal) — é o valor DEBITADO. Propagada Session→Order na lista do `_do_commit()` |
| `awaiting_wo_refs` | `list[string]` | `shop.handlers.production_order_sync` | Backstage pedidos/producao projections | Refs de WorkOrders que cobrem itens produzidos do pedido. Contextual, derivável e limpável em void. |
| `pos_committed_at` | `string` | `shop/services/pos.py` (`_mark_tab_committed`) | — | Timestamp ISO de quando a comanda foi finalizada no POS |
| `client_request_id` | `string` | `shop/services/pos.py` (`_mark_tab_committed`) | `_existing_sale_by_client_request_id` (dedupe) | Chave de idempotência do checkout direto POS. Espelhada em `pos.client_request_id` |
| `pos` | `dict` | `shop/services/pos.py` (`_mark_tab_committed`) | POS projections, `CashShift.close()` | Contexto POS selado no Order: `{cash_shift_id, client_request_id, ...}`. `cash_shift_id` liga a venda ao turno de caixa para reconciliação |
| `external_order_code` | `string` | `shop/services/ifood_ingest.py` | — | Código do pedido no marketplace iFood. Duplicado em `ifood.order_code` |
| `merchant_id` | `string` | `shop/services/ifood_ingest.py` | — | ID do merchant na iFood. Duplicado em `ifood.merchant_id` |
| `ifood` | `dict` | `shop/services/ifood_ingest.py` | — | Contexto da iFood (só em pedidos ingeridos via `ifood_ingest`): `{order_code, merchant_id, created_at}` |
| `courier` | `dict` | `CourierDispatchHandler`, `services/courier.apply_status` | `_courier_block` (projection do gestor), webhook Machine (lookup por `data__courier__id_mch`), notificação (`courier_tracking_url`) | Corrida de entrega na logística externa (Machine). Ver detalhamento abaixo |

### courier — detalhamento

Corrida de entrega via logística externa (Machine/Gaudium). Escrito pelo
`CourierDispatchHandler` (abertura) e por `services/courier.apply_status`
(funil único de status: webhook + polling convergem nele). Status usa a letra
crua da Machine (`D` distribuindo, `G` aguardando aceite, `P` pendente, `A`
aceita, `S` em espera, `E` em andamento, `F` finalizada, `N` não atendida,
`C` cancelada, `U` agrupada); labels pt-BR só na projection.

```jsonc
"courier": {
  "provider": "machine",
  "id_mch": "184532",              // corrida ATIVA (string); some quando N/C arquiva
  "status": "E",                   // letra Machine crua
  "requested_at": "2026-07-07T18:02:11-03:00",
  "dispatched_at": null,           // setado no primeiro E (coleta)
  "finished_at": null,             // setado no F
  "driver": {"name": "", "phone": "", "vehicle_plate": "", "vehicle_model": ""},  // a partir de A
  "tracking_url": "",              // link de rastreio da parada (a partir de A)
  "confirmation_code": "",
  "estimate": {"value_q": 1250, "minutes": 18.0, "km": 4.2},  // custo interno (centavos)
  "final_value_q": null,           // finished.final_value convertido p/ centavos
  "last_event_at": "iso",
  "last_source": "webhook",        // "webhook" | "poll" | "dispatch" | "operator:<nome>"
  "attempts": [                    // corridas anteriores (N/C ou canceladas p/ re-despacho)
    {"id_mch": "184501", "status": "N", "requested_at": "iso", "ended_at": "iso"}
  ],
  "error": {"message": "...", "at": "iso"}  // falha terminal do despacho; limpo no re-despacho
}
```

### Chaves seed-only para QA adversarial

Estas chaves só devem ser escritas por seed/dados demo. Elas existem para
exercitar jornadas de seguranca, confiabilidade e atendimento, sem virar
contrato de negocio em producao.

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `edge_case` | `string` | Nelson seed | QA manual/automatizado, relatorios de auditoria | Marcador deterministico de cenario adversarial. Ex: `"low_attention_payment_pending"`, `"late_payment_after_cancel"`, `"marketplace_stale_confirmation"` |


### Chaves lidas por views (convenience — fallback para vazio)

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `customer_name` | `string` | — | **Não usar.** Views agora lêem `customer.name` canônico com fallback para `order.handle_ref`. Reservado para canais legados que achatam o nome |
| `delivery_method` | `string` | pedidos._enrich_order, kds._enrich_order, PedidoAdvanceView | **Não escrito pela checkout padrão.** Falls back para `""`. Previsto para canais que usam `delivery_method` em vez de `fulfillment_type` |
| `customer_phone` | `string` | NotificationHandler._resolve_recipient | **Não escrito diretamente.** Fallback quando `customer.phone` não encontrado |

### payment — detalhamento

**Contrato**: `{intent_ref, method}` são as chaves canônicas. Status de pagamento vive
em Payman (`PaymentService`) — nunca duplicado em `order.data`. Demais chaves são
dados de display (UI) ou audit (rastreabilidade).

```json
{
  "method": "pix",
  "intent_ref": "INT-abc123",
  "idempotency_key": "order-payment:ORD-001:pix:2500:...",
  "amount_q": 2500,
  "qr_code": "data:image/png;base64,...",
  "copy_paste": "00020126...",
  "expires_at": "2026-03-30T10:15:00Z",
  "e2e_id": "E123456789",
  "paid_amount_q": 2500,
  "captured_at": "2026-03-30T10:12:00Z",
  "client_secret": "pi_xxx_secret_yyy",
  "transaction_id": "TXN-001",
  "error": "Gateway timeout (truncado a 200 chars)"
}
```

Classificações: **canonical** = fonte de verdade para decisões; **display** = dados de UI, nunca usado para lógica; **audit** = rastreabilidade; **idempotency** = flag de deduplicação.

**Status de pagamento NÃO está aqui** — consulte sempre `payment_svc.get_payment_status(order)` (canonical source: Payman).

| Sub-chave | Tipo | Classe | Escrito por | Lido por | Descrição |
|-----------|------|--------|-------------|----------|-----------|
| `method` | `string` | **canonical** | CheckoutView → CommitService | lifecycle, views, handlers | `"pix"`, `"card"`, `"counter"`, `"external"` |
| `intent_ref` | `string` | **canonical** | `payment.initiate()` | `payment_svc.get_payment_status`, PaymentStatusView | ID do intent no Payman/gateway |
| `idempotency_key` | `string` | idempotency | `payment.initiate()` | adapters Payman/gateway | Chave da tentativa de pagamento para retry seguro; não é status e não libera fluxo operacional |
| `amount_q` | `int` | display | `payment.initiate()` | PaymentView, templates | Valor em centavos (referência para UI) |
| `qr_code` | `string` | display | `payment.initiate()` | PaymentView template | QR code image (data URI) — PIX only |
| `copy_paste` | `string` | display | `payment.initiate()` | PaymentView template | Brcode PIX copia-e-cola — PIX only |
| `expires_at` | `string` | display | `payment.initiate()` | PaymentStatusView (expiração) | ISO datetime de expiração do QR — PIX only |
| `client_secret` | `string` | display | `payment.initiate()` | PaymentView template | Stripe PaymentIntent secret — card only |
| `e2e_id` | `string` | audit + idempotency | `EfiPixWebhookView` | EfiPixWebhookView (deduplicação) | End-to-end ID da transação PIX |
| `paid_amount_q` | `int` | audit | `EfiPixWebhookView` | — | Valor efetivamente pago pelo cliente |
| `captured_at` | `string` | audit + idempotency | `confirm_pix` / `payment.capture()` / POS | `confirm_pix` (guard de re-dispatch do `on_paid`) | ISO datetime da captura SUFICIENTE (só gravado quando o valor capturado cobre `total_q`; pagamento parcial não grava) |
| `transaction_id` | `string` | audit | `payment.capture()` | — | Transaction ID do adapter pós-capture |
| `marked_paid_by` | `string` | legacy audit | endpoint removido | leitura histórica apenas | Campo legado de versões antigas; não é status de pagamento, não deve liberar fluxo operacional e não existe mais como ação de operador |
| `error` | `string` | audit | `payment.initiate()` | — | Mensagem de erro se create_intent falhou (max 200 chars) |

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
  "delivery_time_slot": "slot-09",
  "order_notes": "Sem cebola",
  "origin_channel": "web",
  "is_preorder": true,
  "payment": {
    "method": "pix",
    "intent_ref": "INT-abc123",
    "idempotency_key": "order-payment:WEB-010426-ABCD:pix:2500:...",
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
| `items` | `list[dict]` | hooks._build_directive_payload (stock.hold), customers.OrderingOrderHistoryBackend | Itens da sessão: `[{line_id, sku, name, qty, unit_price_q, line_total_q, meta}]`. Flag D-1 (sobras) mora em `meta.is_d1` — setada na inclusão quando o estoque é só D-1 (alinhado à vitrine) e consumida pelo AvailabilityDiscountModifier. Um `is_d1` no topo da linha NÃO sobrevive ao `Session._normalize_items` (whitelist), por isso vive em `meta` |
| `data` | `dict` | handlers/customer.py (fallback), hooks (stock.commit holds) | Cópia integral de `session.data` no momento do commit |
| `pricing` | `dict` | customers.OrderingOrderHistoryBackend | Pricing da sessão: `{total_q, subtotal_q, discount_q, ...}` |
| `rev` | `int` | hooks._build_directive_payload (stock.hold) | Revisão da sessão no commit |
| `seed` | `string` | seed | QA/auditoria | Marcador de origem para dados demo. Não usado em lógica de negócio |
| `seed_namespace` | `string` | seed | QA/auditoria | Grupo deterministico do seed, ex: `"security_reliability_edges"` |
| `seed_key` | `string` | seed | seed idempotente, QA/auditoria | Chave unica do cenario seed para evitar duplicacao em reruns |

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

#### `preorder.activate`

Despertador da encomenda (pedido com `delivery_date` futura): o lifecycle adia
KDS e baixa e agenda esta directive com `available_at` na madrugada da data.
Dedupe: `preorder.activate:{order_ref}`.

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | lifecycle._schedule_preorder_activation | PreorderActivateHandler |
| `channel_ref` | `string` | lifecycle._schedule_preorder_activation | PreorderActivateHandler |
| `delivery_date` | `string` (ISO) | lifecycle._schedule_preorder_activation | auditoria |

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

#### `production.late_check`

Heartbeat auto-reagendável de alertas de produção (WP-PE0). Payload **vazio** —
é um singleton por loja, não referencia pedido. Armado por
`ensure_late_check_scheduled()` em qualquer `production_changed` (e pelo seed);
o handler roda `check_late_started_orders()` + `check_forgotten_planned_orders()`
e reenfileira a si mesmo em `production.alerts.late_check_cadence_minutes`
(0 = desligado), zerando `attempts`. Duplicatas colapsam mantendo a mais antiga.

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

#### `courier.dispatch`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | `courier.request_dispatch` | CourierDispatchHandler |
| `channel_ref` | `string` | `courier.request_dispatch` | — (auditoria) |
| `actor` | `string` | `courier.request_dispatch` (`lifecycle.on_ready` ou `operator:<nome>`) | CourierDispatchHandler (auditoria no evento) |

Write-back em `Order.data["courier"]` (ver detalhamento). `dedupe_key` =
`courier.dispatch:{order_ref}:{tentativa}`.

#### `courier.sync`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | CourierDispatchHandler / CourierSyncHandler (reagenda) | CourierSyncHandler |

Heartbeat de polling do status da corrida (fallback do webhook Machine).
Auto-reagendável a cada `Shop.defaults.delivery.courier_poll_seconds` (default
60; `0` desliga). Morre em status terminal (F/N/C).

#### `loyalty.earn`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | LoyaltyEarnHandler |

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

Configuração do canal. Schema formal via `ChannelConfig` dataclass em `shopman/shop/config.py`.

### Cascata de configuração

```
ChannelConfig.defaults() ← Shop.defaults ← Channel.config
```

O método `ChannelConfig.for_channel(channel_or_ref)` faz o merge profundo (deep_merge).
Chave ausente no override = herda. Chave presente (mesmo None) = sobreescreve.

### 1. Confirmation — como o pedido é aceito?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `mode` | `string` | `"immediate"` | `"immediate"` (auto-confirma), `"auto_confirm"` (auto-confirma após timeout), `"auto_cancel"` (cancela após timeout), `"manual"` (aguarda) |
| `timeout_minutes` | `int` | `5` | Timeout para modes auto_confirm/auto_cancel |

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

### 7. Lifecycle — como o pedido transita entre status?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `transitions` | `dict \| None` | `None` | Transições permitidas: `{status: [status, ...]}` |
| `terminal_statuses` | `list[str] \| None` | `None` | Status terminais (não transitam mais) |
| `auto_transitions` | `dict \| None` | `None` | Transições automáticas: `{"on_payment_confirm": "processing"}` |
| `auto_sync_fulfillment` | `bool` | `False` | Sync automático fulfillment → order status |

Lido por: `hooks.on_payment_confirmed`, `FulfillmentUpdateHandler`.

### Chaves fora do ChannelConfig schema

Estas chaves são lidas diretamente de `channel.config` como dict bruto, sem passar pelo `ChannelConfig`:

| Chave | Lido por | Descrição |
|-------|----------|-----------|
| `cutoff_hour` | CheckoutView._get_cutoff_info | Hora de corte para pedidos do dia (default 18) |
| `rules.d1_discount_percent` | D1DiscountModifier, product_cards | Percentual de desconto D-1 |

### Presets

| Preset | Confirmation | Payment | Stock TTL | Notifications | Validators |
|--------|-------------|---------|-----------|---------------|------------|
| `pos()` | immediate | counter | 5 min | console | business_hours |
| `remote()` | auto_confirm/5min | [pix, card]/15min | 30 min | manychat | business_hours, min_order |
| `whatsapp()` | auto_confirm/5min | [pix, card]/15min | 30 min | whatsapp | business_hours, min_order |
| `marketplace()` | auto_cancel/5min | external | None | none | (vazio) |

---

## Shop.defaults

Configurações padrão da loja — camada intermediária na cascata de configuração de canais.

```
ChannelConfig.defaults() ← Shop.defaults ← Channel.config
```

O schema é idêntico ao `ChannelConfig` (ver seção `Channel.config` acima). Chaves ausentes
em `Shop.defaults` herdam os defaults de código do `ChannelConfig`. Canais que não sobrescrevem
uma chave específica herdam a da loja.

**Campo**: `Shop.defaults` (JSONField, `shopman/shop/models/shop.py`).
**Mergeado por**: `ChannelConfig.for_channel()` via `deep_merge`.

### Exemplo

```json
{
  "confirmation": {"mode": "auto_confirm", "timeout_minutes": 10},
  "stock": {"hold_ttl_minutes": 30, "safety_margin": 2},
  "notifications": {"backend": "manychat", "fallback_chain": ["sms"]},
  "rules": {"minimum_order_q": 0, "delivery_minimum_q": 2500, "free_delivery_above_q": 0}
}
```

### Políticas de pedido/entrega — `Shop.defaults["rules"]`

Valores em centavos (`_q`). **Semântica única: `0`/ausente = regra desligada** (sem
fallback mágico). Fonte única consumida pelo aviso ao vivo (projections) e pelo
gate de commit. Editáveis tipados em Reais no ShopAdmin (`shop/admin/shop.py`).

| Chave | Aplica a | Lido por | Descrição |
|-------|----------|----------|-----------|
| `rules.minimum_order_q` | todo pedido | `build_minimum_order_progress`, `can_checkout` | Mínimo geral para finalizar. Barra de progresso + bloqueio do checkout |
| `rules.delivery_minimum_q` | só entrega | `build_delivery_minimum_progress`, `DeliveryZoneRule` (commit), POS | Mínimo só para entrega (retirada nunca tem). Aviso no passo de entrega + bloqueio do commit |
| `rules.free_delivery_above_q` | só entrega | `build_free_delivery_progress`, `DeliveryFeeModifier` | Taxa de entrega zera no/above deste valor. Reusa a barra como upsell ("faltam X para frete grátis") |

> Convivem no mesmo sub-dict `rules` que o tri-state `validators`/`modifiers`/
> `checks` do `ChannelConfig` — o `_safe_init` filtra estas chaves de política, que
> são lidas direto de `shop.defaults["rules"]` por `shop_rule_q()`.

A taxa de entrega por região segue nas **Zonas de Entrega** (`DeliveryZone`, inline
no admin). O frete grátis global é avaliado por cima da taxa da zona.

### Fidelidade — `Shop.defaults["loyalty"]`

Política do programa de fidelidade, fora do schema do `ChannelConfig` (`_safe_init`
filtra). Source-of-truth tipado em `shopman/shop/loyalty_config.py` (`LoyaltyConfig`,
dataclass-driven), editável no ShopAdmin (fieldset "Fidelidade"). O Core (guestman)
não depende do shop: o orquestrador (`shop/apps.py`) registra resolvers em
`guestman.contrib.loyalty.conf` que injetam estes valores.

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `loyalty.points_per_real` | `int` | `LoyaltyEarnHandler` (`shop/handlers/loyalty.py`) | Pontos por R$ 1,00 gasto. `0` desliga o acúmulo. Default `1` |
| `loyalty.stamps_target` | `int` | `LoyaltyService.enroll` (via resolver) | Meta de carimbos de novas contas. Default `10` |
| `loyalty.tiers` | `list[{name, threshold}]` | `LoyaltyService._update_tier` (via resolver) | Limiares de nível por pontos acumulados. `name` ∈ {bronze, silver, gold, platinum}; bronze é o piso (`0`) |

```json
{
  "loyalty": {
    "points_per_real": 1,
    "stamps_target": 10,
    "tiers": [
      {"name": "bronze", "threshold": 0},
      {"name": "silver", "threshold": 500},
      {"name": "gold", "threshold": 2000},
      {"name": "platinum", "threshold": 5000}
    ]
  }
}
```

> Chaves ausentes herdam os defaults do dataclass (idênticos ao comportamento
> hardcoded anterior — zero regressão). Sem `Shop` ou sem bloco `loyalty`, os
> resolvers caem nos defaults do guestman.

### Ponto de venda — `Shop.defaults["pos"]`

Políticas do balcão, fora do schema do `ChannelConfig`.

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `pos.discount_approval_threshold_q` | `int` (centavos) | `_discount_approval_threshold_q` (`backstage/projections/pos.py`) | Descontos manuais acima deste valor exigem PIN do gerente. `0` = todo desconto exige aprovação. **Ausente = herda `SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q`** (deploy) — zero regressão. Editado em Reais no ShopAdmin. |

### Alertas de estoque — `Shop.defaults["stock_alerts"]`

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `stock_alerts.cooldown_minutes` | `int` (minutos) | `get_alert_cooldown_minutes` (`stockman/contrib/alerts/conf.py`, via resolver) | Intervalo mínimo entre re-notificações do MESMO alerta de estoque baixo (anti-flood; o cooldown é por `StockAlert` = par sku+posição). **Ausente = herda `STOCKMAN_ALERT_COOLDOWN_MINUTES`** (deploy, default 60) — zero regressão. O Core não depende do shop: o orquestrador injeta um resolver em `stockman.contrib.alerts.conf`. O limiar de cada alerta (`min_quantity`) continua por-SKU no admin de Alertas. |

### Produção — `Shop.defaults["production"]`

Contrato único de configuração de produção, fora do schema do `ChannelConfig`
(produção é da loja, não do canal). Source-of-truth tipado em
`shopman/shop/production_config.py` (`ProductionConfig`, dataclass-driven, mesma
mecânica do `LoyaltyConfig`): defaults sensatos, `deep_merge` com
`Shop.defaults["production"]`, validação que acusa cedo no `load()`.

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `production.suggestion.seasons` | `dict[str, list[int]]` | `production.suggest_for()` (`shop/services/production.py`) | Estações → meses (1-12). O mês da data-alvo resolve a estação; a lista filtra o histórico de demanda do `craft.suggest()`. Vazio = sem filtro sazonal. |
| `production.suggestion.high_demand_multiplier` | `string` (Decimal) | `production.suggest_for()` | Multiplicador aplicado em sexta/sábado (ex: `"1.2"`). Ausente = desligado. |
| `production.suggestion.safety_stock_percent` | `string` (Decimal) | `production.suggest_for()` | Margem sobre (demanda média + committed), ex: `"0.20"`. **Ausente = herda `CRAFTSMAN["SAFETY_STOCK_PERCENT"]`** (deploy, default 0.20). |
| `production.alerts.low_yield_threshold` | `string` (Decimal 0-1) | `maybe_create_low_yield_alert` (`shop/handlers/production_alerts.py`) | Yield (finished/started) abaixo disto → `OperatorAlert production_low_yield`. Default `"0.80"`. |
| `production.alerts.default_max_started_minutes` | `int` | `production_alerts`, projections de produção | Janela padrão de WO em andamento antes de "atrasada". `Recipe.meta["max_started_minutes"]` sobrescreve por receita. Default `240`. |
| `production.alerts.late_check_cadence_minutes` | `int` | `ProductionLateCheckHandler` | Cadência do heartbeat `production.late_check`. `0` = desligado. Default `15`. |
| `production.notifications.enabled` | `bool` | `production_alerts._notify_operator` | Liga o par alerta+notificação: além do `OperatorAlert` (sempre criado), o alerta enfileira `notification.send` de sistema (operador, email→console, retry). Default `false` — opt-in contra ruído. |
| `production.notifications.severities` | `list[string]` | `production_alerts._notify_operator` | Severidades que notificam quando `enabled`: subconjunto de `info\|warning\|error\|critical`. Default `["error"]` (só falta de insumo); ampliar para `["error", "warning"]` cobre atraso/yield/esquecimento. |
| `production.order_match` | `string` | `production_order_sync._match_strategy` | Estratégia de vínculo pedido confirmado → WorkOrder: `first_planned` (default) \| `earliest_target` \| `manual`. |

> Editáveis no ShopAdmin (estações, multiplicador e margem no fieldset de
> produção). CLI (`suggest_production`), projections do backstage e matriz do
> fournil resolvem a sugestão pelo MESMO caminho (`suggest_for`) — nunca chame
> `craft.suggest()`/`formula suggest()` direto de uma superfície.

---

## Shop.integrations

Seleção de adapters por tipo. Sobreescreve `settings.py` sem exigir redeploy.

**Campo**: `Shop.integrations` (JSONField, `shopman/shop/models/shop.py`).
**Lido por**: `shopman.shop.adapters.get_adapter()`.

### Schema

```json
{
  "payment": {
    "pix":  "<módulo Python>",
    "card": "<módulo Python>"
  },
  "notification": {
    "default": "<módulo Python>"
  },
  "fiscal": "<módulo Python>"
}
```

Adapters aceitos por tipo:

| Tipo | Chaves | Adapters disponíveis |
|------|--------|----------------------|
| `payment` | `pix`, `card`, `external` | `payment_efi`, `payment_stripe` |
| `notification` | `default`, por backend | `notification_manychat`, `notification_console` |
| `fiscal` | (string) | `fiscal_nfce` |

### Prioridade de resolução

`Shop.integrations` → `settings.SHOPMAN_*_ADAPTERS` → defaults de código.

---

## Customer.metadata

Extensao do cadastro de cliente para contexto operacional e demos. Dados que
alteram autorizacao, cobranca ou identidade devem viver em campos/modelos
proprios, nao aqui.

**Campo**: `Customer.metadata` (JSONField, `shopman/guestman/models/customer.py`).

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `preferences` | `string \| dict` | cadastro/importacao | atendimento, segmentacao | Preferencias gerais do cliente, ex: restricoes alimentares |
| `birthday` | `string` | cadastro/importacao legado | atendimento, segmentacao | Data de aniversario em registros legados. Preferir campo `Customer.birthday` |
| `seed_persona` | `string` | seed | QA/auditoria | Persona operacional deterministica. Ex: `"low_attention"` |
| `qa_notes` | `list[string]` | seed | QA/auditoria | Observacoes de teste para simular baixa atencao, recuperacao e suporte |

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
10. **Channel.config usa ChannelConfig dataclass**. Chaves fora do schema devem ser documentadas na seção "Chaves fora do ChannelConfig schema".

---

## WorkOrder.meta

Contexto operacional de produção mantido fora do core Craftsman.

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `committed_order_refs` | `list[string]` | `shop.handlers.production_order_sync` | Backstage produção/pedidos projections | Pedidos que comprometem quantidade do SKU produzido por esta WorkOrder. Espelho operacional de `Order.data.awaiting_wo_refs`; a métrica de produção é a soma de itens, não a contagem de pedidos. |
| `steps_progress` | `int` | Backstage produção (futuro botão manual) | `build_production_kds` | Override manual do passo atual no KDS de produção, 1-based. |
| `batch_ref` | `string` | `backstage.services.production` | auditoria/lotes | Lote criado para receita com rastreabilidade. |
| `batch_quantity` | `string` | `backstage.services.production` | auditoria/lotes | Quantidade acabada associada ao lote. |
| `expiry_date` | `string` | `backstage.services.production` | auditoria/lotes | ISO date de validade do lote, quando aplicável. |
| `formula_basis` | `dict` | `set_planned_quantity` (`shop/services/production.py`) | matriz/auditoria de sugestão | Basis da sugestão aceita (demanda média, committed, margem, `accepted_quantity`). Só quando `source_ref="formula:suggestion"`. |
| `consolidated_work_order_refs` | `list[string]` | `set_planned_quantity` | auditoria | Refs de WOs planned duplicadas consolidadas nesta. |
| `_recipe_snapshot` | `dict` | Core (`CraftPlanning.plan`) | Core (`finish`) | BOM congelada no plan — **gerida pelo Core, nunca editar**. |

## Recipe.meta

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `steps` | `list[dict]` | seed/admin de receitas | KDS de produção | Passos do KDS: `[{name: string, target_seconds: int}]`. Fallback: campo legado `Recipe.steps`. |
| `max_started_minutes` | `int` | seed/admin de receitas | alertas/KDS produção | Tempo alvo total para WO em produção antes de atraso. Ausente = `production.alerts.default_max_started_minutes`. |
| `capacity_per_day` | `int` | seed/admin de receitas | dashboard/relatórios | Capacidade diária nominal da receita. |
| `production_lifecycle` | `string` | admin de receitas (contrib Unfold, campo provider-driven) | `dispatch_production` (`shop/production_lifecycle.py`) | Variante de lifecycle do orquestrador: `standard` (default, chave omitida) \| `forecast` \| `subcontract` (ADR-007). O campo só existe porque `CRAFTSMAN["PRODUCTION_LIFECYCLE_PROVIDER"]` aponta para `production_lifecycle_choices()` do orquestrador — pacote standalone não o renderiza. |
| `requires_batch_tracking` | `bool` | admin de receitas (contrib Unfold) | `backstage.services.production` | Cria lote ao concluir a produção. |
| `shelf_life_days` | `int` | admin de receitas (contrib Unfold) | `backstage.services.production` | Validade do lote produzido, em dias. |

## DayClosing.data

Registros antigos podem ser uma lista simples de snapshots. Registros novos usam envelope:

```json
{
  "items": [
    {"sku": "SKU", "qty_reported": 1, "qty_applied": 1, "qty_discrepancy": 0, "qty_remaining": 0, "qty_d1": 0, "qty_loss": 0}
  ],
  "production_summary": {
    "recipe-ref": {"recipe_ref": "recipe-ref", "output_sku": "SKU", "planned": 10, "finished": 9, "loss": 1}
  },
  "reconciliation_errors": [
    {"sku": "SKU", "sold": 12, "available": 10, "deficit": 2}
  ]
}
```

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `items` | `list[dict]` | `services/closing.py::perform_day_closing` | template fechamento | Snapshot por SKU com qty reportada, aplicada, D-1, perda. |
| `production_summary` | `dict[str, dict]` | `services/closing.py::_production_summary` | template fechamento, projection | Agregado de WOs do dia por receita: `{recipe_ref: {recipe_ref, output_sku, planned, finished, loss}}`. |
| `pending_production` | `list[dict]` | `services/closing.py::_pending_production_snapshot` | auditoria | WOs ainda abertas (planned/started, `target_date <= data do fechamento`) no momento do fechamento: `{ref, output_sku, recipe_ref, status, quantity, target_date}`. O fechamento acusa, não bloqueia. |
| `cash_shift_summary` | `dict` | `services/closing.py::_cash_shift_summary` | template fechamento, projection | Turnos de caixa do dia (fechados/abertos/totais). |
| `reconciliation_errors` | `list[dict]` | `services/closing.py::_reconciliation_errors` | projection (`ReconciliationError.from_dict`) | Discrepâncias detectadas: SKUs vendidos além do que estoque + produção poderiam suprir. Schema: `{sku, sold, available, deficit}` (a projection converte para `ReconciliationError(sku, sold_qty, available_qty, deficit_qty)` na leitura). |
