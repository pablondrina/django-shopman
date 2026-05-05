# Operações

Guia curto para operadores / ops de produção. Cresce conforme amadurecemos
deploy, observabilidade e incident response.

## Health checks

Dois endpoints, sem auth, sem CSRF, sem rate limit, JSON puro.

### `GET /health/` — liveness

Responde se o processo Django está vivo e consegue falar com o banco e o cache.
Usado por **load balancers** e **k8s livenessProbe** para decidir se o container
precisa ser reiniciado.

- **200 ok**: banco acessível, cache operacional (ou `skipped` se `LocMemCache`).
- **503 error**: banco inacessível **ou** cache quebrado.
- Migrations pendentes **não** causam 503 aqui — liveness não deve reiniciar
  container por schema drift (isso é readiness).

Exemplo:

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "cache": "skipped",
    "migrations": "ok"
  }
}
```

### `GET /ready/` — readiness

Tudo do `/health/` + verifica que **não há migrations pendentes**. Usado por
**k8s readinessProbe** e **deploy validation** para segurar tráfego até que o
schema esteja alinhado com o código em produção.

- **200 ok**: pronto para receber tráfego.
- **503 error**: qualquer check falhou (inclui migrations).

### Snippet k8s

```yaml
livenessProbe:
  httpGet:
    path: /health/
    port: 8000
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready/
    port: 8000
  periodSeconds: 5
  failureThreshold: 2
```

### Snippet uptime monitor

```bash
curl -fsS https://seu-host/health/ || alerta
```

### Cache em dev e produção

`LocMemCache` não é production-grade (per-process, some a cada restart), então
o check de cache retorna `skipped` em fallback local — não é um sinal negativo
nesse modo. Em staging/producao, `REDIS_URL` é obrigatório: o check faz
roundtrip `set`/`get` e falha se o Redis estiver inacessível.

Redis é usado para cache compartilhado, `django-ratelimit`, caches operacionais
curtos e fanout SSE multi-worker. Ver o contrato em
[`docs/reference/runtime-dependencies.md`](../reference/runtime-dependencies.md).

### Observabilidade

Sucessos **não** geram log (evita poluição em ambientes com probes de alta
frequência). Falhas emitem `WARNING` em `shopman.shop.views.health` com a lista
de checks críticos que falharam.

## Logs estruturados

Em produção, `SHOPMAN_JSON_LOGS=true` por padrão quando `DJANGO_DEBUG=false`.
Cada linha vai para stdout como JSON compacto, com `timestamp`, `level`,
`logger`, `message` e campos extras como `event`, `order_ref`, `intent_ref`,
`gateway` e `provider`.

Para voltar ao formato humano em um ambiente específico:

```env
SHOPMAN_JSON_LOGS=false
```

Eventos operacionais críticos usam nomes estáveis:

- `payment.reconciled`
- `payment_reconciliation.failed`
- `webhook.failed`
- `operator_alert.created`
- `operator_alert.debounced`

## Alertas operacionais

Falhas que exigem ação humana criam `OperatorAlert` com debounce local:

- `webhook_failed`: webhook autenticado entrou, mas o processamento falhou.
- `payment_reconciliation_failed`: divergência de gateway/Payman ou falha ao
  aplicar reconciliação.

Esses alertas aparecem no Backstage junto dos alertas de estoque, produção e
pagamento já existentes. Replays ou erros de assinatura/token não criam alerta
por padrão para evitar spam; continuam aparecendo em log.

## Reconciliação financeira diária

Use após o fechamento do dia para cruzar pedido, `PaymentIntent`,
`PaymentTransaction` e `DayClosing`:

```bash
make reconcile-financial-day date=YYYY-MM-DD dry_run=1
make reconcile-financial-day date=YYYY-MM-DD require_closing=1
```

O comando grava o resumo em `DayClosing.data["financial_reconciliation"]` e as
divergências em `DayClosing.data["financial_reconciliation_errors"]`. Em
divergência `error` ou `critical`, cria `OperatorAlert` do tipo
`payment_reconciliation_failed`.

O escopo atual valida o contrato interno. Snapshot real de gateway depende de
credenciais sandbox/staging e permanece no plano de smoke dos provedores.

## Smoke de gateways

Use antes de release e depois de mexer em webhooks/pagamentos:

```bash
make smoke-gateways
make smoke-gateways json=1
make smoke-gateways-sandbox
```

`make smoke-gateways` roda fixtures locais com rollback e exercita os caminhos
canônicos de EFI PIX, Stripe e iFood: replay, idempotência, pagamento atrasado,
refund cumulativo fora de ordem e pedido externo duplicado. A saída também mostra
se a validação real de sandbox/staging está `ready` ou `blocked_by_credentials`.

`make smoke-gateways-sandbox` é propositalmente estrito: sem credenciais reais de
sandbox/staging, falha com `blocked_by_credentials`. Não use o smoke local como
prova de que o provedor externo foi validado.

## QA manual Omotenashi

Use antes de release com mudança visual, fluxo de pedido, pagamento, KDS, POS ou
Backstage:

```bash
make seed
make omotenashi-qa strict=1
make omotenashi-qa json=1
make run
make omotenashi-browser-qa strict=1
```

`make omotenashi-qa` garante que a rodada manual parte do mesmo seed e aponta
URLs/evidências para mobile, tablet/KDS e desktop gerente.
`make omotenashi-browser-qa` navega essa matriz em Chrome headless, gera
screenshots em `/tmp/shopman-omotenashi-qa-screens` e relatório JSON em
`/tmp/shopman-omotenashi-qa-browser.json`. Ele não substitui dispositivo físico
nem julgamento visual humano antes de release real. O roteiro fica em
[`docs/guides/omotenashi-qa.md`](omotenashi-qa.md).

### Segurança

- Endpoints não expõem stacktrace, config, nem dados de negócio — apenas o
  nome da classe da exceção (`OperationalError`, `ConnectionRefusedError`).
- Não retornam sessão, token, ou cookie.
- Públicos por design (probes não autenticam).
