# Data Schemas — JSONField Reference

> Inventário completo de chaves usadas nos JSONFields do Core.
> **Regra**: toda nova chave deve ser documentada aqui antes de ser usada.
> Ver também: [CLAUDE.md](../../CLAUDE.md) § "Core é Sagrado".

---

## Session.data

Unidade mutável pré-commit (carrinho/comanda). Populado pelo App (views, CartService, handlers).
O Core não impõe schema — a governança é por convenção documentada aqui.

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `customer` | `dict` | CheckoutView | CommitService, handlers | Dados do cliente: `{name, phone, notes, cpf, address}` |
| `fulfillment_type` | `string` | CheckoutView | CommitService, FulfillmentHandler | `"pickup"` ou `"delivery"` |
| `delivery_address` | `string` | CheckoutView | CommitService | Endereço formatado (texto livre) |
| `delivery_address_structured` | `dict` | CheckoutView | CommitService, FulfillmentHandler | Endereço estruturado: `{route, street_number, complement, neighborhood, city, state_code, postal_code, place_id, formatted_address, delivery_instructions, is_verified, latitude, longitude}` |
| `delivery_date` | `string` | CheckoutView | CommitService | ISO date. Se futuro, indica encomenda |
| `delivery_time_slot` | `string` | CheckoutView | CommitService | Faixa horária: `"manha"`, `"tarde"`, etc. |
| `order_notes` | `string` | CheckoutView | CommitService | Observações do pedido |
| `origin_channel` | `string` | CartService, BridgeTokenView | CommitService, hooks.py | Canal de origem: `"web"`, `"whatsapp"`, `"instagram"`, `"pos"` |
| `coupon_code` | `string` | CartService.apply_coupon | CouponModifier, CartService.get_cart | Código do cupom aplicado (uppercase) |
| `checks` | `dict` | SessionWriteService.apply_check_result | CommitService (validação) | Resultados de checks: `{check_code: {rev, at, result}}` |
| `issues` | `list[dict]` | SessionWriteService | CommitService (validação) | Issues de validação: `[{source, code, message, blocking, id, data}]` |

### Exemplo completo

```json
{
  "customer": {"name": "João Silva", "phone": "5543999990001"},
  "fulfillment_type": "delivery",
  "delivery_address": "Rua das Flores 123 - Centro - Londrina",
  "delivery_date": "2026-04-01",
  "delivery_time_slot": "manha",
  "order_notes": "Sem cebola",
  "origin_channel": "whatsapp",
  "coupon_code": "WELCOME10",
  "checks": {
    "stock": {"rev": 3, "at": "2026-03-30T10:00:00Z", "result": {"holds": [{"hold_id": "H-1", "expires_at": "..."}]}}
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
    "delivery_date", "delivery_time_slot", "order_notes",
    "origin_channel",
):
```

**Para adicionar uma nova chave ao fluxo Session→Order, adicione-a nessa lista.**

### Chaves computadas pelo CommitService

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `is_preorder` | `bool` | `True` se `delivery_date > hoje`. Calculado no commit |

### Chaves adicionadas por handlers pós-commit

| Chave | Tipo | Escrito por | Descrição |
|-------|------|-------------|-----------|
| `payment` | `dict` | PaymentHandler, CheckoutView, webhooks | `{method, intent_id, status, amount_q, qr_code, copy_paste, expires_at, client_secret, e2e_id, paid_amount_q}` |
| `customer_ref` | `string` | CustomerEnsureHandler | Ref do Customer criado/encontrado |
| `fulfillment_created` | `bool` | FulfillmentHandler | Flag: Fulfillment object criado |
| `cancellation_reason` | `string` | PixTimeoutHandler, OrderCancelView | Motivo: `"pix_timeout"`, `"customer_requested"` |
| `returns` | `list[dict]` | ReturnHandler | `[{timestamp, actor, reason, type, items: [{line_id, sku, qty, refund_q}], refund_total_q, refund_processed}]` |
| `nfce_access_key` | `string` | FiscalHandler | Chave de acesso NFCe |
| `nfce_number` | `int` | FiscalHandler | Número do documento |
| `nfce_danfe_url` | `string` | FiscalHandler | URL do DANFE PDF |
| `nfce_qrcode_url` | `string` | FiscalHandler | URL do QR code |
| `nfce_cancelled` | `bool` | FiscalHandler | NFCe cancelada |
| `nfce_cancellation_protocol` | `string` | FiscalHandler | Protocolo de cancelamento |
| `session_key` | `string` | hooks._on_cancelled | Chave de sessão original (referência) |

### payment — detalhamento

```json
{
  "method": "pix",
  "intent_id": "INT-abc123",
  "status": "captured",
  "amount_q": 2500,
  "qr_code": "data:image/png;base64,...",
  "copy_paste": "00020126...",
  "expires_at": "2026-03-30T10:15:00Z",
  "e2e_id": "E123456789",
  "paid_amount_q": 2500
}
```

Status possíveis: `"pending"`, `"captured"`, `"refunded"`, `"expired"`, `"failed"`.

---

## Directive.payload

Payload da tarefa assíncrona. Schema depende do `topic`.

| Chave | Tipo | Presente em | Descrição |
|-------|------|-------------|-----------|
| `order_ref` | `string` | Todos | Ref do pedido |
| `channel_ref` | `string` | Todos | Ref do canal |
| `session_key` | `string` | Quando disponível | Chave da sessão original |
| `origin_channel` | `string` | Quando disponível | Canal de origem (para routing de notificação) |
| `template` | `string` | notification.send | Template de notificação: `"order_confirmed"`, `"order_cancelled"`, etc. |
| `holds` | `list[dict]` | stock.commit | Holds a confirmar: `[{hold_id, expires_at}]` |
| `items` | `list[dict]` | stock.hold | Items a reservar: `[{sku, qty}]` |
| `rev` | `int` | stock.hold | Revisão da sessão |
| `amount_q` | `int` | pix.generate, payment.refund | Valor em centavos |
| `intent_id` | `string` | payment.refund | ID do intent a estornar |
| `reason` | `string` | payment.refund | Motivo do estorno |
| `pix_timeout_minutes` | `int` | pix.generate | TTL do QR PIX |
| `expires_at` | `string` | confirmation.timeout | ISO datetime de expiração |
| `context` | `dict` | notification.send | Variáveis do template de notificação |

---

## Channel.config

Configuração do canal. Schema formal via `ChannelConfig` dataclass (7 aspectos).
Ver [`docs/guides/channels.md`](../guides/channels.md) para detalhes.

Aspectos: `confirmation`, `payment`, `stock`, `pipeline`, `notifications`, `rules`, `flow`.

---

## Regras de Governança

1. **Toda nova chave** em qualquer JSONField deve ser adicionada a este documento antes do merge.
2. **CommitService** é o único caminho Session.data → Order.data. A lista de chaves é explícita.
3. **Handlers** escrevem apenas nas chaves documentadas na sua seção.
4. **Nenhum handler lê chave de outro handler** sem contrato documentado aqui.
5. **Nome da chave**: snake_case, descritivo, sem prefixo redundante (ex: `origin_channel`, não `session_origin_channel`).
6. **Tipo**: consistente. Valores monetários sempre `_q` (int centavos). Datas sempre ISO string.
