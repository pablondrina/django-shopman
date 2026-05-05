# Referência de Management Commands

> Gerado a partir dos arquivos em `management/commands/` do código atual.

---

## Visão Geral

| Comando | App | Categoria | Descrição |
|---------|-----|-----------|-----------|
| [`release_expired_holds`](#release_expired_holds) | stockman | Manutenção | Libera holds expirados |
| [`load_crafting_demo`](#load_crafting_demo) | craftsman | Seed | Carrega dados demo de produção |
| [`process_directives`](#process_directives) | orderman | Worker | Processa fila de directives |
| [`cleanup_idempotency_keys`](#cleanup_idempotency_keys) | orderman | Manutenção | Remove chaves de idempotência antigas |
| [`customers_cleanup`](#customers_cleanup) | guestman | Manutenção | Remove eventos processados antigos |
| [`auth_cleanup`](#auth_cleanup) | doorman | Manutenção | Remove tokens/códigos expirados |
| [`reconcile_payments`](#reconcile_payments) | shop | Operação | Reconcilia pedidos cujo webhook de pagamento pode ter sido perdido |
| [`reconcile_financial_day`](#reconcile_financial_day) | backstage | Operação | Reconcilia pedido, intent, transação e fechamento diário |
| [`smoke_gateways`](#smoke_gateways) | backstage | Operação | Estressa webhooks/gateways com fixtures locais e matriz sandbox |
| [`omotenashi_qa`](#omotenashi_qa) | backstage | QA | Lista matriz manual QA Omotenashi com evidências do seed |
| [`seed`](#seed) | shop | Seed | Popula banco com dados da Nelson Boulangerie |

---

## Detalhes

### release_expired_holds

**App:** `shopman.stockman`
**Arquivo:** `packages/stockman/shopman/stockman/management/commands/release_expired_holds.py`

Libera bloqueios de estoque que ultrapassaram o TTL configurado (`STOCKMAN.HOLD_TTL_MINUTES`).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--dry-run` | — | Mostra quantos holds seriam liberados sem executar |

```bash
# Verificar holds expirados
python manage.py release_expired_holds --dry-run

# Liberar holds expirados
python manage.py release_expired_holds
```

**Recomendação:** Executar via cron a cada 5–15 minutos.

---

### load_crafting_demo

**App:** `shopman.craftsman`
**Arquivo:** `packages/craftsman/shopman/craftsman/management/commands/load_crafting_demo.py`

Cria dados de demonstração para produção: 4 receitas de padaria (croissant, pão francês, baguette, brioche) com BOM de ingredientes e work orders distribuídas em 10 dias.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--clear` | — | Limpa dados existentes antes de carregar |

```bash
# Carregar dados demo
python manage.py load_crafting_demo

# Limpar e recarregar
python manage.py load_crafting_demo --clear
```

---

### process_directives

**App:** `shopman.orderman`
**Arquivo:** `packages/orderman/shopman/orderman/management/commands/process_directives.py`

Processa directives enfileiradas usando os handlers registrados. Implementa row-level locking (`skip_locked`), retry com backoff exponencial, e reaping de directives "stuck".

| Flag | Default | Descrição |
|------|---------|-----------|
| `--topic` | *(todos)* | Tópico específico para processar (repetível) |
| `--limit` | `50` | Máx. directives por execução |
| `--watch` | — | Modo contínuo (loop simples) |
| `--interval` | `2` | Segundos entre iterações no modo watch |
| `--max-attempts` | `5` | Máx. tentativas antes de marcar como falha |
| `--reap-timeout` | `10` | Minutos para considerar directive "stuck" |

```bash
# Processar uma vez
python manage.py process_directives

# Modo worker contínuo
python manage.py process_directives --watch

# Processar apenas stock e payment
python manage.py process_directives --topic stock.hold --topic payment.capture

# Worker com configuração customizada
python manage.py process_directives --watch --interval 5 --limit 100 --max-attempts 3
```

**Veja também:** [ADR-003 — Directives sem Celery](../decisions/adr-003-directives-sem-celery.md)

---

### cleanup_idempotency_keys

**App:** `shopman.orderman`
**Arquivo:** `packages/orderman/shopman/orderman/management/commands/cleanup_idempotency_keys.py`

Remove IdempotencyKeys expiradas ou antigas. Limpa 3 categorias: keys com `expires_at` passado, keys antigas (done/failed), e opcionalmente keys "in_progress" órfãs (> 1h).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--days` | `7` | Remove keys mais antigas que N dias |
| `--dry-run` | — | Mostra o que seria removido |
| `--include-in-progress` | — | Inclui keys "in_progress" órfãs (> 1h) |

```bash
# Preview
python manage.py cleanup_idempotency_keys --dry-run

# Cleanup padrão (7 dias)
python manage.py cleanup_idempotency_keys

# Cleanup agressivo incluindo keys órfãs
python manage.py cleanup_idempotency_keys --days 3 --include-in-progress
```

**Recomendação:** Executar via cron diariamente.

---

### customers_cleanup

**App:** `shopman.guestman` (app label: `guestman`)
**Arquivo:** `packages/guestman/shopman/guestman/management/commands/customers_cleanup.py`

Remove ProcessedEvent mais antigos que o threshold configurado (`GUESTMAN.EVENT_CLEANUP_DAYS`, default 90 dias).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--days` | *(da config)* | Override do threshold em dias |
| `--dry-run` | — | Mostra quantos eventos seriam removidos |

```bash
# Preview com default da config
python manage.py customers_cleanup --dry-run

# Cleanup com threshold custom
python manage.py customers_cleanup --days 30
```

**Recomendação:** Executar via cron semanalmente.

---

### auth_cleanup

**App:** `shopman.doorman` (app label: `doorman`)
**Arquivo:** `packages/doorman/shopman/doorman/management/commands/auth_cleanup.py`

Limpa artefatos de autenticação expirados: AccessLinks, VerificationCodes e TrustedDevices.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--days` | `7` | Remove registros mais antigos que N dias |
| `--dry-run` | — | Mostra o que seria removido |

```bash
# Preview
python manage.py auth_cleanup --dry-run

# Cleanup padrão
python manage.py auth_cleanup

# Cleanup conservador
python manage.py auth_cleanup --days 30
```

**Recomendação:** Executar via cron diariamente.

---

### reconcile_payments

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/reconcile_payments.py`

Reconcilia pedidos `new`/`confirmed` antigos com `PaymentIntent` quando o
webhook pode ter sido perdido. E idempotente e deve ser rodado primeiro em
`--dry-run` durante incidente.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--since` | `2h` | Considera pedidos criados antes de N tempo (`30m`, `4h`, `1d`) |
| `--dry-run` | — | Lista a acao sem executar transicao |

```bash
# Preview seguro
python manage.py reconcile_payments --since=4h --dry-run

# Executar reconciliacao apos validar gateway/dry-run
python manage.py reconcile_payments --since=4h
```

**Veja também:** [runbook de pedido pago sem confirmacao](../runbooks/pedido-pago-sem-confirmacao.md).

---

### reconcile_financial_day

**App:** `shopman.backstage`
**Arquivo:** `shopman/backstage/management/commands/reconcile_financial_day.py`

Gera auditoria financeira diária cruzando pedidos, `PaymentIntent`,
`PaymentTransaction` e `DayClosing`. Quando não está em `--dry-run`, persiste o
resumo em `DayClosing.data["financial_reconciliation"]` e divergências em
`DayClosing.data["financial_reconciliation_errors"]`. Divergência `error` ou
`critical` cria alerta `payment_reconciliation_failed`.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--date` | ontem | Data local `YYYY-MM-DD` |
| `--dry-run` | — | Gera relatório sem persistir e sem alertar |
| `--require-closing` | — | Ausência de `DayClosing` vira erro |
| `--no-alert` | — | Persiste sem criar `OperatorAlert` |
| `--json` | — | Imprime JSON auditável |

```bash
# Preview seguro de uma data
make reconcile-financial-day date=2026-05-05 dry_run=1

# Rotina pós-fechamento, exigindo DayClosing
make reconcile-financial-day date=2026-05-05 require_closing=1

# JSON para anexar em incidente
python manage.py reconcile_financial_day --date=2026-05-05 --dry-run --json
```

**Veja também:** [runbook de pagamento divergente](../runbooks/pagamento-divergente.md).

---

### smoke_gateways

**App:** `shopman.backstage`
**Arquivo:** `shopman/backstage/management/commands/smoke_gateways.py`

Executa um smoke operacional de gateways usando fixtures locais com rollback:
EFI PIX duplicado e atrasado após cancelamento, Stripe capture/replay/refund
cumulativo fora de ordem e iFood pedido externo duplicado. Também reporta matriz
de prontidão sandbox/staging sem marcar provedor real como validado quando faltam
credenciais.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--local-only` | — | Só executa fixtures locais |
| `--sandbox-only` | — | Só avalia credenciais/prontidão sandbox |
| `--require-sandbox` | — | Falha se sandbox estiver bloqueado |
| `--keep-data` | — | Não faz rollback das fixtures locais |
| `--json` | — | Imprime JSON auditável |

```bash
# Smoke local + matriz sandbox, com rollback
make smoke-gateways

# JSON para anexar em release/incidente
make smoke-gateways json=1

# Gate estrito de sandbox/staging real
make smoke-gateways-sandbox
```

Sem credenciais reais, `smoke-gateways-sandbox` retorna
`blocked_by_credentials`; isso é bloqueio honesto, não sucesso falso.

---

### omotenashi_qa

**App:** `shopman.backstage`
**Arquivo:** `shopman/backstage/management/commands/omotenashi_qa.py`

Lista a matriz manual QA Omotenashi para mobile, tablet/KDS e desktop gerente,
apontando a URL a abrir e a evidência concreta criada pelo seed Nelson. O modo
estrito falha quando qualquer cenário não tem dado seed correspondente.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--json` | — | Imprime JSON auditável |
| `--strict` | — | Falha se algum cenário estiver sem evidência |

```bash
# Depois do seed, verificar se a rodada manual está pronta
make omotenashi-qa strict=1

# JSON para anexar em release
make omotenashi-qa json=1
```

**Veja também:** [QA Manual Omotenashi E2E](../guides/omotenashi-qa.md).

---

## Wrappers de diagnóstico

Os diagnosticos operacionais vivem em `scripts/diagnose_operational.py` e sao
expostos por Makefile para nao exigir conhecimento de Docker:

```bash
make diagnose-runtime
make diagnose-worker
make diagnose-payments
make diagnose-webhooks
make diagnose-health
```

Saida `FAIL` significa acao operacional pendente. Ver
[`docs/runbooks/`](../runbooks/README.md).

---

### seed

**App:** `shop`
**Arquivo:** `instances/nelson/management/commands/seed.py`

Popula o banco com dados completos da Nelson Boulangerie: catálogo, estoque,
receitas, clientes, canais, pedidos, pagamentos com `Order.data.payment.intent_ref`,
sessões abertas, alertas, POS/KDS e superuser admin.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--flush` | — | Deleta TODOS os dados antes de popular |

```bash
# Popular banco
python manage.py seed

# Resetar e popular do zero
python manage.py seed --flush
```

**Variável de ambiente:** `ADMIN_PASSWORD` — senha do superuser (default: `"admin"`).

---

## Cron Recomendado

```cron
# Liberar holds expirados (a cada 10 min)
*/10 * * * * cd /app && python manage.py release_expired_holds

# Limpar idempotency keys (diário, 3h)
0 3 * * * cd /app && python manage.py cleanup_idempotency_keys

# Limpar tokens de auth (diário, 3h)
5 3 * * * cd /app && python manage.py auth_cleanup

# Limpar eventos processados (semanal, domingo 4h)
0 4 * * 0 cd /app && python manage.py customers_cleanup

# Reconciliação defensiva de pagamentos (diário, 4h30)
30 4 * * * cd /app && python manage.py reconcile_payments --since=1d

# Auditoria financeira diária (após fechamento)
45 4 * * * cd /app && python manage.py reconcile_financial_day --require-closing

# Worker de directives (systemd/supervisor, não cron)
# python manage.py process_directives --watch
```
