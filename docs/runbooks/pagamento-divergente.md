# Pagamento divergente

## Sintoma visivel

Pedido, `PaymentIntent` e transacoes nao batem: capturado apos cancelamento,
refund maior que captura, intent sem pedido, ou pedido concluido com saldo
capturado insuficiente.

## Impacto

Risco financeiro direto, atendimento confuso e fechamento diario incorreto.

## Diagnostico

```bash
make diagnose-payments
make diagnose-webhooks
make reconcile-financial-day date=YYYY-MM-DD dry_run=1
python manage.py reconcile_payments --since=1d --dry-run
```

Leia primeiro `payment divergences`. A referencia canonica de pagamento e
`PaymentIntent` + `PaymentTransaction`; `Order.data.payment.intent_ref` e apenas
o elo operacional. O comando `reconcile_financial_day` cruza o dia inteiro e
mostra divergencias persistiveis no fechamento.

## Acao imediata segura

1. Congelar a decisao operacional do pedido: nao entregar, cancelar ou estornar
   sem confirmar gateway.
2. Preservar refs: `order`, `intent`, `gateway`, valores em `q`.
3. Se o problema for webhook perdido e o dry-run estiver correto, executar:

```bash
python manage.py reconcile_payments --since=1d
```

## Recuperacao

- Intent sem pedido: investigar criacao incompleta antes de refund/capture.
- Pedido cancelado com saldo capturado: confirmar gateway e iniciar refund pelo
  fluxo canonico.
- Refund parcial suspeito: comparar soma de transacoes, gateway e fechamento.
- Dia fechado com divergencia: depois de validar o dry-run, executar
  `make reconcile-financial-day date=YYYY-MM-DD require_closing=1` para gravar o
  resumo em `DayClosing`.

## Escalar

Escalar qualquer divergencia que envolva valor capturado liquido, chargeback,
pedido entregue ou gateway mostrando status diferente do Payman.

## Evidencia minima

`order_ref`, `intent_ref`, status do pedido, status do intent, capture/refund em
`q`, gateway status, saida de `make diagnose-payments`.
