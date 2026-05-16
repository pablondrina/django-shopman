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

## Reconciliation

- **Snapshots de gateway são cumulativos.** `PaymentService.reconcile_gateway_status()` recebe totais do gateway (`captured_q`, `refunded_q`) e grava apenas o delta local necessário.
- **Sem replay financeiro.** Repetir o mesmo snapshot não cria nova transação.
- **Sem voltar dinheiro no tempo.** Se o gateway reporta refund menor que o total local, o serviço falha com `reconciliation_refund_mismatch`.
- **Sem fail-open.** Divergência de valor, moeda, gateway id ou captura após cancelamento local gera `PaymentError` específico para revisão operacional.
- **Stripe:** `charge.amount_refunded` é cumulativo; o adapter reconcilia esse total em vez de tratá-lo como delta.

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
| `PaymentService.reconcile_gateway_status(ref, ...)` | `PaymentReconciliationResult` | Aplica snapshot cumulativo do gateway |

## PaymentTransaction

- **Imutável**: uma vez criada, não pode ser atualizada nem deletada.
- Correções são feitas via nova Transaction (ex: refund parcial adicional).
- Tipos: `capture`, `refund`, `chargeback`.
- `amount_q` é sempre positivo (`> 0`), validado por CheckConstraint.
