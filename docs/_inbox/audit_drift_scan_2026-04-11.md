# Drift Scan — 2026-04-11 (atualizado 2026-04-14)

> **Atualização pós-P0 (2026-04-14):** Todos os achados do scan original foram corrigidos.
> Documento atualizado para refletir:
> - Reestruturação: `framework/shopman/` → `shopman/shop/`, `project/` → `config/`
> - P0 Naming Plan: adapters e diretórios de templates renomeados para nomes canônicos
> - Análise crítica externa incorporada como novos pontos de verificação

## Resumo executivo

**Original (2026-04-11):** 13 achados: 2 críticos, 5 altos, 3 médios, 3 baixos.
**Status atual:** Todos corrigidos. Ver `docs/reports/drift_scan_2026-04-11.md` para detalhes das correções.
**Próximo scan:** Verificar contratos de adapters, escopo do `Shop`, e resíduos pós-P0.

---

## Achados conhecidos — todos corrigidos

### AUDIT-FIX-PLAN (sessões anteriores)

| WP | Status | Observação |
|----|--------|------------|
| AF-1 `notification.py` lê items de `order.data` | ✅ CORRIGIDO | `_build_context` agora lê `order.snapshot.get("items", [])` |
| AF-2 `get_transitions()` via ChannelConfig | ✅ CORRIGIDO | Campo `lifecycle` adicionado ao ChannelConfig; `commit.py` popula corretamente |
| AF-3 `ChannelConfig.Pipeline` + `on_payment_confirm` | ✅ CORRIGIDO | Pipeline removido, webhooks usam `on_paid` |
| AF-4 `required_checks_on_commit` → `ChannelConfig.rules.checks` | ✅ CORRIGIDO | `commit.py` usa `effective_config.get("rules", {}).get("checks", [])` |
| AF-5 `customer.py` discriminação por `channel_ref == "balcao"` | ✅ CORRIGIDO | Registry pattern implementado; sem `_handle_balcao` em services |
| AF-6 `STOREFRONT_CHANNEL_REF` hardcoded | ✅ CORRIGIDO | `constants.py` lê `getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")` |

**DRIFT-FIX-PLAN — todos corrigidos:**

| WP | Status | Evidência |
|----|--------|-----------|
| DF-1 Contrato adapters de pagamento (DTOs) | ✅ CORRIGIDO | `payment_types.py` com `PaymentIntent`/`PaymentResult`; três adapters retornam DTOs |
| DF-2 `_channel_config` helper + bypass de ChannelConfig | ✅ CORRIGIDO | `shopman/shop/lifecycle.py` usa `ChannelConfig.for_channel()`; zero `_channel_config` |
| DF-3 `_pop_matching_hold` / sangria de estoque | ✅ CORRIGIDO | `shopman/shop/services/stock.py` usa `_adopt_holds_for_qty` por quantidade |

---

### Achados do scan 2026-04-11

#### [CRÍTICO] AF-2 regrediu: `snapshot["lifecycle"]` sempre vazio — CORRIGIDO

**Arquivo:** `shopman/shop/services/commit.py` + `packages/orderman/shopman/orderman/models/order.py`
**Fix:** Campo `lifecycle: dict = field(default_factory=dict)` adicionado ao `ChannelConfig` em `shopman/shop/config.py`, com chaves `transitions` e `terminal_statuses`. `commit.py` agora popula o snapshot corretamente.

---

#### [CRÍTICO] POS bypassa ChannelConfig — CORRIGIDO

**Arquivo:** `shopman/shop/web/views/pos.py`
**Fix:** `channel_config=config.to_dict()` passado para `ModifyService` e `CommitService`, espelhando o padrão de `shopman/shop/web/views/checkout.py`.

---

#### [ALTO] URL paths com forma gerúndio — CORRIGIDO

**Arquivo:** `config/urls.py`
**Fix:** Renomeados para `api/orderman/`, `api/offerman/`, `api/stockman/`, `api/craftsman/`.

---

#### [ALTO] `"balcao"` hardcoded na view POS — CORRIGIDO

**Arquivo:** `shopman/shop/web/views/pos.py`, `shopman/shop/models/cash_register.py`
**Fix:** `POS_CHANNEL_REF` em `shopman/shop/web/constants.py` (override via `SHOPMAN_POS_CHANNEL_REF`).

---

#### [ALTO] Payment methods `"dinheiro"`/`"cartao"` não-canônicos — CORRIGIDO

