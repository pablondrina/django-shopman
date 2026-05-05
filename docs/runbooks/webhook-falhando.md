# Webhook falhando

## Sintoma visivel

Pagamento, marketplace ou notificacao externa nao muda o pedido; alertas
`webhook_failed` aparecem no admin; gateway reenvia eventos.

## Impacto

Cliente pode pagar sem receber confirmacao, operador perde confianca na fila e
eventos duplicados podem se acumular.

## Diagnostico

```bash
make diagnose-webhooks
make diagnose-runtime
make deploy-logs
```

Verifique `failed webhook keys`, `stale webhook keys` e alertas ativos. Nao use
payload de cliente como evidencia principal; use `scope`, `id`, `order_ref`,
provider e horario.

## Acao imediata segura

1. Nao marcar pedido como pago manualmente sem checar o gateway.
2. Se o gateway mostra pagamento confirmado, rode reconcilicao em dry-run:

```bash
python manage.py reconcile_payments --since=4h --dry-run
```

3. Se o dry-run aponta a acao correta, rode sem `--dry-run`.

## Recuperacao

- Corrigir token/secret ausente se `make diagnose-health` apontar falha.
- Garantir Redis/eventstream ativos se os eventos chegam mas a tela nao atualiza.
- Reenfileirar manualmente apenas depois de confirmar que a chave idempotente nao
  esta `in_progress` recente.

## Escalar

Escalar se houver `in_progress` com mais de 5 minutos, falha recorrente no mesmo
provider, divergencia financeira ou evento pago sem pedido correspondente.

## Evidencia minima

Horario, provider, `scope`, id da chave idempotente, `order_ref`, status no
gateway, saida de `make diagnose-webhooks` e decisao tomada.

