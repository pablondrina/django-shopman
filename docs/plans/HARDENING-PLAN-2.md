# HARDENING-PLAN-2 — Fechamento de contrato spec↔código

> Plano de ação derivado do Relatório Final da Suíte (2026-04-18).
> 94 achados nos 11 relatórios → verificados contra código atual → 46 confirmados, 20 alarmes falsos,
> 15 já resolvidos pelos WP-GAPs, 13 design debt a documentar.
> Organizado em 9 WPs paralelizáveis por pacote.

Data: 2026-04-18
Baseline: commit após merge de todos os 14 WP-GAPs.

---

## Metodologia de triagem

Cada achado do relatório foi verificado contra o código atual por agentes que leram os arquivos,
entenderam as decisões de design (CLAUDE.md, ADRs), e classificaram:

- **VALID BUG** — quebra em runtime, precisa fix
- **VALID DRIFT** — funciona mas contrato diverge da implementação
- **FALSE ALARM** — analista não entendeu o design; intencional ou já tratado
- **DESIGN DEBT** — simplificação deliberada a documentar (não é bug)

---

## Alarmes falsos descartados (20)

| Pacote | Achado | Motivo de descarte |
|--------|--------|-------------------|
| ORDERMAN | channel_config SimpleNamespace no registry | É stub de `channel`, não `channel_config` — args separados |
| ORDERMAN | Unique (channel_ref, session_key) em Order | Intencional — Session tem o constraint; Order é 1:1 via CommitService |
| ORDERMAN | OrderEvent.seq sem DB constraint | select_for_update + UniqueConstraint(order,seq) já garante |
| DOORMAN | verify_for_login importa guestman | Import dentro de try/except, fail gracioso — coupling opcional |
| DOORMAN | VerificationCodeVerifyView cria AccessLink sintético | Source.INTERNAL existe exatamente para isso — reuso legítimo |
| DOORMAN | DoormanConfig.ready() não valida classes | Validação é lazy via import_string() — intencional |
| DOORMAN | AccessLink 60s reuse window | Comentário explícito: "para lidar com prefetch de navegadores" |
| DOORMAN | _user_bridge concurrent User creation | IntegrityError + retry + savepoint — handled |
| DOORMAN | code_hash default API confusa | Default é defensivo; flows reais passam hash explícito |
| GUESTMAN | Customer.save() não promove ContactPoint | _sync_contact_points() faz exatamente isso |
| GUESTMAN | suggest_address() swallows exceptions | Intencional e documentado no código |
| OFFERMAN | ListingViewSet.items() sem filtro published | Aplica ListingItemFilter — funciona |
| OFFERMAN | unit_price() fallback silencioso | Contrato documentado: base_price como fallback |
| OFFERMAN | get_descendants sem depth limit | Respeita MAX_COLLECTION_DEPTH |
| SHOP | craftsman.contrib import deep coupling | Guardado por try/except ImportError — opcional |
| SHOP | Channel.kind stored mas unused | Usado em admin Unfold para ícone sidebar |
| NELSON | Seed password 'admin' default | Seed de dev; env var ADMIN_PASSWORD disponível |
| NELSON | Seed não-determinístico | Deliberado para dados de demo realistas |
| STOCKMAN | shelf_life_days mismatch | Código usa getattr(product, "shelf_life_days", None) consistentemente |
| UTILS | table_admin_link broken URL | Código atual implementa corretamente |

---

## Design debt a documentar (13)

Itens que não são bugs mas merecem ADR ou documentação:

| Pacote | Item | Ação |
|--------|------|------|
| DOORMAN | Sem select_for_update em verify/exchange | Documentar que concorrência é aceita no scale atual |
| DOORMAN | Rate limit check-then-act sem lock | Documentar trade-off; considerar Redis quando escalar |
| DOORMAN | Error codes não surfaced nas views | Documentar; API v2 pode incluir |
| ORDERMAN | set_data whitelist só no serializer | Documentar: serializer é trust boundary; ModifyService é internal API |
| ORDERMAN | contrib/refs target_id UUID vs Session int PK | Contrib dormant; documentar incompatibilidade |
| ORDERMAN | CommitService não chama on_session_committed | Hook órfão; documentar ou remover |
| SHOP | ChannelConfig.validate() shallow | Documentar que validação é by-construction |
| SHOP | Shop.defaults/integrations sem schema formal | Deliberado por CLAUDE.md §Core; documentar shapes em data-schemas.md |
| UTILS | DashboardTable sem validação de cell count | Thin builder; documentar uso correto |
| UTILS | format_quantity annotation sem None | Fix annotation |
| NELSON | Seed non-deterministic | Deliberado; documentar para quem espera idempotência |
| STOCKMAN | Hold sem audit trail (actor) | Simplificação para v1; documentar |
| STOCKMAN | Hold não split entre quants | Deliberado; documentar limitação |

