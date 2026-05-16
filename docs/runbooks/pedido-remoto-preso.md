# Pedido remoto preso

## Sintoma visivel

Cliente veio por WhatsApp/Nuxt/Ionic, mas o pedido nao avanca: pagamento nao
aparece, tracking fica parado, AccessLink expirou, ManyChat nao responde, hold
sumiu ou directive falhou.

## Impacto

Cliente perde confianca, estoque pode ficar reservado indevidamente e operador
pode tentar corrigir pelo caminho errado.

## Diagnostico

Comece pelo pedido especifico:

```bash
python manage.py diagnose_remote_order ORDER-REF
```

Depois rode apenas os diagnosticos relacionados ao achado:

```bash
make diagnose-worker
make diagnose-payments
make diagnose-webhooks
python manage.py release_expired_holds --dry-run
python manage.py auth_cleanup --dry-run
```

Leia `result=OK/WARN/FAIL` e as linhas `recommendation=...`. O comando
`diagnose_remote_order` nao altera estado; ele so le Order, Payman, Directives,
Stockman, channel policy e projection conversacional.

## Acao imediata segura

1. Nao editar `Order.status` direto.
2. Nao marcar pagamento manualmente para liberar pedido digital.
3. Nao recriar regra de disponibilidade/preco no ManyChat.
4. Preservar `order_ref`, `intent_ref`, directive ids, hold ids e horario.

## Recuperacao por causa

### Aguardando pagamento

- Se o cliente diz que pagou, validar gateway/Payman.
- Rodar primeiro:

```bash
python manage.py reconcile_payments --since=4h --dry-run
```

- Executar sem `--dry-run` apenas se o dry-run e o gateway concordarem.

### Aguardando confirmacao

- Verificar se `confirmation.timeout` existe e se o worker esta processando.
- Se o pedido esta `new` com pagamento capturado, operador deve confirmar ou
  rejeitar pelo fluxo canonico; gateway nao confirma pedido operacionalmente.

### Directive failed/running/queued

```bash
python manage.py process_directives --limit=50
```

- Se `failed` persistir, usar o runbook do tema do topico: pagamento,
  notificacao, estoque ou fulfillment.

### AccessLink expirado ou usado

- Gerar novo AccessLink pelo Doorman/adaptador autorizado.
- Nao reutilizar token antigo; token bruto nao e persistido.
- Rodar `python manage.py auth_cleanup --dry-run` para avaliar lixo expirado.

### ManyChat indisponivel

- Usar fallback chain configurado em `ChannelConfig.notifications`.
- Se for entrega de AccessLink, usar SMS/email apenas se o cliente puder ser
  identificado com seguranca.
- Registrar indisponibilidade ManyChat e manter Shopman como fonte de verdade.

### Stock hold expirado/divergente

```bash
python manage.py release_expired_holds --dry-run
```

- Se o hold expirou antes do commit, refazer availability/check pelo fluxo
  canonico.
- Se a divergencia for fisica, pausar SKU afetado e seguir runbook de estoque.

## Escalar

Escalar se ha pagamento capturado sem pedido confirmavel, directive failed
apos retries, hold divergente em pedido pago, AccessLink gerado para cliente
errado, ou ManyChat indisponivel impactando pedidos ativos.

## Evidencia minima

`order_ref`, canal, `Order.status`, `intent_ref`, status Payman/gateway, ids de
directive, ids de hold, AccessLink id/audience/source, saida de
`diagnose_remote_order`, horario e acao tomada.
