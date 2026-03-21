# Plano de Refatoração — Django Shopman

> Este arquivo é a fonte de verdade para a refatoração.
> Vive no repo. Cada conversa nova DEVE lê-lo antes de agir.

## Origem e Destino

- **Origem** (read-only): `/Users/pablovalentini/Dev/Claude/django-shopman-suite/`
- **Destino** (projeto novo): `/Users/pablovalentini/Dev/Claude/django-shopman/`

## Estado Atual (2026-03-21)

### Testes passando agora: 1.766

| App | Testes | Status |
|-----|--------|--------|
| shopman.utils (ex-commons) | 67 | Migrado |
| shopman.offering (ex-offerman) | 180 | Migrado |
| shopman.stocking (ex-stockman) | 157+1s | Migrado |
| shopman.crafting (ex-craftsman) | 205 | Migrado |
| shopman.ordering (ex-omniman kernel) | 216 | **Migrado** |
| shopman.attending (ex-guestman) | 369 | **Migrado** |
| shopman.gating (ex-doorman) | 152 | **Migrado** |
| shopman (orquestrador) | 420 | **Migrado** (confirmation, stock, pricing, customer, payment, notifications, fiscal, accounting, returns, webhook) |
| Integration / Nelson | 0 | **Não migrado** |
| **Total** | **1.766** | **Target: ~1.649** |

### O que foi feito (WP-0 a WP-5 originais)

- [x] WP-0: Scaffold + shopman.utils
- [x] WP-1: shopman.offering
- [x] WP-2: shopman.stocking
- [x] WP-3: shopman.crafting (com sub-WPs 3.1-3.4 de renaming)
- [ ] ~~WP-4: attending + gating~~ — FOI PULADO, virou "shopman-app básico"
- [x] WP-5: shopman.ordering kernel (parcial)
- [x] WP-R1: completar ordering kernel + fix Makefile (216 testes, make test 5 apps)
- [x] WP-R2: shopman.attending + shopman.gating (369 + 152 testes, make test 7 apps)
- [x] WP-R3: orquestração — confirmation, stock, pricing, customer (154 testes, make test 8 apps)
- [x] WP-R4: orquestração — payment, notifications, fiscal, accounting, returns, webhook (420 testes, make test 8 apps)

### O que DESVIOU do plano (WP-6 em diante)

A partir do WP-6, Claude desviou do plano original e começou a inventar features:
- WP-6 a WP-9: parcialmente corretos (presets, config, stock handler, notification handler)
- **WP-10 a WP-14: features inventadas** (post_commit_directives, dispatch command, abandon())
- WP-15+: mais features inventadas (SessionReadService, etc.)

Esses WPs inventados adicionaram arquivos ao ordering que foram **removidos no WP-R1**:
- `services/directive.py` — REMOVIDO
- `management/commands/dispatch_directives.py` — REMOVIDO (substituído por process_directives.py original)
- `CommitService.abandon()` — REMOVIDO (não existe no original)
- `dispatch.py` e `commit.py` — SUBSTITUÍDOS pelo conteúdo original

### Gaps no ordering kernel (vs omniman original) — RESOLVIDO em WP-R1

Todos os arquivos kernel foram migrados. Arquivos que NÃO estão no kernel (correto):

| Arquivo | Motivo |
|---------|--------|
| `channel_config.py` | Movido para shopman-app (correto) |
| `channel_presets.py` | Movido para shopman-app (correto) |
| `monetary.py` | Movido para shopman.utils (correto) |
| `contrib/` (exceto refs/) | Será migrado em WP-R3/R4 |
| `management/commands/seed_rich_demo.py` | Demo only, não kernel |
| `management/commands/simulate_shop_order.py` | Demo only, não kernel |
| `management/commands/fix_channel_post_commit_directives.py` | Migration helper, não kernel |

**Testes do kernel**: 216 (kernel + contrib/refs). Testes de contrib (stock, payment, notification, etc.) serão migrados nos WP-R3/R4.

### Gaps na orquestração (shopman-app)

| Módulo | Original (omniman/contrib/) | Migrado? |
|--------|---------------------------|----------|
| confirmation/ | 4 files | **Migrado** (WP-R3) |
| stock/ | 5 files | **Migrado** (WP-R3) |
| pricing/ | 3 files | **Migrado** (WP-R3) |
| payment/ | 5 files | **Migrado** (WP-R4) |
| customer/ | 4 files | **Migrado** (WP-R3) |
| notifications/ | 4 files | **Migrado** (WP-R4) |
| fiscal/ | 2 files | **Migrado** (WP-R4) |
| accounting/ | 2 files | **Migrado** (WP-R4) |
| returns/ | 3 files | **Migrado** (WP-R4) |
| webhook/ | 5 files | **Migrado** (WP-R4) |