---

## HP2-01 — Orderman: API + admin fixes

**Confirmados: 2 bugs + 1 drift**

| # | Sev | Achado | Verificação |
|---|-----|--------|-------------|
| 1 | P0 | Admin usa `session.channel.ref` mas Session só tem `channel_ref` CharField. AttributeError em 4 locations. | VALID BUG — `admin.py` lines 412, 454, 506, 535 |
| 2 | P1 | `OrderViewSet` sem `lookup_field = "ref"` — usa PK default. | DESIGN DEBT — funciona mas inconsistente com convenção ref-first |

**Entregáveis:**
- Fix admin: `session.channel.ref` → `session.channel_ref` (4 locais)
- Avaliar `lookup_field = "ref"` no ViewSet
- Testes

---

## HP2-02 — Doorman: template + error semantics ✅ CONCLUÍDO

**Confirmados: 1 bug + 2 drifts** — todos resolvidos em HP2-02.

| # | Sev | Achado | Resolução |
|---|-----|--------|-----------|
| 1 | P0 | Template `access_link_invalid.html` usava `doorman:code-request` mas app_name era antigo. NoReverseMatch em runtime. | `app_name` renomeado para `doorman`. Todos os db_table, related_name e cookie também renomeados. |
| 2 | P1 | `exchange()` mapeava todos GateError para TOKEN_EXPIRED. TOKEN_USED nunca retornado. | Mapeamento semântico: used→TOKEN_USED, expired→TOKEN_EXPIRED, resto→TOKEN_INVALID. |
| 3 | P1 | `send_access_link()` aceitava `sender` param mas nunca usava. | Param removido de `send_access_link()` e `_send_access_link_email()`. |

**Entregáveis:**
- Rename completo: `app_name`, db_table, related_name, cookie name (`doorman_dt`)
- `exchange()`: mapeamento semântico de GateError para error codes corretos
- `send_access_link()`: param `sender` removido
- Migrações regeneradas do zero (banco pode ser zerado)

---

## HP2-03 — Guestman: merge admin + sync + insights

**Confirmados: 3 bugs + 4 drifts + 3 polish**

| # | Sev | Achado | Verificação |
|---|-----|--------|-------------|
| 1 | P0 | Merge admin URL `customers_customer_merge` vs `guestman_customer_merge` — 404 | VALID BUG |
| 2 | P0 | Merge template path errado — TemplateDoesNotExist | VALID BUG |
| 3 | P0 | `sync_subscriber()` sem `transaction.atomic()` — orphaned Customer possível | VALID BUG |
| 4 | P1 | `InsightService.recalculate()` nunca escreve `favorite_products` | VALID DRIFT |
| 5 | P1 | `ContactPoint.mark_verified()` aceita qualquer string | VALID DRIFT |
| 6 | P1 | `CustomerViewSet` missing `filter_backends` | VALID DRIFT |
| 7 | P1 | `favorite_products` sem writer (mesmo que achado 4, confirmado) | VALID DRIFT |
| 8 | P2 | `customer_type_badge` usa "company" em vez de "business" | VALID BUG (badge sempre defaults) |
| 9 | P2 | `export_selected_csv` Content-Disposition malformed | VALID BUG |
| 10 | P2 | `CustomerGroup` default group race condition | VALID DRIFT |

**Entregáveis:**
- Fix merge admin: URL name + template path
- `transaction.atomic()` em `sync_subscriber()`
- `favorite_products`: implementar writer ou remover campo
- `mark_verified()`: enum de métodos válidos
- `CustomerViewSet.filter_backends` explícito
- Fix badge enum + CSV header
- CustomerGroup: atomic select_for_update para default
- Testes

---