**Arquivo:** `shopman/shop/web/views/pos.py`, `shopman/shop/services/payment.py`
**Fix:** `pos.py` usa `"counter"`/`"card"`. `payment.py` whitelist atualizada. `cash_register.py` filtra por `data__payment__method="counter"`.

---

#### [ALTO] `order.data["hold_ids"]` — schema documentado incorreto — CORRIGIDO

**Arquivo:** `docs/reference/data-schemas.md`
**Fix:** Tipo corrigido para `list[dict]` com schema `[{sku, hold_id, qty}]`.

---

#### [MÉDIO] Glossário: ChannelConfig com "6 aspectos" (são 8) — CORRIGIDO

**Arquivo:** `docs/reference/glossary.md`
**Fix:** Lista correta dos 8 aspectos: confirmation, payment, fulfillment, stock, notifications, pricing, editing, rules.

---

#### [MÉDIO] Chaves `stock_check_unavailable` e `manual_discount` não documentadas — CORRIGIDO

**Arquivos:** `shopman/shop/web/views/checkout.py`, `shopman/shop/web/views/pos.py`
**Fix:** Ambas adicionadas à tabela `Session.data` em `docs/reference/data-schemas.md`.

---

#### [MÉDIO] `customer_name` flat vs `customer.name` aninhado — CORRIGIDO

**Arquivos:** `shopman/shop/web/views/kds.py`, `shopman/shop/web/views/pedidos.py`
**Fix:** Agora usam `order.data.get("customer", {}).get("name", "")` (acesso canônico).

---

### P0 Naming Plan (2026-04-13→14) — todos corrigidos

| Item | Status | Detalhe |
|------|--------|---------|
| Template orderman admin — URLs `omniman_session_*` | ✅ CORRIGIDO | → `orderman_session_resolve_issue`, `orderman_session_run_check` |
| Admin `get_urls()` registrava como `ordering_session_*` | ✅ CORRIGIDO | → `orderman_session_run_check`, `orderman_session_resolve_issue` |
| `adapters/offering.py` (stockman) — era SKU validator | ✅ CORRIGIDO | → `packages/stockman/.../adapters/sku_validation.py` |
| `adapters/crafting.py` (stockman) — era ProductionBackend | ✅ CORRIGIDO | → `packages/stockman/.../adapters/production.py` |
| `adapters/stocking.py` (craftsman) — era StockingBackend | ✅ CORRIGIDO | → `packages/craftsman/.../adapters/stock.py` |
| `adapters/offering.py` (shopman/shop) — era StorefrontPricingBackend | ✅ CORRIGIDO | → `shopman/shop/adapters/pricing.py` |
| `templates/ordering/` (orderman) | ✅ CORRIGIDO | → `packages/orderman/.../templates/orderman/` |
| Test files `test_crafting_*.py`, `test_ordering_*.py` | ✅ CORRIGIDO | Renomeados para nomes canônicos (`test_production_*.py`, `test_session_*.py`) |
| SECRET_KEY strings `"offering"`, `"ordering"` + throttle keys em test_settings | ✅ CORRIGIDO | Strings limpas |

---

## Itens de baixa prioridade — monitorar

### [BAIXO] `delivery_method` — dois conceitos com o mesmo nome

**Arquivos:**
- `packages/doorman/shopman/doorman/models/verification_code.py` — canal OTP (whatsapp/sms/email)
- `packages/orderman/shopman/orderman/models/order.py` — fallback legacy para `fulfillment_type`
- `shopman/shop/web/views/auth.py` — parâmetro de POST

**Impacto:** Baixo (packages separados). Monitorar se os contextos se misturarem.

---

### [BAIXO] `customer_name` flat — verificar novos usos

Corrigido em views do framework. Verificar periodicamente se novo código usa o path flat ao invés de `order.data.get("customer", {}).get("name", "")`.

---

## Itens verificados sem achados (padrões a manter)

- **Frontend (HTMX/Alpine):** zero `onclick=`, `onchange=`, `document.getElementById` em templates ✓
- **Concorrência:** `select_for_update` aplicado corretamente em sequences, holds, fulfillment, orders ✓
- **Mocks em produção:** nenhum mock importado fora de `tests/`. `payment_mock.py` está em `adapters/` (correto) ✓
- **Handlers órfãos:** todos têm topics emitidos; nenhum dead handler ✓
- **Imports de `instances/` no framework:** zero ocorrências ✓
- **Referências Nelson hardcoded em `shopman/shop/`:** zero ocorrências ✓
- **Personas antigas em código não-import:** hits de `ordering` são todos `Meta.ordering` Django ✓

---

## Pontos a investigar no próximo scan

