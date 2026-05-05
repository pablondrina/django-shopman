# OPERATION-RUNBOOKS-PLAN

> Criado em 2026-05-05.

## Objetivo

Transformar o hardening de operação real em procedimentos curtos, testáveis e
acionáveis. O operador nao deve precisar entender Docker, internals de Django ou
gateway para diagnosticar incidente comum.

Este plano começa depois do bloco Django 6:

- Django 6 foi migrado e arquivado em
  [`completed/DJANGO-6-UPGRADE-PLAN.md`](completed/DJANGO-6-UPGRADE-PLAN.md);
- Runtime Gate com PostgreSQL/Redis e build Docker passou no PR #3;
- Redis segue nativo via `django.core.cache.backends.redis.RedisCache`, sem
  `django-redis`.

## Escopo

### WP-OR-1 — Runbooks de incidente

Status: baseline implementado em [`docs/runbooks/`](../runbooks/).

Criar runbooks curtos em `docs/runbooks/` para:

- webhook falhando;
- pagamento divergente ou refund parcial suspeito;
- Redis fora ou sem fanout SSE;
- PostgreSQL lento ou indisponível;
- directive worker parado;
- pedido pago sem confirmação;
- estoque divergente;
- loja fechada/aberta em estado errado.

Cada runbook deve ter:

- sintoma visível;
- impacto para cliente/operador;
- comandos de diagnóstico;
- ação imediata segura;
- ação de recuperação;
- quando escalar;
- evidência mínima para pós-incidente.

### WP-OR-2 — Comandos `make` de diagnóstico

Status: baseline implementado via `scripts/diagnose_operational.py` e targets
`make diagnose-runtime`, `make diagnose-worker`, `make diagnose-payments`,
`make diagnose-webhooks` e `make diagnose-health`.

Adicionar wrappers simples, sem exigir Docker manual:

- `make diagnose-runtime`: DB, Redis, cache, SSE/eventstream, settings críticos;
- `make diagnose-worker`: backlog de directives, oldest directive, retries e erros;
- `make diagnose-payments`: pedidos pagos/divergentes, intents sem pedido e refunds;
- `make diagnose-webhooks`: últimos eventos idempotentes, falhas e alertas;
- `make diagnose-health`: health/readiness + `check --deploy` em modo seguro.

Os comandos podem chamar scripts Python em `scripts/` ou management commands.
Saída deve ser curta, textual e própria para suporte.

### WP-OR-3 — Healthcheck profundo

Status: parcialmente implementado como diagnóstico CLI nao público em
`make diagnose-health`. Endpoint público segue enxuto por segurança.

Complementar `/health/` e `/ready/` com um diagnóstico operacional não público
ou comando CLI que cubra:

- worker de directives vivo ou backlog dentro de limite;
- Redis cache roundtrip;
- eventstream Redis configurado;
- conexão PostgreSQL;
- migrations aplicadas;
- storage/static sanity quando em deploy;
- adapters críticos configurados fora de `DEBUG`.

Nao expor segredo, token, payload de cliente ou dados financeiros em endpoint
público.

### WP-OR-4 — Reconciliação financeira diária

Status: baseline interno implementado em `reconcile_financial_day` e no wrapper
`make reconcile-financial-day`. O comando cruza pedido, `PaymentIntent`,
`PaymentTransaction` e `DayClosing`, persiste resumo no fechamento e cria alerta
`payment_reconciliation_failed` para divergência `error`/`critical`.

Pendente neste WP: snapshot real de gateway quando houver credenciais sandbox ou
staging; sem credenciais, o comando não finge validação externa.

Amarrar a rotina diária de reconciliação:

- pedido ↔ `PaymentIntent`;
- transações capture/refund;
- gateway snapshot quando disponível;
- fechamento do dia;
- alerta operacional para divergência;
- saída de comando com resumo auditável.

Sem credenciais sandbox, validar localmente o contrato interno. Com credenciais
sandbox, rodar smoke real em staging.

### WP-OR-5 — Gateway sandbox smoke

Status: baseline local implementado em `smoke_gateways` e nos wrappers
`make smoke-gateways` / `make smoke-gateways-sandbox`. O smoke local roda com
rollback e cobre EFI PIX duplicado/atrasado após cancelamento, Stripe
capture/replay/refund cumulativo fora de ordem e iFood pedido externo duplicado.
Sandbox/staging real continua bloqueado até existirem credenciais e ambiente.

Quando houver credenciais:

- EFI Pix: intent criado, pago, webhook duplicado, webhook atrasado;
- Stripe: checkout/session, capture, refund parcial, refund total, evento fora
  de ordem;
- iFood: pedido externo duplicado, cancelamento, evento atrasado;
- ManyChat: access link, session, confirmação e notificação.

Sem credenciais, `make smoke-gateways-sandbox` reporta
`blocked_by_credentials`, não passa falsamente. O smoke local prova contrato
interno; não substitui snapshot real do provedor.

## Critério de Pronto

- `docs/runbooks/` tem runbook para cada incidente P1 listado.
- `make diagnose-*` existe e roda localmente sem comandos Docker manuais.
- `Runtime Gate` segue verde.
- Divergência financeira cria alerta `payment_reconciliation_failed`.
- `docs/status.md` aponta o último gate verde e o estado dos runbooks.