## HP2-04 — Offerman: pricing + projeção

**Confirmados: 1 bug + 5 drifts + 2 polish**

| # | Sev | Achado | Verificação |
|---|-----|--------|-------------|
| 1 | P0 | Admin `if not instance.price_q:` trata 0 como falsy — zero-price items quebram | VALID BUG — ambos admin files |
| 2 | P1 | `get_projection_items()` pega wholesale tier em vez de base | VALID DRIFT |
| 3 | P1 | `retract()` não pega SKUs removidos do listing | VALID DRIFT |
| 4 | P1 | Temporal validity não filtrada em API routes | VALID DRIFT |
| 5 | P1 | `ProductInfo` DTO falta `image_url` e outros | VALID DRIFT |
| 6 | P1 | `category` inconsistente entre adapters (ref vs name) | VALID DRIFT |
| 7 | P2 | `expand_bundle` swallows CatalogError | VALID DRIFT |
| 8 | P2 | `is_bundle` N+1 em list views | VALID DRIFT |

**Entregáveis:**
- Fix admin: `if instance.price_q is None:` (not falsy check)
- `get_projection_items()`: ordenar `min_qty ASC` para base tier
- `retract()`: diff de snapshots para retrair SKUs removidos
- Temporal validity filter em API querysets
- Enriquecer ProductInfo DTO
- Padronizar category → `collection.ref`
- Logging em expand_bundle failure
- is_bundle annotation em queryset
- Testes

---

## HP2-05 — Stockman: BatchQuerySet + disponibilidade

**Confirmados: 2 bugs + 5 drifts**

| # | Sev | Achado | Verificação |
|---|-----|--------|-------------|
| 1 | P0 | `BatchQuerySet.active()` usa `quants___quantity__gt=0` mas Batch→Quant não tem FK. FieldError em runtime. | VALID BUG |
| 2 | P0 | `StockQueries.available()` não filtra batches expirados — diverge de `availability_for_sku()` | VALID BUG |
| 3 | P1 | `test_quantity_invariant.py` chama `confirm_hold/fulfill_hold/release_hold` — não existem | VALID BUG (testes skipped em SQLite, crash em Postgres) |
| 4 | P1 | `availability_scope_for_channel()` sempre retorna safety_margin=0 | VALID DRIFT — feature declarada não implementada |
| 5 | P1 | `replan()` lookup ambíguo em multi-position | VALID DRIFT |
| 6 | P1 | `IssueView` lookup ambíguo (sem target_date/batch) | VALID DRIFT |
| 7 | P2 | Move QuerySet.update sem guard (Quant tem via WP-08) | VALID DRIFT |

**Entregáveis:**
- Fix BatchQuerySet.active() — usar annotation ou filter correto
- Alinhar StockQueries.available() com availability_for_sku()
- Fix test method names: confirm_hold→confirm, fulfill_hold→fulfill, release_hold→release
- Implementar ou remover availability_scope_for_channel (ADR)
- replan/IssueView: lookup com position + batch
- MoveQuerySet.update guard (pattern WP-08)
- Testes

---

## HP2-06 — Payman: intents expirados + gateway_id

**Confirmados: 2 drifts + 2 polish (maioria é design debt)**

| # | Sev | Achado | Verificação |
|---|-----|--------|-------------|
| 1 | P1 | `get_active_intent()` não exclui intents expirados | VALID DRIFT |
| 2 | P1 | `gateway_id` sem unique index — reconciliação unreliable | VALID DRIFT |
| 3 | P2 | Move/PaymentTransaction QuerySet.update bypass imutabilidade | VALID DRIFT |
| 4 | P2 | `cancel()` reason não persistido | VALID DRIFT |

Nota: Muitos achados do relatório original (PaymentIntent.save() terminal status, PaymentBackend protocol, authorize→CaptureResult, chargeback dangling, API scope) foram verificados como **design debt ou false alarm** — PaymentIntent.save() já tem state machine enforced, PaymentBackend é forward-looking, chargeback é placeholder futuro.

**Entregáveis:**
- `get_active_intent()`: filtrar `expires_at__gt=now()` ou `expires_at__isnull=True`
- Unique index `(gateway, gateway_id)` onde gateway_id not null
- PaymentTransaction QuerySet.update guard
- `cancel_reason` field ou structured log
- Testes

