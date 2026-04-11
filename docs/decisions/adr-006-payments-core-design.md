# ADR-006: Payments Core Design

**Status:** Aceito
**Data:** 2026-03-25

## Contexto

O sistema de pagamentos precisa suportar múltiplos gateways (Efi PIX, Stripe, mock para testes) e métodos de pagamento (PIX, cartão, balcão, marketplace externo) sem acoplar o core a nenhum gateway específico.

## Decisão

### 1. Service Layer Agnóstico

`PaymentService` é uma classe com métodos estáticos (`create_intent`, `authorize`, `capture`, `refund`, `cancel`, `fail`) que gerencia o lifecycle de `PaymentIntent` no banco de dados. O service:

- Não conhece gateways — recebe dados já processados pelo handler/backend
- Usa `@transaction.atomic` + `select_for_update()` em toda operação state-changing
- Emite signals após cada transição para extensibilidade
- Valida transições via tabela `TRANSITIONS` no model

### 2. PaymentIntent Model (não inline em Order.data)

O pagamento vive em model dedicado (`PaymentIntent`) vinculado ao pedido por `order_ref` (string, sem FK).

**Trade-offs considerados:**

| Abordagem | Prós | Contras |
|-----------|------|---------|
| Inline em `Order.data` | Simples, sem model extra | Sem histórico de transações, difícil auditoria, sem queries eficientes |
| `PaymentIntent` model | Auditoria completa, queries indexadas, suporte a múltiplos intents/refunds parciais, imutabilidade de transações | Model extra, join necessário |

Escolhemos model dedicado porque:
- Reembolsos parciais requerem registro de cada transação
- Auditoria fiscal exige histórico imutável
- Queries por `gateway_id` (webhooks) precisam de índice próprio
- Um pedido pode ter múltiplos intents (falha + retry)

### 3. Protocols no Payments Core

`PaymentBackend` protocol vive em `shopman.payments.protocols` porque é uma interface de domínio genérica. O core define os DTOs (`GatewayIntent`, `CaptureResult`, `RefundResult`, `PaymentStatus`) que backends devem usar.

Os backends concretos vivem no orquestrador (`shopman/backends/payment_*.py`) porque dependem de settings e infraestrutura do App.

### 4. Webhook como Ponto de Entrada

Webhooks de gateway (`shopman/webhooks/`) recebem a notificação externa e chamam `PaymentService.authorize()` + `capture()`. Depois disparam o hook `on_payment_confirmed()` que cria directives de pós-pagamento (stock.commit, notification).

O webhook não cria directives diretamente — ele usa o mesmo mecanismo de hooks que o resto do lifecycle.

## Consequências

- **Testabilidade:** `MockPaymentBackend` implementa o protocol completo sem I/O externo
- **Extensibilidade:** Novos gateways = novo backend em `shopman/backends/` + setting
- **Auditoria:** `PaymentTransaction` é imutável, cada operação financeira tem registro
- **Desacoplamento:** Orderman não importa Payman; a ligação é via `order_ref` (string) e signals
