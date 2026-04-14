# P0 — Plano de Execução: Naming Canônico & Limpeza de Resíduos

**Status:** Em execução
**Data:** 2026-04-13
**Base:** REFATOR_SPEC + Constituição Semântica + Auditoria completa

---

## Contexto

Auditoria completa realizada em 2026-04-13 revelou que a migração Omniman → packages individuais
está **substancialmente completa**, mas há resíduos pontuais que violam a política de legado zero.

## Achados da Auditoria

### Crítico (funcional — pode quebrar em runtime)

| # | Arquivo | Problema |
|---|---------|----------|
| 1 | `packages/orderman/.../templates/ordering/admin/session_change_form.html:19,37` | URLs referem `admin:omniman_session_*` — nome inexistente |
| 2 | `packages/orderman/.../admin.py:395,400` | `get_urls()` registra como `ordering_session_*` — deveria ser `orderman_session_*` |

### Cosmético (naming drift — não quebra, mas viola legado zero)

| # | Local | Problema | Ação |
|---|-------|----------|------|
| 3 | `packages/stockman/.../adapters/offering.py` | Filename "offering" — conteúdo é SkuValidator loader | Renomear → `sku_validation.py` |
| 4 | `packages/stockman/.../adapters/crafting.py` | Filename "crafting" — conteúdo é ProductionBackend | Renomear → `production.py` |
| 5 | `packages/craftsman/.../adapters/stocking.py` | Filename "stocking" — conteúdo é StockingBackend | Renomear → `stock.py` |
| 6 | `framework/shopman/adapters/offering.py` | Filename "offering" — conteúdo é StorefrontPricingBackend | Renomear → `pricing.py` |
| 7 | `packages/orderman/.../templates/ordering/` | Diretório "ordering" | Renomear → `orderman/` |
| 8 | `framework/.../tests/integration/test_crafting_offering.py` | Filename legacy | Renomear → `test_production_catalog.py` |
| 9 | `framework/.../tests/integration/test_ordering_auth.py` | Filename legacy | Renomear → `test_session_auth.py` |
| 10 | `framework/.../tests/integration/test_ordering_attending.py` | Filename legacy | Renomear → `test_session_attending.py` |
| 11 | `framework/.../tests/integration/test_crafting_stocking.py` | Filename legacy | Renomear → `test_production_stock.py` |
| 12 | `framework/.../tests/integration/test_crafting_app_integration.py` | Filename legacy | Renomear → `test_production_app_integration.py` |
| 13 | `packages/offerman/offerman_test_settings.py:7` | SECRET_KEY string "offering" | Limpar |
| 14 | `packages/orderman/orderman_test_settings.py:7,32,41-42` | SECRET_KEY "ordering", throttle keys `ordering_*` | Limpar |

### Limpo (confirmado pela auditoria)

- Todos os `apps.py` labels: canônicos ✓
- Todos os `pyproject.toml` metadata: canônicos ✓
- Todos os imports cross-package no framework: usam nomes novos ✓
- `protocols.py`, `lifecycle.py`, `config.py`: zero resíduos ✓
- Zero referências a "omniman" fora do template acima ✓
- Zero referências a "guesting" ✓

## Plano de Execução

### Fase 1 — Fixes críticos (runtime)

1. **Template orderman admin** — corrigir URLs:
   - `omniman_session_resolve_issue` → `orderman_session_resolve_issue`
   - `omniman_session_run_check` → `orderman_session_run_check`

2. **Admin get_urls()** — corrigir nomes registrados:
   - `ordering_session_resolve_issue` → `orderman_session_resolve_issue`
   - `ordering_session_run_check` → `orderman_session_run_check`

### Fase 2 — Renames de arquivos + diretórios

3. Renomear adapter files (atualizar imports em todo o projeto)
4. Renomear diretório `templates/ordering/` → `templates/orderman/`
5. Renomear test files de integração

### Fase 3 — Limpeza de strings

6. Corrigir SECRET_KEY strings e throttle keys nos test_settings

### Fase 4 — Verificação

7. `make test` — zero breakage
8. `make lint` — zero warnings
