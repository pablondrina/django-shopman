# Referência de Management Commands

> Gerado a partir dos arquivos em `management/commands/` do código atual.

---

## Visão Geral

| Comando | App | Categoria | Descrição |
|---------|-----|-----------|-----------|
| [`release_expired_holds`](#release_expired_holds) | stocking | Manutenção | Libera holds expirados |
| [`load_crafting_demo`](#load_crafting_demo) | crafting | Seed | Carrega dados demo de produção |
| [`process_directives`](#process_directives) | ordering | Worker | Processa fila de directives |
| [`cleanup_idempotency_keys`](#cleanup_idempotency_keys) | ordering | Manutenção | Remove chaves de idempotência antigas |
| [`customers_cleanup`](#customers_cleanup) | customers | Manutenção | Remove eventos processados antigos |
| [`auth_cleanup`](#auth_cleanup) | auth | Manutenção | Remove tokens/códigos expirados |
| [`seed`](#seed) | shop | Seed | Popula banco com dados da Nelson Boulangerie |

---

## Detalhes

### release_expired_holds

**App:** `shopman.stocking`
**Arquivo:** `packages/stockman/shopman/stocking/management/commands/release_expired_holds.py`

Libera bloqueios de estoque que ultrapassaram o TTL configurado (`STOCKING.HOLD_TTL_MINUTES`).

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

**App:** `shopman.crafting`
**Arquivo:** `packages/craftsman/shopman/crafting/management/commands/load_crafting_demo.py`

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

**App:** `shopman.ordering`
**Arquivo:** `packages/omniman/shopman/ordering/management/commands/process_directives.py`

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

**App:** `shopman.ordering`
**Arquivo:** `packages/omniman/shopman/ordering/management/commands/cleanup_idempotency_keys.py`

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

**App:** `shopman.customers` (app label: `customers`)
**Arquivo:** `packages/guestman/shopman/customers/management/commands/customers_cleanup.py`

Remove ProcessedEvent mais antigos que o threshold configurado (`CUSTOMERS.EVENT_CLEANUP_DAYS`, default 90 dias).

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

**App:** `shopman.auth` (app label: `auth`)
**Arquivo:** `packages/doorman/shopman/auth/management/commands/auth_cleanup.py`

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

### seed

**App:** `shop`
**Arquivo:** `framework/shopman/management/commands/seed.py`

Popula o banco com dados completos da Nelson Boulangerie: catálogo (13 produtos + 1 bundle), estoque (3 posições), receitas (6 com BOM), clientes (7), canais (5), pedidos (105+), sessões abertas (3), alertas de estoque (7), e superuser admin.

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

# Worker de directives (systemd/supervisor, não cron)
# python manage.py process_directives --watch
```