### Makefile — ATUALIZADO em WP-R4

`make test` roda todos os 8 apps: utils, offering, stocking, crafting, ordering, attending, gating, shopman-app (1.766 testes).

---

## WPs Restantes (corrigidos)

### WP-R1: Completar ordering kernel + corrigir Makefile
**Escopo**: shopman-core/ordering/

1. Copiar do omniman os arquivos faltantes:
   - `admin.py`, `admin_widgets.py`, `unfold.py`
   - `protocols.py`, `holds.py`, `context_processors.py`
   - `api/` (diretório completo)
   - `templates/`, `templatetags/`
   - `contrib/refs/` (é kernel)
2. Adaptar imports: `omniman` → `shopman.ordering`, `commons` → `shopman.utils`
3. Migrar testes faltantes do omniman/tests/ (excluir testes de contribs)
4. Corrigir Makefile: adicionar test-offering, test-stocking, test-crafting
5. Target: ordering passa ~630 testes (kernel), make test roda TUDO

**Verificação**: `make test` roda 5 apps, ~1.200+ testes

### WP-R2: shopman.attending + shopman.gating (ex-guestman + doorman)
**Escopo**: shopman-core/attending/ e shopman-core/gating/

1. Copiar `guestman/guestman/` → `shopman-core/attending/shopman/attending/`
2. Copiar `doorman/doorman/` → `shopman-core/gating/shopman/gating/`
3. Renomear: app_label="attending", app_label="gating"
4. Replace imports cruzados (adapters bidirecionais)
5. Migrations zeradas
6. Adaptar testes de ambos
7. Adicionar ao Makefile

**Target**: attending ~251 testes + gating ~152 testes
**Verificação**: `make test` → ~1.600+ testes

### WP-R3: Orquestração — confirmation, stock, pricing, customer
**Escopo**: shopman-app/shopman/

1. Reestruturar: mover `contrib/` para sub-módulos próprios
2. Copiar do omniman/contrib/:
   - `confirmation/` → `shopman/confirmation/`
   - `stock/` → `shopman/stock/` (completar o que falta)
   - `pricing/` → `shopman/pricing/`
   - `customer/` → `shopman/customer/`
3. Cada sub-módulo com apps.py que registra handlers
4. Adaptar imports
5. Adaptar testes

**Verificação**: testes de orquestração passam

### WP-R4: Orquestração — payment, notifications, fiscal, accounting, returns, webhook
**Escopo**: shopman-app/shopman/

1. Copiar do omniman/contrib/:
   - `payment/` → `shopman/payment/`
   - `notifications/` → `shopman/notifications/` (completar)
   - `fiscal/` → `shopman/fiscal/`
   - `accounting/` → `shopman/accounting/`
   - `returns/` → `shopman/returns/`
   - `webhook/` → `shopman/webhook/`
2. Adaptar imports e testes

**Verificação**: testes passam

### WP-R5: Integration tests + Nelson + Finalização
**Escopo**: shopman-app/

1. Copiar `tests/integration/` do suite (conftest + 8 test files)
2. Copiar `shopman-nelson/` → `shopman-app/nelson/`
3. Adaptar imports em tudo
4. INSTALLED_APPS completo no settings.py
5. Makefile final com todos os targets
6. Rodar TODOS os testes

**Target final**: ~1.649 testes passando
**Verificação**: `make test` — tudo verde

---

## Grafo de Dependências (WPs restantes)

```
WP-R1 (completar ordering + fix Makefile)
  │
  ├──► WP-R2 (attending + gating)
  │
  ├──► WP-R3 (confirmation, stock, pricing, customer)
  │
  └──► WP-R4 (payment, notif, fiscal, etc.)
         │
WP-R1..R4 ──► WP-R5 (integration, nelson, finalização)
```

## Regras (repetir em cada prompt)

1. Não tocar no `django-shopman-suite/` original (read-only)
2. Ler REFACTOR-PLAN.md no início de cada conversa
3. Não inventar features novas — só migrar código existente
4. Testes existentes devem continuar passando
5. Migrations zeradas (software novo)
6. Ao final, mostrar o prompt do próximo WP
