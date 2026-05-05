# Pedido pago sem confirmacao

## Sintoma visivel

Cliente pagou, gateway mostra confirmado, mas o pedido segue `new` ou sem entrar
na fila operacional.

## Impacto

Experiencia ruim para cliente e risco de preparo atrasado ou duplicado.

## Diagnostico

```bash
make diagnose-payments
make diagnose-webhooks
python manage.py reconcile_payments --since=4h --dry-run
```

Procure `paid_not_confirmed`, alerta `payment_reconciliation_failed` ou webhook
travado.

## Acao imediata segura

1. Confirmar no gateway se a captura existe.
2. Se o dry-run apontar `on_paid`, executar a reconciliacao.
3. Avisar operador para nao recriar o pedido antes da reconciliacao.

## Recuperacao

Depois da reconciliacao, confirmar que o pedido avancou para o estado esperado e
que directives de fulfillment/notificacao nao ficaram `failed`.

```bash
make diagnose-worker
make diagnose-payments
```

## Escalar

Escalar se a captura existe mas `reconcile_payments` falha, se ha mais de um
intent para o mesmo pedido, ou se o gateway mostra evento duplicado fora de
ordem.

## Evidencia minima

`order_ref`, `intent_ref`, status gateway, status antes/depois, saidas dos
diagnosticos e horario.

