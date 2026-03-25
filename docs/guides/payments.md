# Guia de Pagamentos

## Visão Geral

O sistema de pagamentos é composto por duas camadas:

1. **Payments Core** (`shopman.payments`) — Service layer agnóstico que gerencia o lifecycle de `PaymentIntent` e `PaymentTransaction` no banco
2. **Payment Handlers** (`channels/handlers/payment.py`) — Handlers que conectam o lifecycle do pedido aos backends de gateway

O core não sabe nada sobre gateways (Efi, Stripe, etc.). Os backends implementam o `PaymentBackend` protocol e são configurados no orquestrador.

## Modelo de Dados

### PaymentIntent

Representa uma intenção de pagamento vinculada a um pedido.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | str | Identificador único (auto: `PAY-XXXXXXXXXXXX`) |
| `order_ref` | str | Referência do pedido (string, sem FK) |
| `method` | str | `pix`, `card`, `counter`, `external` |
| `status` | str | Estado atual do pagamento |
| `amount_q` | int | Valor em centavos |
| `currency` | str | ISO 4217 (default: `BRL`) |
| `gateway` | str | Nome do gateway (`efi`, `stripe`, etc.) |
| `gateway_id` | str | ID da transação no gateway externo |
| `gateway_data` | JSON | Dados extras do gateway (QR code, chave PIX, etc.) |
| `expires_at` | datetime | Expiração do intent |

### PaymentTransaction

Registro imutável de cada operação financeira sobre um intent.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `intent` | FK | PaymentIntent associado |
| `type` | str | `CAPTURE` ou `REFUND` |
| `amount_q` | int | Valor da transação em centavos |
| `gateway_id` | str | ID da transação no gateway |

## Lifecycle

```
PENDING → AUTHORIZED → CAPTURED → REFUNDED
   │          │
   ├→ FAILED  ├→ FAILED
   │          │
   └→ CANCELLED └→ CANCELLED
```

**Estados terminais:** `CAPTURED`, `REFUNDED`, `FAILED`, `CANCELLED`.

## PaymentService API

Todas as operações state-changing usam `@transaction.atomic` + `select_for_update()`. Cada transição emite o signal correspondente.

```python
from shopman.payments import PaymentService, PaymentError

# Criar intent
intent = PaymentService.create_intent("ORD-001", 1500, "pix")

# Autorizar (gateway confirmou fundos)
PaymentService.authorize(intent.ref, gateway_id="efi_txid_123")

# Capturar
tx = PaymentService.capture(intent.ref)

# Reembolsar (parcial ou total)
PaymentService.refund(intent.ref, amount_q=500, reason="item danificado")

# Cancelar (antes da captura)
PaymentService.cancel(intent.ref)

# Queries
intent = PaymentService.get(ref)
intents = PaymentService.get_by_order("ORD-001")
active = PaymentService.get_active_intent("ORD-001")
intent = PaymentService.get_by_gateway_id("efi_txid_123")

# Aggregates
total_captured = PaymentService.captured_total(ref)
total_refunded = PaymentService.refunded_total(ref)
```

## Fluxo PIX Completo

O fluxo PIX é o mais complexo. Envolve handlers, webhooks e timeouts:

```
1. Pedido confirmado (status → CONFIRMED)
   │
2. on_order_lifecycle() → pipeline.on_confirmed inclui PIX_GENERATE
   │
3. PixGenerateHandler executa:
   ├── PaymentBackend.create_intent() → GatewayIntent (QR code, copiar-colar)
   ├── PaymentService.create_intent() → persiste no DB
   ├── Salva dados PIX no Order.data (qr_code, copy_paste, expires_at)
   ├── Cria directive: notification.send (lembrete de pagamento)
   └── Cria directive: pix.timeout (timer de expiração)
   │
4. Cliente paga via PIX
   │
5. Gateway envia webhook → EfiPixWebhookView
   ├── PaymentService.authorize(ref)  → PENDING → AUTHORIZED
   ├── PaymentService.capture(ref)    → AUTHORIZED → CAPTURED
   └── on_payment_confirmed(order) hook:
       ├── Cria directive: stock.commit
       └── Cria directive: notification.send (pagamento confirmado)
   │
6. [Timeout] Se não pago a tempo:
   └── PixTimeoutHandler executa:
       ├── PaymentService.cancel(ref) → PENDING → CANCELLED
       ├── Order → CANCELLED
       └── Cria directive: stock.release + notification.send
```

### Configuração PIX

Via `ChannelConfig.payment`:

```python
ChannelConfig.Payment(
    method="pix",
    timeout_minutes=15,    # Tempo para pagar antes de cancelar
)
```

O timeout total de hold de estoque deve cobrir: confirmação + pagamento + margem. Veja `confirmation.calculate_hold_ttl()`.

## Backends Disponíveis

### MockPaymentBackend

Para testes e desenvolvimento. Simula fluxo completo com PIX mockado.

```python
SHOPMAN_PAYMENT_BACKEND = "channels.backends.payment_mock.MockPaymentBackend"
```

### EfiPixBackend

Integração com Efi (Gerencianet) para PIX real.

```python
SHOPMAN_PAYMENT_BACKEND = "channels.backends.payment_efi.EfiPixBackend"

# Settings necessários:
EFI_CLIENT_ID = "..."
EFI_CLIENT_SECRET = "..."
EFI_CERTIFICATE = "/path/to/cert.pem"
EFI_SANDBOX = True  # False em produção
```

### StripeBackend

Integração com Stripe (cartão, PIX via Stripe).

```python
SHOPMAN_PAYMENT_BACKEND = "channels.backends.payment_stripe.StripeBackend"

# Settings necessários:
STRIPE_SECRET_KEY = "sk_..."
STRIPE_WEBHOOK_SECRET = "whsec_..."
```

## Signals

Todos emitidos por `PaymentService` após cada transição:

| Signal | Quando | Payload |
|--------|--------|---------|
| `payment_authorized` | PENDING → AUTHORIZED | `intent`, `order_ref`, `amount_q`, `method` |
| `payment_captured` | AUTHORIZED → CAPTURED | `intent`, `order_ref`, `amount_q`, `transaction` |
| `payment_refunded` | Refund registrado | `intent`, `order_ref`, `amount_q`, `transaction` |
| `payment_cancelled` | PENDING/AUTHORIZED → CANCELLED | `intent`, `order_ref` |
| `payment_failed` | Qualquer → FAILED | `intent`, `order_ref`, `error_code`, `message` |

## Handlers do Orquestrador

| Handler | Topic | Descrição |
|---------|-------|-----------|
| `PaymentCaptureHandler` | `payment.capture` | Captura pagamento autorizado |
| `PaymentRefundHandler` | `payment.refund` | Processa reembolso via backend |
| `PixGenerateHandler` | `pix.generate` | Cria PIX charge com QR code e timeout |
| `PixTimeoutHandler` | `pix.timeout` | Cancela pedido se PIX não pago a tempo |

## Tratamento de Erros

```python
from shopman.payments.exceptions import PaymentError

try:
    PaymentService.capture(ref)
except PaymentError as e:
    print(e.code)     # "invalid_transition"
    print(e.message)  # "Não é possível capture: status atual é pending..."
    print(e.as_dict())
```

Códigos de erro: veja [errors.md](../reference/errors.md#paymenterror-payments).
