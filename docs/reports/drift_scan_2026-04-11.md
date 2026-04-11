# Drift Scan Audit — 2026-04-11

Auditoria de drift entre código, docs e convenções. Todos os achados foram corrigidos nesta sessão.

---

## CRITICAL

### C1. AF-2 lifecycle regression — CORRIGIDO
`commit.py:314` escrevia `"lifecycle": effective_config.get("lifecycle", {})` ao snapshot, mas `ChannelConfig` não tinha campo `lifecycle` → sempre `{}`.

**Fix**: Adicionado `lifecycle: dict = field(default_factory=dict)` ao `ChannelConfig` em `config.py`, com chaves `transitions` (dict status→list[status]) e `terminal_statuses` (list[str]).

### C2. POS bypasses ChannelConfig — CORRIGIDO
`pos.py` carregava config mas não passava `channel_config` para `ModifyService`/`CommitService`.

**Fix**: Adicionado `channel_config=config.to_dict()` nas duas chamadas, espelhando o padrão de `checkout.py`.

---

## HIGH

### A1. URL gerund paths — CORRIGIDO
`project/urls.py` tinha `api/ordering/`, `api/offering/`, `api/stocking/`, `api/crafting/`.

**Fix**: Renomeados para `api/orderman/`, `api/offerman/`, `api/stockman/`, `api/craftsman/`.

### A2. "balcao" hardcoded — CORRIGIDO
`pos.py` tinha ~6 ocorrências hardcoded. `cash_register.py` também.

**Fix**: Criado `POS_CHANNEL_REF` em `web/constants.py` (override via `SHOPMAN_POS_CHANNEL_REF`). Adicionado `_POS_CHANNEL_REF` em `models/cash_register.py`. Todas as ocorrências substituídas.

### A3. Payment methods — CORRIGIDO
`pos.py` usava `"dinheiro"`/`"cartao"` como valores canônicos.

**Fix**: `_PAYMENT_METHODS` e default `"counter"` em `pos.py`. `payment.py` whitelist removeu `"dinheiro"`. `cash_register.py` filtro `data__payment__method="counter"`.

### A4. hold_ids docs — CORRIGIDO
`data-schemas.md` documentava `list[str]`, código usa `list[dict] {sku, hold_id, qty}`.

**Fix**: Tipo e descrição corrigidos em `data-schemas.md`.

### A5. Lint — CORRIGIDO
`ruff check --fix` nas production files: `cash_register.py`, `catalog.py`, `pos.py`, `fiscal.py`, `suggest_production.py`, craftsman contrib admin, doorman `senders.py`, guestman api views.

---

## MEDIUM

### M1. Glossary ChannelConfig — CORRIGIDO
"6 aspectos" → "8 aspectos". Lista correta: confirmation, payment, fulfillment, stock, notifications, pricing, editing, rules.

### M2. data-schemas.md — CORRIGIDO
Adicionadas chaves `stock_check_unavailable` e `manual_discount` à tabela de `Session.data`.

### M3. customer_name flat access — CORRIGIDO
`kds.py` e `pedidos.py` usavam `order.data.get("customer_name", "")`.

**Fix**: Agora usam `order.data.get("customer", {}).get("name", "")` (acesso canônico).

---

## TERMINOLOGY: flows → lifecycle — CORRIGIDO

- `flows.py` → `lifecycle.py` (git mv)
- `production_flows.py` → `production_lifecycle.py` (git mv)
- Todos os imports `from shopman.flows import` → `from shopman.lifecycle import`
- Todos os `@patch("shopman.flows.*")` → `@patch("shopman.lifecycle.*")`
- `apps.py` docstrings e dispatch_uid atualizados
- `CLAUDE.md` atualizado: remove BaseFlow/LocalFlow/RemoteFlow, descreve padrão config-driven
- `docs/guides/flows.md` → `docs/guides/lifecycle.md` (git mv) com conteúdo reescrito

---

## CLEANUP

- `docs/reports/` criado
- Este arquivo salvo como referência permanente