> Baseado em análise crítica externa (`docs/_inbox/analise_critica_django_shopman (1).md`)
> e estado pós-P0. A análise foi feita contra a estrutura `framework/shopman/` (pré-reestruturação);
> os caminhos canônicos atuais são `shopman/shop/`.

### [MÉDIO] Contratos de adapters: sem validação no carregamento

**Dimensão:** Contratos entre camadas
**Arquivo:** `shopman/shop/adapters/__init__.py`

**Contexto:** `get_adapter()` resolve por prioridade (DB → settings → defaults), mas não valida
protocolo no momento do carregamento — duck typing implícito. Se um adapter não implementa um
método obrigatório, a falha ocorre em runtime no ponto de uso, não no startup.

**O que verificar:**
- `get_adapter()`: há validação de contrato após resolução?
- `shopman/shop/protocols.py`: os protocolos são usados como contratos de verificação ou apenas como documentação?
- Existe algum `apps.py` check que valide adapters obrigatórios no startup?

---

### [MÉDIO] Modelo `Shop` com escopo largo

**Dimensão:** Separação de responsabilidades
**Arquivo:** `shopman/shop/models/shop.py`

**Contexto:** `Shop` acumula identidade, endereço, contato, operação, branding, redes sociais,
textos de tracking, defaults de negócio e integração de adapters — funciona como singleton de
configuração + entidade comercial + config-store + integration registry ao mesmo tempo.

**O que verificar:**
- Novos campos adicionados desde o último scan?
- `Shop.integrations` e `Shop.defaults` (JSONFields): schema documentado em `docs/reference/data-schemas.md`?
- Há alguma responsabilidade que já poderia ser extraída para um modelo auxiliar?

---

### [BAIXO] JSON sem schema enforcement na cascade de ChannelConfig

**Dimensão:** Robustez estrutural
**Arquivos:** `shopman/shop/config.py`, `shopman/shop/models/shop.py`,
`packages/orderman/shopman/orderman/models/channel.py`

**Contexto:** A cascade (`Shop.defaults` → `Channel.config` → ChannelConfig defaults) depende de
disciplina humana para manter os JSONs coerentes. Chaves inválidas ou tipos errados falham silenciosamente.

**O que verificar:**
- `ChannelConfig.for_channel()`: o que acontece com chaves inválidas em `Channel.config`?
- Há algum `clean()` ou `full_clean()` no model que valide o schema do JSONField?
- Existe um exemplo de teste que force um `Channel.config` inválido e verifique o comportamento?

---

### [BAIXO] Resíduos pós-P0 — verificação de naming drift

**Dimensão:** Nomenclatura

**O que verificar (grep em código de produção, excluindo `_archive/`, `_quarantine/`, test_settings):**
```
grep -r "ordering\|offering\|stocking\|crafting\|omniman" shopman/ packages/ config/ \
  --include="*.py" \
  | grep -v "Meta\.ordering\|test_settings\|_archive\|_quarantine"
```
Zero ocorrências esperadas. Exceção legítima: `Meta.ordering` Django (forma gerúndio de ORM).

---

## Lint — referência pós-fix (production, não-test)

Após correção via `ruff --fix` no scan de 2026-04-11. Reexecutar `make lint` para verificar estado atual:

```bash
make lint
```

Arquivos que tinham erros na última auditoria (verificar se ainda limpos):
- `shopman/shop/models/cash_register.py`
- `shopman/shop/web/views/catalog.py`
- `shopman/shop/web/views/pos.py`
- `shopman/shop/templatetags/storefront_tags.py`
- `shopman/shop/services/fiscal.py`
- `shopman/shop/management/commands/suggest_production.py`
- `packages/craftsman/shopman/craftsman/contrib/admin_unfold/__init__.py`
- `packages/doorman/shopman/doorman/senders.py`
- `packages/guestman/shopman/guestman/api/views.py`

---

## Referências

- `docs/reference/data-schemas.md` — inventário de chaves em Session.data, Order.data, Directive.payload
- `docs/reference/protocols.md` — contratos de adapters (regenerado 2026-04-14 a partir do código)
- `docs/reference/glossary.md` — glossário de termos canônicos (8 aspectos do ChannelConfig)
- `docs/guides/lifecycle.md` — arquitetura de lifecycle/dispatch (config-driven, sem classes de Flow)
- `docs/_inbox/analise_critica_django_shopman (1).md` — análise crítica externa (2026-04-11): referências a `framework/shopman/` são pré-reestruturação, equivalentes atuais em `shopman/shop/`
- `docs/reports/drift_scan_2026-04-11.md` — detalhes das correções aplicadas no scan original