---

## HP2-07 — Nelson: seed narrative + imports

**Confirmados: 1 bug + 3 drifts**

| # | Sev | Achado | Verificação |
|---|-----|--------|-------------|
| 1 | P1 | Seed reporta "7 coleções" mas cria 9 | VALID BUG |
| 2 | P1 | customer_strategies importa helpers privados `_*` | VALID DRIFT |
| 3 | P2 | iFood 30% markup com pricing.policy="external" | VALID DRIFT — conceptual inconsistency |
| 4 | P3 | `default_app_config` deprecated | VALID DRIFT — dead code |

**Entregáveis:**
- Fix seed log: "7 colecoes" → "9 colecoes"
- customer_strategies: mover helpers usados para API pública ou usar service methods
- Documentar ou remover iFood markup inconsistência
- Remover default_app_config
- Testes

---

## HP2-08 — Shop: tracking duplication

**Confirmados: 1 drift**

| # | Sev | Achado | Verificação |
|---|-----|--------|-------------|
| 1 | P2 | Tracking duplicado entre view e projection (constantes idênticas em dois módulos) | VALID DRIFT — projection é canonical mas view não consome |

**Entregáveis:**
- View tracking: delegar 100% à projection (remover constantes duplicadas)
- Testes

---

## HP2-09 — Utils: imports + docstrings

**Confirmados: 1 bug + 4 drifts**

| # | Sev | Achado | Verificação |
|---|-----|--------|-------------|
| 1 | P1 | `admin_unfold/base.py` top-level `unfold` import sem guard — ImportError se não instalado | VALID BUG |
| 2 | P2 | EnrichedAutocomplete quebra com proxy models | VALID DRIFT |
| 3 | P2 | `is_valid_phone()` docstring incorreta | VALID DRIFT |
| 4 | P2 | `_fallback_normalize()` ignora default_region, hardcoda BR | VALID DRIFT |
| 5 | P2 | `format_quantity()` annotation sem None | VALID DRIFT |

**Entregáveis:**
- Lazy import de unfold com try/except
- Autocomplete: handle proxy models
- Fix docstrings e annotations
- _fallback_normalize: respeitar default_region
- Testes

---

## Resumo filtrado

| WP | Pacote | Bugs | Drifts | Total confirmado | Paralelo? |
|----|--------|------|--------|------------------|-----------|
| HP2-01 | Orderman | 1 | 1 | 2 | ✅ |
| HP2-02 | Doorman | 1 | 2 | 3 | ✅ |
| HP2-03 | Guestman | 5 | 5 | 10 | ✅ |
| HP2-04 | Offerman | 1 | 7 | 8 | ✅ |
| HP2-05 | Stockman | 3 | 4 | 7 | ✅ |
| HP2-06 | Payman | 0 | 4 | 4 | ✅ |
| HP2-07 | Nelson | 1 | 3 | 4 | ✅ |
| HP2-08 | Shop | 0 | 1 | 1 | ✅ |
| HP2-09 | Utils | 1 | 4 | 5 | ✅ |
| **Total** | | **13** | **31** | **44** | |

De 94 achados originais → **44 confirmados** (13 bugs + 31 drifts), **20 alarmes falsos**, **13 design debt**, **15 já resolvidos**, **2 duplicatas**.

**Ordem de execução por impacto:**
1. HP2-05 (Stockman) — 3 bugs runtime, BatchQuerySet broken
2. HP2-03 (Guestman) — 5 bugs, merge admin + sync
3. HP2-04 (Offerman) — zero-price bug + 7 drifts pricing
4. HP2-02 (Doorman) — template crash + error semantics
5. HP2-01 (Orderman) — admin crash
6. HP2-06 (Payman) — expired intents
7. HP2-09 (Utils) — import guard
8. HP2-07 (Nelson) — seed narrative
9. HP2-08 (Shop) — tracking dedup

Todos paralelizáveis — cada WP opera em pacote independente.

---

## Referências

- [docs/reports/relatorio_final_suite_shopman_2026-04-18.md](../reports/relatorio_final_suite_shopman_2026-04-18.md)
- 11 relatórios por pacote em `docs/reports/`
- WP-GAPs 01-15 completados — baseline atual
- Verificação por agentes contra código real (2026-04-18)
