# Payment Domain Contracts

Referência dos contratos de domínio do Payman.

## Lifecycle

```
pending → authorized → captured → refunded
       ↘ failed      ↘ cancelled
       ↘ cancelled   ↘ failed
```

## Capture

- **Single-shot**: apenas uma captura por intent. Uma vez `CAPTURED`, nenhuma captura adicional é permitida.
- **Captura parcial**: se `amount_q < intent.amount_q`, o saldo não capturado é abandonado.
- **Captura total** (default): omitir `amount_q` captura o valor total autorizado (`intent.amount_q`).

## Refund

- **Status `REFUNDED`** significa "pelo menos um refund existe", **não** "totalmente reembolsado".
- **Fonte de verdade financeira**: `PaymentService.refunded_total(ref)` retorna a soma real de todos os refunds.
- **Múltiplos refunds parciais** são permitidos enquanto `captured_total - refunded_total > 0`.
- O intent transiciona para `REFUNDED` no primeiro refund e permanece lá para refunds subsequentes.

## Mutation Surface

- **`PaymentService`** é a superfície canônica de mutação. Todas as transições de status, criação de transações e emissão de signals passam por ele.
- **`intent.transition_status()`** é helper interno de concorrência usado pelo `save()` do model. Código externo **deve sempre** usar métodos do `PaymentService`.

## Queries

| Método | Retorno | Uso |
|--------|---------|-----|
| `PaymentService.get(ref)` | `PaymentIntent` | Busca por ref |
| `PaymentService.get_by_order(order_ref)` | `QuerySet` | Todos os intents de um pedido |
| `PaymentService.get_active_intent(order_ref)` | `PaymentIntent \| None` | Intent não-terminal mais recente |
| `PaymentService.get_by_gateway_id(gateway_id)` | `PaymentIntent \| None` | Busca por ID externo |
| `PaymentService.captured_total(ref)` | `int` (centavos) | Total capturado |
| `PaymentService.refunded_total(ref)` | `int` (centavos) | Total reembolsado |

## PaymentTransaction

- **Imutável**: uma vez criada, não pode ser atualizada nem deletada.
- Correções são feitas via nova Transaction (ex: refund parcial adicional).
- Tipos: `capture`, `refund`, `chargeback`.
- `amount_q` é sempre positivo (`> 0`), validado por CheckConstraint.
