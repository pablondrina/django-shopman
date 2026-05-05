# Shopman — Spec-Driven Specification (v1.0, 2026-04-18)

> Documento de engenharia reversa do Django Shopman, extraído com fidelidade para que outro agente consiga reproduzir o sistema sem equívoco. Estrutura: Meta → Pacotes → Orquestrador → Instância → E2E por POV → Transversais → Invariantes → Checklist de fidelidade.

---

## 0. META

### 0.1 Vocabulário canônico

- **Shopman Suite**: projeto inteiro (9 pacotes Core + Orquestrador + instâncias).
- **Shopman** (sem qualificador): a camada orquestradora (`shopman/shop/`, `app_label="shop"`).
- **Core / packages**: 9 pacotes pip-instaláveis em `packages/*` — sem dependência cruzada entre si.
- **Instância**: aplicação Django concreta em `instances/*` (Nelson Boulangerie é a referência).
- **Persona naming** (obrigatório): Offerman, Stockman, Craftsman, Orderman, Guestman, Doorman, Payman. Nunca "Offering", "Stocking", "Ordering".
- **Namespace**: `shopman.*` via PEP 420 (sem `__init__.py` em `shopman/` raiz).

### 0.2 Visão em três frases

1. **Core é domínio puro**: 9 pacotes ortogonais, pip-instaláveis, independentes entre si, cada um resolvendo de forma excelente um subdomínio de comércio (refs, catálogo, estoque, produção, pedidos, clientes, auth, pagamento, utilitários).
2. **Orquestrador é coordenação, não lógica**: `shopman/shop/` conecta os Core via Lifecycle config-driven (`ChannelConfig` + `dispatch()`), Adapters plugáveis, Rules engine DB-driven, Handlers/Directives assíncronos e UIs (Storefront, Pedidos, KDS, POS, Admin).
3. **Instância é configuração**: `instances/nelson/` é uma aplicação que compõe Core + Orquestrador com seed, branding e estratégias próprias; nunca contamina Core; sempre sobrescreve via padrões bem-definidos.

### 0.3 Princípios arquiteturais (traduzidos em decisões de código)

| # | Princípio | Consequência de código |
|---|-----------|------------------------|
| P1 | Core é sagrado | `Session.data`, `Order.data`, `Directive.payload`, `Channel.config` são `JSONField` — extensíveis sem migração; chaves catalogadas em `docs/reference/data-schemas.md`. |
| P2 | Config-driven, não OOP-driven | Sem classes de lifecycle. Lifecycle é despachado por `ChannelConfig` (8 aspectos) + `dispatch(order, phase)`. |
| P3 | Identificadores textuais como `ref` | Exceção deliberada: `Product.sku` (campo SKU de produto). `WorkOrder.ref` é sequencial (`WO-YYYY-NNNNN`). |
| P4 | Monetário inteiro em centavos com sufixo `_q` | `price_q=1500` ⇒ R$ 15,00. `monetary_mult`/`monetary_div` são canônicos (`ROUND_HALF_UP`). |
| P5 | Directives em vez de Celery | Tabela `Directive` + dispatch via signal post-commit + backoff `2^attempts` + max 5. Idempotente via `dedupe_key`. |
| P6 | Zero resíduos em renames | Sem aliases `OldName = NewName`, sem `# formerly X`. |
| P7 | Offerman ≠ insumos | Apenas produtos vendáveis (`is_sellable`). Insumos vivem em Stockman/Craftsman. |
| P8 | HTMX ↔ servidor, Alpine ↔ DOM | Jamais `onclick`, `document.getElementById`, `classList.toggle`. |
| P9 | Omotenashi e acessibilidade first-class | Não é afterthought: 3 portões (antecipar / estar presente / ressoar) + 5 testes (invisível / antecipação / ma / calor / retorno). |
| P10 | Timeouts transparentes | Todo TTL que afeta o cliente tem UI explícita + notificação ativa. |
| P11 | Confirmação otimista | Operador tem prazo para cancelar; default é confirmar. |
| P12 | Zero backward-compat aliases | Projeto novo, sem consumidor externo legado. |

---

## 1. PACOTES (CORE)

Cada pacote abaixo é pip-instalável (`shopman-<nome>`), vive em `packages/<nome>/shopman/<nome>/`, tem `admin_unfold/` opcional em `contrib/`, e expõe serviço(s), modelos, signals, protocols e testes.

### 1.1 utils (`shopman-utils`, ~0.3)

**Escopo**: primitivas puras sem modelos de domínio.

**API pública**
- `shopman.utils.monetary`: `monetary_mult(qty: Decimal, unit_price_q: int) → int`, `monetary_div(total_q, divisor) → int`, `format_money(value_q) → "12,50"`. `ROUND_HALF_UP`, nunca banker's. Divisor ≤ 0 levanta `ValueError`.
- `shopman.utils.phone`: `normalize_phone(value, default_region="BR", contact_type=None) → E.164 str` (trata DDD sem código de país 55, bug de Manychat `+DDD9XXXXXXXX` 11 dígitos, email passa lowercased, Instagram handle sem `@`, inválido ⇒ `""`); `is_valid_phone()`.
- `shopman.utils.formatting.format_quantity(value, decimal_places=2) → "10.50"`.
- `shopman.utils.admin.mixins.AutofillInlineMixin`: injeta JS Select2-cache para autopreencher campos em `TabularInline` via `autofill_fields = {source: {target: json_key}}`.
- `shopman.utils.exceptions.BaseError`: base para erros de todos os pacotes (`code`, `message`, `data`).

**Invariantes**
- Toda aritmética monetária passa por `monetary_*`. Nunca `Decimal * Decimal` direto.
- Todo telefone passa por `normalize_phone()` antes de persistir. Manychat injeta países sem o `55`.

**Nuance pro**
- `format_money` usa vírgula decimal e ponto de milhares (pt-BR), invertendo o default do Python.
- `_is_phone_brazilian` checa três condições (len=11, DDD≥11, digits[2]=='9') — sem isso, números austríacos (+43) seriam mutilados.

### 1.2 offerman (`shopman-offerman`)

**Escopo**: catálogo de produtos **vendáveis**. Nunca insumos.

**Modelos**
- `Product(uuid, sku[unique], name, short_description, long_description, keywords[taggit], unit, unit_weight_g, storage_tip, ingredients_text, nutrition_facts[JSON|NutritionFacts], base_price_q, availability_policy∈{stock_only, planned_ok, demand_ok}, shelf_life_days, production_cycle_hours, is_published, is_sellable, image_url, is_batch_produced, metadata, history[simple-history])`.
- `ProductComponent(parent FK Product, component FK Product, qty ≥ 0.001)` — UniqueConstraint(parent,component); cycles/self-reference proibidos; `BUNDLE_MAX_DEPTH=5`.
- `Listing(ref[unique], name, valid_from, valid_until, priority, is_active)`.
- `ListingItem(listing FK, product FK, price_q, min_qty, is_published, is_sellable, history)` — UniqueConstraint(listing, product, min_qty).
- `Collection(ref, name, parent[self, cascade], valid_from, valid_until, sort_order, is_active)` — `MAX_COLLECTION_DEPTH=10`, cycles proibidos.
- `CollectionItem(collection, product, is_primary, sort_order)` — uma primária por produto.

**Serviços**
- `CatalogService`: `get(sku)`, `unit_price(sku, qty, channel, listing)` (casca em `min_qty__lte`, ordena `-min_qty`), `price()`, `get_price()→ContextualPrice`, `expand(sku, qty)→list[{sku,name,qty}]` (recursivo, scale qty por qty), `validate(sku)→SkuValidation`, `search(query|collection|keywords)`, `get_listed/published/sellable_products(listing_ref)`, `get_projection_items(listing_ref)`.

**Protocols** (injeção por outros pacotes)
- `CostBackend.get_cost(sku)→int|None` (implementado por Craftsman).
- `PricingBackend.get_price(...)→ContextualPrice|None` (implementado por orquestrador/payman).
- `CatalogProjectionBackend.project/retract` (para iFood, Rappi).

**Signals**: `product_created`, `price_changed(old_price_q, new_price_q)`.

**Contrib**
- `contrib/substitutes/substitutes.py::find_substitutes(sku, limit=5, same_collection=True)` — score: keywords 3pts + coleção 2pts + price proximity 1pt. **Sem SequenceMatcher de nome** (evita falsos positivos em catálogos prefixados).

**Invariantes**
- Visibilidade = `Product.is_published ∧ ListingItem.is_published` (AND, não OR).
- Vendabilidade = `Product.is_sellable ∧ ListingItem.is_sellable`.
- Preço: cascata por `min_qty` — `filter(min_qty__lte=qty).order_by('-min_qty').first()`; fallback em `Product.base_price_q`.
- Bundle expansion escala por qty (2 croissants por combo × 5 combos = 10 croissants).
- Nutrição: validação ANVISA RDC 360/2003 — se qualquer nutriente, `serving_size_g>0`; `trans_fat_g ≤ total_fat_g`; `sugars_g ≤ carbohydrates_g`.

**Nuance pro**
- Acoplamento frouxo via `ref` (Listing.ref = Channel.ref por convenção, sem FK) — permite evolução independente.
- `ContextualPrice` nunca retorna `None` — se não há `PricingBackend`, list_price = final_price.
- Audit de preço via `simple-history` em `ListingItem`.

### 1.3 stockman (`shopman-stockman`, 0.3)

**Escopo**: inventário físico + planejado, ledger imutável, reserva com contrato check↔reserve travado.

**Modelos**
- `Position(ref, name, kind∈{PHYSICAL, PROCESS, VIRTUAL}, is_saleable, is_default, metadata)`.
- `Quant(sku, position→FK|null, target_date|null, batch='', _quantity[cache O(1)], metadata)` — UniqueConstraint(sku,position,target_date,batch); `_quantity≥0` check.
- `Move(quant FK PROTECT, delta, reason[obrigatório], timestamp, user|null, metadata)` — **save e delete proibidos em registros existentes**; atômico com `F()` update no Quant.
- `Hold(sku, quant FK|null, quantity, target_date, status∈{PENDING, CONFIRMED, FULFILLED, RELEASED}, expires_at|null, metadata{reference})`.
- `StockAlert(sku, position|null, min_quantity, is_active, last_triggered_at)`.
- `Batch(ref[unique], sku, production_date, expiry_date, supplier)`.

**Serviços** (facade `StockService` via `from shopman.stockman import stock`)
- `available(sku, target_date, position)`, `promise(sku, qty, target_date, safety_margin, allowed_positions)→PromiseDecision`, `demand()`, `committed()`.
- `receive(quantity, sku, position, target_date, batch, reason, user, **meta)→Quant`.
- `issue(quantity, quant, reason)→Move`.
- `adjust(quant, new_quantity, reason)→Move`.
- `hold(quantity, product, target_date, expires_at, allowed_positions, excluded_positions, **meta)→"hold:{pk}"`.
- `confirm(hold_id)`, `release(hold_id, reason)`, `fulfill(hold_id, user)→Move`.
- `release_expired()→int` (batch com `skip_locked=True`).
- `find_by_reference/find_active_by_reference/retag_reference`.
- `plan(quantity, product, target_date, position, reason, user, **meta)→Quant`.
- `replan`, `realize(product, target_date, actual_quantity, to_position, from_position, from_batch)` — materializa holds; holds sem TTL ganham `DEFAULT_MATERIALIZED_HOLD_TTL_MINUTES=30`; emite signal `holds_materialized`.
- `availability_for_sku/for_skus` — retornam `{sku, availability_policy, total_available, total_promisable, total_reserved, available, expected, planned, ready_physical, held_ready, breakdown{ready,in_production,planned,d1}, is_planned, is_paused, positions[]}`.
- `promise_decision_for_sku(sku, qty, ...)→PromiseDecision(approved, requested_qty, available_qty, reason_code)`.

**Scope gate canônico**: `quants_eligible_for(sku, channel_ref, target_date, allowed_positions, excluded_positions)` — aplicado por availability reads E hold finding; filtros na ordem: (1) sku+`_quantity>0`, (2) `filter_valid_quants()` shelflife, (3) allowed/excluded positions, (4) batch expiry.

**Signal**: `holds_materialized(hold_ids, sku, target_date, to_position)`.

**Protocol**: `SkuValidator.validate_sku/validate_skus/get_sku_info/search_skus` (implementado por Offerman).

**Invariantes não-negociáveis**
- **available = valid_quants_sum − active_holds_sum** (holds expirados nunca descontam — `is_active` checa TTL real-time).
- **D-1 staff-only**: `batch='D-1'` é bucket separado; canais remotos usam `excluded_positions=["ontem"]`.
- **Contrato check↔reserve travado**: ambos usam `quants_eligible_for()`. Check nunca aprova algo que reserve não consiga.
- **Atomicidade**: Move save + Quant._quantity via `F()` em `transaction.atomic()`; Hold creation via `select_for_update()` + recheck após lock; Hold transitions via `select_for_update()` + status guard.
- **Policy-driven promise**: `stock_only` (só ready), `planned_ok` (default, ready+planned), `demand_ok` (sempre aprovado, cria demand hold quant=None).
- **TTL de materialização**: `realize()` preserva TTL explícito; se hold era contra planejado sem TTL, aplica default ao materializar ("você queria; agora é real; mantenha sessão viva").
- **`metadata.planned=True`** propaga de `plan()` → Quant → availability.breakdown.

**Testes-contrato (PostgreSQL concurrency)**
- `test_concurrency.TestConcurrentHoldSameSku`: dois threads disputam mesmo quant; apenas um vence — zero over-sell garantido.
- `test_concurrency.TestConcurrentFulfillSameHold`: fulfill não duplica.
- `test_concurrency.TestConcurrentReleaseAndFulfill`: release e fulfill mutuamente exclusivos.
- `test_planned_holds.TestRealizeWithHolds`: TTL setado em materialização, preservado se pré-existente.

### 1.4 craftsman (`shopman-craftsman`)

**Escopo**: produção em lote (NUNCA por-pedido). WorkOrder = batch antecipado (bake 50 croissants para amanhã).

**Modelos**
- `Recipe(ref[slug unique], output_ref, batch_size, steps[JSON list], is_active, meta)` — `batch_size` é o rendimento base da ficha técnica.
- `RecipeItem(recipe, input_ref, quantity, unit, is_optional, sort_order)` — coeficiente francês: `qty_needed = item.qty × (wo.qty / recipe.batch_size)`.
- `WorkOrder(ref[WO-YYYY-NNNNN], recipe FK, output_ref[copiado no plan, imutável], quantity, finished|null, status∈{PLANNED,STARTED,FINISHED,VOID}, rev[optimistic concurrency], target_date, source_ref, position_ref, operator_ref, meta{_recipe_snapshot})`.
- `WorkOrderEvent(seq[monotônico por WO], kind∈{PLANNED,ADJUSTED,STARTED,FINISHED,VOIDED}, payload, idempotency_key[unique null], actor)` — append-only; PK composta (work_order, seq).
- `WorkOrderItem(kind∈{REQUIREMENT,CONSUMPTION,OUTPUT,WASTE}, item_ref, quantity, unit, recorded_at, recorded_by, meta)`.
- `RefSequence(prefix, next_value)` — atomicamente incrementado.

**Serviço** `CraftService` (facade classmethod)
- `plan(recipe, quantity, date, ...) → WorkOrder` (atomically: WO + "planned" event + `_recipe_snapshot` congelado em `meta`).
- `adjust(wo, quantity, reason)` — apenas `PLANNED`; emite "adjusted" event; bump rev.
- `start(wo, quantity=None)` — `PLANNED→STARTED`.
- `finish(wo, finished, expected_rev, idempotency_key)` — implicit start se `PLANNED`; atomico; retorna existing se `idempotency_key` já usado.
- `void(wo, reason)`.
- Queries: `expected(output_ref, date)`, `needs(date, expand=False)` (BOM explosion recursiva até 5 níveis), `suggest(date, demand_forecast)`.

**Signal**: `production_changed(product_ref, date, action∈{planned,adjusted,started,finished,voided}, work_order)`.

**Invariantes**
- **`_recipe_snapshot` congelado em `plan()`**: receita pode mudar depois, o registro histórico da WO é imutável.
- **Optimistic concurrency**: `UPDATE ... WHERE rev = expected_rev`; falha ⇒ `StaleRevision`; cliente retry com rev fresco.
- **seq monotônico via `select_for_update()`** em `_next_seq` — sem gaps, sem colisão.
- **Idempotência de `finish()`** via `idempotency_key` — retry seguro.
- **Yield rate** = finished/started; `loss` = base−finished. Payload do evento `finished` traz tudo.

**Nuance pro**
- WorkOrder **não** é assembly per-pedido. Pedidos sinalizam demanda; planejamento decide quando e quanto. KDS Prep faz montagem on-demand.

### 1.5 orderman (`shopman-orderman`)

**Escopo**: kernel de pedidos. Session mutável → Order selado → Directives assíncronas.

**Modelos**
- `Session(session_key, channel_ref, handle_type, handle_ref, state∈{open,committed,abandoned}, pricing_policy∈{internal,external}, edit_policy∈{open,locked}, rev, commit_token, data[JSON], pricing[JSON], pricing_trace[JSON list])` — UniqueConstraint(channel_ref, session_key) e (channel_ref, handle_type, handle_ref) parcial WHERE state='open'.
- `SessionItem(session, line_id, sku, name, qty, unit_price_q, line_total_q, meta)`.
- `Order(ref, uuid, channel_ref, session_key, handle_type, handle_ref, external_ref, status∈{NEW,CONFIRMED,PREPARING,READY,DISPATCHED,DELIVERED,COMPLETED,CANCELLED,RETURNED}, snapshot[JSON selado], data[JSON mutável pós-commit], total_q, currency)`.
  - `SEALED_FIELDS = [ref, channel_ref, session_key, snapshot, total_q, currency]` — save levanta `ImmutabilityError`.
  - Timestamps auto: `confirmed_at, preparing_at, ready_at, dispatched_at, delivered_at, completed_at, cancelled_at, returned_at`.
  - Guard: `DISPATCHED` requer `fulfillment_type="delivery"`.
- `OrderItem(order, line_id, sku, name, qty, unit_price_q, line_total_q, meta)`.
- `OrderEvent(order, seq, type, actor, payload)` — seq único por order.
- `Directive(topic, status∈{queued,running,done,failed}, payload, attempts, available_at, last_error, error_code, dedupe_key)` — at-least-once.
- `Fulfillment/FulfillmentItem` (PENDING→IN_PROGRESS→DISPATCHED→DELIVERED).
- `IdempotencyKey(scope, key, status, response_body)`.

**Serviços**
- `CommitService.commit(session_key, channel_ref, idempotency_key, ctx, channel_config) → dict`
  1. Lock idempotency (fora da tx) → retorna cached se `done`.
  2. Lock session (`select_for_update`); validar `open`.
  3. Validar `required_checks` frescos (rev match + holds não expirados).
  4. Validar `issues` sem blocking.
  5. Rodar validators `stage="commit"`.
  6. Copiar chaves específicas de `session.data → order.data` (lista explícita: customer, fulfillment_type, delivery_address, delivery_address_structured, delivery_date, delivery_time_slot, order_notes, origin_channel, payment, delivery_fee_q, is_preorder).
  7. Criar Order + OrderItems; `snapshot` = estado da sessão; `commitment` = evidência de checks/issues.
  8. `snapshot.lifecycle` = transitions/terminais do `channel_config` (cartão em pedra — congelado).
  9. Emit `OrderEvent("created")` + signal `order_changed`.
  10. Mark session `committed`.
  11. Enqueue diretivas pós-commit (ex.: preorder reminder D-1 09:00 se `delivery_date > today`).
  12. Mark idempotency `done`.
- `ModifyService.modify_session(session_key, channel_ref, ops, ctx, channel_config)` — ops: `add_line, remove_line, set_qty, replace_sku, set_data, merge_lines`. Pricing modifiers (prefix `pricing.*`) rodam sempre; restantes filtrados por `channel_config.rules.modifiers`. Validators `stage="draft"`. Incrementa rev; limpa checks/issues. Enqueue check directives.
- `Order.transition_status(new_status, actor)` — atomicamente, valida contra `snapshot.lifecycle` ou `DEFAULT_TRANSITIONS`, seta timestamp, emit `OrderEvent + order_changed`.

**Dispatch de directives** (`dispatch.py`)
- post_save Directive queued → `transaction.on_commit()` → `_process_directive()`:
  - Lock + status=running + attempts++.
  - Reentrancy guard (thread-local).
  - Handler.handle(message, ctx) via registry.
  - Success ⇒ done; fail ⇒ queued com `available_at = now + 2^attempts` ou failed se `MAX_ATTEMPTS=5`.
- Sweep oportunista: até 3 failed/queued prontos.

**Registry** (thread-safe RLock): validators, modifiers, directive_handlers (por topic), issue_resolvers, checks (topic+validator pair).

**Invariantes**
- **Selado pós-create**: `SEALED_FIELDS` + `ImmutabilityError`. Historia imutável mesmo que alguém chame `order.save(save=True)`.
- **Snapshot embala lifecycle**: order carrega transitions no momento do commit — mudança posterior não afeta order antigos.
- **Commitment snapshot**: `order.snapshot.commitment` guarda quais checks passaram, resultados e issues no ato — audit trail para disputas.
- **Idempotency por channel**: scope `commit:{channel_ref}`; key órfão `in_progress >24h` destravado automaticamente.
- **At-least-once directives + dedupe_key** ⇒ operação logicamente exactly-once.
- **Status→timestamp auto** (sem chamada explícita).
- **DISPATCHED guard**: rejeita se `fulfillment_type != "delivery"`.

### 1.6 guestman (`shopman-guestman`)

**Escopo**: identidade, segmentação, loyalty, insights RFM — todos channel-agnostic.

**Modelos**
- `Customer(ref[CUST-{12hex}], uuid, first_name, last_name, customer_type∈{INDIVIDUAL,BUSINESS}, document, birthday, email[cache], phone[cache], group FK, is_active, notes, metadata, source_system, history)`.
- `CustomerContact/ContactPoint(type∈{WHATSAPP,PHONE,EMAIL,INSTAGRAM}, value_normalized, value_display, is_primary, is_verified, verification_method∈{UNVERIFIED,CHANNEL_ASSERTED,OTP_WHATSAPP,OTP_SMS,EMAIL_LINK,MANUAL}, verified_at, verification_ref)` — UniqueConstraint global `(type, value_normalized)`; UniqueConstraint parcial `(customer, type) WHERE is_primary`.
- `CustomerGroup(ref, name, description, listing_ref, is_default[apenas um], priority, metadata)`.
- `contrib/loyalty/LoyaltyAccount(customer OneToOne, points_balance, lifetime_points[nunca decresce], stamps_current/target/completed, tier∈{BRONZE,SILVER,GOLD,PLATINUM})` — thresholds `[(5000,"platinum"),(2000,"gold"),(500,"silver"),(0,"bronze")]`.
- `LoyaltyTransaction(account, type∈{EARN,REDEEM,ADJUST,EXPIRE,STAMP}, points, balance_after, description, reference, created_at, created_by)` — **imutável** (save/delete em existente levanta `ValueError`).
- `contrib/insights/CustomerInsight(customer OneToOne, total_orders, total_spent_q, average_ticket_q, first/last_order_at, days_since_last_order, avg_days_between_orders, preferred_weekday[0-6], preferred_hour[0-23], favorite_products[JSON list], preferred_channel, channels_used, rfm_recency/frequency/monetary[1-5], rfm_segment∈{champion,loyal_customer,recent_customer,at_risk,lost,regular}, churn_risk[0-1], predicted_ltv_q, calculated_at, calculation_version)`.

**Serviços**
- `CustomerService`: `get`, `get_by_uuid/document/phone/email`, `validate(ref)→CustomerValidation`, `search(query)`, `groups()`, `create()` (emit `customer_created`), `update()` (emit `customer_updated` com `changes` dict, whitelisted fields).
- `LoyaltyService`: `enroll` (idempotente), `get_account/balance`, `earn_points` (atomico, atualiza tier), `redeem_points` (checa saldo), `add_stamp` (auto-reset ao completar), `get_transactions`.
- `InsightService`: `recalculate(customer_ref)` — usa `OrderHistoryBackend` injetado via setting `GUESTMAN.ORDER_HISTORY_BACKEND`; calcula RFM via thresholds configuráveis; churn heurístico; LTV; `recalculate_all`; `get_segment_customers`; `get_at_risk_customers(min=0.7)`.

**Invariantes**
- **ContactPoint é source of truth**; `Customer.phone/email` são caches (sync bidirecional via `set_as_primary()` / `_sync_contact_points()`).
- **LoyaltyTransaction append-only**: ledger contábil. `lifetime_points` só sobe.
- **Tier auto-upgrade** em earn, **nunca downgrade**.
- **RFM é opt-in**: recalculation não bloqueia create. Backend é plugável.

### 1.7 doorman (`shopman-doorman`)

**Escopo**: auth channel-agnostic (WhatsApp-first), device trust, magic links.

**Modelos**
- `VerificationCode(id UUID, code_hash[HMAC-SHA256, nunca plaintext], target_value[E.164|email], purpose∈{LOGIN,VERIFY_CONTACT}, status∈{PENDING,SENT,VERIFIED,EXPIRED,FAILED}, delivery_method∈{WHATSAPP,SMS,EMAIL}, attempts, max_attempts[default 5], ip_address, customer_id UUID, created_at, expires_at, sent_at, verified_at)`.
- `TrustedDevice(id UUID, customer_id UUID, token_hash[HMAC], user_agent, ip_address, label, created_at, expires_at[default 30d], last_used_at, is_active)`.
- `AccessLink(id UUID, token_hash[HMAC], customer_id UUID, audience∈{WEB_CHECKOUT,WEB_ACCOUNT,WEB_SUPPORT,WEB_GENERAL}, source∈{MANYCHAT,INTERNAL,API}, created_at, expires_at[default 5min], used_at, metadata, user FK|null)`.

**Serviço AuthService**
- `request_code(target, purpose, delivery_method, ip_address, sender) → CodeRequestResult` — normaliza, checa `is_login_allowed`, rate-limit (target+IP+cooldown), invalida PENDING/SENT anteriores do mesmo (target, purpose), gera 6 dígitos + HMAC, envia via `sender` ou adapter fallback chain, marca SENT, emit `verification_code_sent`.
- `verify_for_login(target, code_input, request) → VerifyResult` — normaliza, acha código válido (PENDING|SENT, not expired), `verify()` (HMAC constant-time); em fail: `record_attempt()` (atomic F()); resolve customer via adapter (auto-create se setting); `_link_verified_identifier()` (ContactPoint + IdentifierService, best-effort logged); marca VERIFIED; Django login com `PRESERVE_SESSION_KEYS`; emit `verification_code_verified`.
- `cleanup_expired_codes(days=7)`.

**Adapter hooks**: `normalize_login_target`, `resolve_customer`, `create_customer`, `should_auto_create_customer`, `is_login_allowed`, `send_code_with_fallback`, `on_login_failed`, `on_customer_authenticated`, `on_device_trusted`, `get_login/logout_redirect_url`.

**Invariantes**
- **HMAC hashing + constant-time compare** para código, token de device, token de magic link. Nunca plaintext.
- **Rate limit multi-dimensão**: por target + por IP + cooldown entre requests.
- **Fallback chain**: manychat → sms → email, registra método efetivo.
- **TrustedDevice**: HttpOnly + SameSite=Strict cookie; `last_used_at` atualizado a cada verificação; TTL com refresh on-use.
- **AccessLink single-use**: `used_at` marca consumo; TTL curto.

### 1.8 payman (`shopman-payman`)

**Escopo**: lifecycle de PaymentIntent + ledger imutável de transactions + adapters plugáveis.

**Modelos**
- `PaymentIntent(ref[PAY-{12hex}], order_ref[string, sem FK], method∈{PIX,CASH,CARD,EXTERNAL}, status∈{PENDING,AUTHORIZED,CAPTURED,FAILED,CANCELLED,REFUNDED}, amount_q[>0], currency, gateway, gateway_id, gateway_data, created_at, authorized_at, captured_at, cancelled_at, expires_at)`.
- `PaymentTransaction(intent FK PROTECT, type∈{CAPTURE,REFUND,CHARGEBACK}, amount_q[>0], gateway_id, created_at)` — **imutável** (save/delete em existente levanta).

**Transitions (TRANSITIONS dict — source of truth)**
- `PENDING → [AUTHORIZED, FAILED, CANCELLED]`
- `AUTHORIZED → [CAPTURED, CANCELLED, FAILED]`
- `CAPTURED → [REFUNDED]`
- Terminais: `FAILED, CANCELLED, REFUNDED`.

**Serviço PaymentService** (todas via `select_for_update()` atomicamente)
- `create_intent`, `authorize` (pende→auth, merge gateway_data), `capture` (auth→captured, **single-shot**, parcial abandona saldo), `refund` (captured|refunded, **múltiplos parciais até exaurir**, default refund_amount = available), `cancel`, `fail`, `get`, `get_by_order`, `get_active_intent`, `get_by_gateway_id`, `captured_total`, `refunded_total`.

**Protocol PaymentBackend**: `create_intent`, `authorize`, `capture`, `refund`, `cancel`, `get_status`.

**Invariantes**
- **Single-shot capture**: uma captura por intent; parcial abandona saldo.
- **Multiple partial refunds**: enquanto `refunded_total < captured_total`.
- **Status REFUNDED ≠ totalmente reembolsado**: é marcador de "pelo menos um refund". Verdade financeira é `refunded_total()`.
- **Idempotente via `select_for_update()`** — webhook replay seguro.
- **order_ref como string** (sem FK) — desacoplamento.

---

## 2. ORQUESTRADOR (`shopman/shop/`)

### 2.1 Shop + Channel + ChannelConfig

**Shop** (singleton via `.load()` cacheado): identidade, endereço Google Places estruturado, contato, operação (`opening_hours[JSON]`, currency, timezone), branding (colors OKLCH/RGB, fonts Google), `defaults[JSON]`, `integrations[JSON dict adapter→módulo]`.

**Channel**: `ref` canônico, `name`, `display_order`, `is_active`, `config[JSON]`, `integrations[JSON]` (overrides adapter por canal).

**ChannelConfig** (`shopman/shop/config.py`, 8 aspectos):

| # | Aspecto | Campos |
|---|---------|--------|
| 1 | **Confirmation** | `mode∈{immediate,auto_confirm,auto_cancel,manual}`, `timeout_minutes=5`, `stale_new_alert_minutes=0` |
| 2 | **Payment** | `method∈{counter,pix,card,external}\|list`, `timing∈{post_commit,at_commit,external}`, `timeout_minutes=15` |
| 3 | **Fulfillment** | `timing∈{at_commit,post_commit,external}`, `auto_sync=True` |
| 4 | **Stock** | `hold_ttl_minutes`, `safety_margin=0`, `planned_hold_ttl_hours=48`, `allowed_positions`, `excluded_positions`, `check_on_commit=False`, `low_stock_threshold=5` |
| 5 | **Notifications** | `backend∈{manychat,email,console,sms,webhook,none}`, `fallback_chain[list]`, `routing{event:backend}` |
| 6 | **Pricing** | `policy∈{internal,external}` |
| 7 | **Editing** | `policy∈{open,locked}` |
| 8 | **Rules** | `validators∈list|None (None=all; []=none)`, `modifiers∈list|None (tri-state)`, `checks[list]` |

**Cascata** via `deep_merge()`: defaults hardcoded da dataclass ← `Shop.defaults` ← `Channel.config`. Dicts merged; lists replaced. Não existe sistema de presets factory; cada instância configura canais via dicts literais no seed (ou admin posteriormente), e a cascata resolve o efetivo em `ChannelConfig.for_channel(channel)`.

### 2.2 Lifecycle + dispatch

Sinal `order_changed` (de orderman) → `dispatch(order, phase)` → resolve `ChannelConfig.for_channel(order.channel_ref)` → despacha no `_PHASE_HANDLERS`.

| Phase | Ações (em ordem) |
|-------|------------------|
| **on_commit** | `customer.ensure()` → availability check (se `check_on_commit`) → `stock.hold()` → `loyalty.redeem()` → `payment.initiate()` se `timing==at_commit` → `fulfillment.create()` se `timing==at_commit` → `_handle_confirmation()` ("order_received" notif salvo `immediate`) |
| **on_confirmed** | `payment.initiate()` se `timing==post_commit` → `stock.fulfill()` se `timing==external` e counter → notif "order_confirmed" |
| **on_paid** | race guard (cancelled? ⇒ refund + alert) → `stock.fulfill()` → notif "payment_confirmed" |
| **on_preparing** | `kds.dispatch()` se KDS ativo → notif |
| **on_ready** | `fulfillment.create()` se `timing==post_commit` → notif |
| **on_dispatched** / **on_delivered** | notif |
| **on_completed** | `loyalty.earn()` → `fiscal.emit()` |
| **on_cancelled** | `kds.cancel_tickets()` → `stock.release()` → `payment.refund()` → notif |
| **on_returned** | `stock.revert()` → `payment.refund()` → `fiscal.cancel()` → notif |

**Confirmação otimista**:
- `immediate`: `ensure_confirmable()` → transição síncrona para CONFIRMED.
- `auto_confirm`: `Directive(topic="confirmation.timeout", action="confirm", expires_at=now+timeout)`; operador pode cancelar antes.
- `auto_cancel`: directive com `action="cancel"`; operador deve confirmar.
- `manual`: sem directive; alerta opcional se stale em NEW.

**Guards**: `ensure_confirmable()` rejeita se `availability_decision.approved != True` (exceto `payment.timing=="external"`); `ensure_payment_captured()` ignora offline methods ("counter","cash","dinheiro","balcao","debito","credito") ou external.

**Production lifecycle** (paralelo): `production_changed(product_ref, date, work_order, action)` → `dispatch_production(wo, phase)` — hooks `reserve_materials(wo)`, `emit_goods(wo)`, `notify(wo, event)`.

### 2.3 Services (todos funções puras)

**Sync**: `stock.hold/fulfill/release/revert`, `availability.check/reserve/reconcile/decide/bump_session_hold_expiry/classify_planned_hold_for_session_sku/own_holds_by_sku`, `payment.initiate/capture/refund/get_payment_status`, `customer.ensure`, `fulfillment.create/update`, `pricing.resolve`, `checkout.process(session_key, channel_ref, data, idempotency_key, ctx)`, `kds.dispatch/on_all_tickets_done`, `production.reserve_materials/emit_goods/notify`.

**Async** (emitem Directives): `notification.send`, `loyalty.earn/redeem`, `fiscal.emit/cancel`.

### 2.4 Adapters + Protocols

**Resolução** `get_adapter(kind, method=None)`: (1) `Shop.integrations[DB]` → (2) `settings.SHOPMAN_*_ADAPTERS` → (3) built-in defaults.

**Tipos de adapter**
- `payment` (dict por método): `pix→payment_efi`, `card→payment_stripe`, `cash→payment_counter`, `external→payment_external`, `mock→payment_mock`. Signature `create_intent/authorize/capture/refund/cancel/get_status`; retorna `GatewayIntent`.
- `notification` (dict por backend): `console, email, manychat, sms, webhook, none`. Signature `send(recipient, template, context)→NotificationResult`.
- `stock`: módulo único; funções `create_hold/fulfill_hold/release_holds/receive_return`.
- `fiscal`: opcional; `FiscalBackend.emit_nfce/cancel_nfce`.
- `catalog`: `get_price(sku, qty, channel)→int`.
- `production`, `customer`: módulos.

**Protocols**: `PaymentBackend, GatewayIntent, PaymentStatus, CaptureResult, RefundResult, FiscalBackend, AccountingBackend, NotificationResult, CostBackend, PricingBackend, CatalogProjectionBackend`.

### 2.5 Rules engine (governança em duas camadas)

**Camada estática (handlers)**: registrados em `ShopmanConfig.ready()` via `register_all()`. Nunca mudam em runtime.

**Camada dinâmica (rules DB)**: tabela `RuleConfig(code, rule_path, label, enabled, params[JSON], channels[M2M], priority)`.

- `get_active_rules(channel, stage)` — filtrado, cache 1h, invalidado em `post_save(RuleConfig)`.
- `load_rule(rule_config)` — import dotted + instancia com `params` kwargs.
- `register_active_rules()` + `bootstrap_active_rules()` (deferred após conexão DB pronta, via signal `connection_created`).

**Tipos**:
- **Pricing modifiers** (wraps em `shop.modifiers` para visibilidade admin): D1Rule, PromotionRule, EmployeeRule, HappyHourRule.
- **Validators**: BusinessHoursRule (flag `outside_business_hours`), DeliveryZoneRule (blocker).

### 2.6 Handlers + Directive Topics

**Topics** (`shopman/shop/directives.py`): `notification.send`, `fulfillment.create/update`, `confirmation.timeout`, `order.stale_new_alert`, `fiscal.emit_nfce/cancel_nfce`, `accounting.create_payable`, `loyalty.earn/redeem`, `return.process`, `stock.hold/commit`, `pix.generate/timeout`, `payment.capture`.

**Handlers** (idempotentes): ConfirmationTimeoutHandler, StaleNewOrderAlertHandler, MockPixConfirmHandler (dev), NotificationSendHandler (chain manychat→sms→email, escala para OperatorAlert em fail), FulfillmentCreate/UpdateHandler, NFCeEmit/CancelHandler, PurchaseToPayableHandler, LoyaltyEarn/RedeemHandler, ReturnHandler.

**register_all()** ordem (em `apps.py::ready()`):
1. notification handlers + backends
2. confirmation + stale handlers
3. mock pix (se adapter `payment_mock`)
4. customer strategies (`SHOPMAN_CUSTOMER_STRATEGY_MODULES`)
5. fiscal (se setting)
6. accounting (se setting)
7. return
8. fulfillment
9. loyalty
10. pricing modifiers (ItemPricingModifier, SessionTotalModifier, OffermanPricingBackend, shop modifiers)
11. validators (BusinessHoursRule, DeliveryZoneRule)
12. stock signals (signal bridge para stockman)
13. SSE emitters

**Signal wiring** (`apps.py`): `connection_created → bootstrap_active_rules`; `post_save(RuleConfig) → invalidate_rules_cache`; `order_changed → dispatch`; `production_changed → dispatch_production`; `post_save(Recipe) → fill_nutrition_from_recipe`.

### 2.7 Modifiers (ordem de execução)

| Order | Modifier | Função |
|-------|----------|--------|
| 10 | pricing.item | base do backend, qty-aware |
| 20 | shop.discount | promos + cupom (maior desconto ganha, skip D-1) |
| 50 | pricing.session_total | recalc |
| 60 | shop.employee_discount | staff (default 20%, bloqueia happy_hour) |
| 70 | shop.delivery_fee | por zona, só delivery |
| 80 | shop.loyalty_redeem | pontos |
| 85 | shop.manual_discount | POS manual |

**Regra**: por item, **uma** discount vence (maior valor absoluto). D-1 bloqueia todos. Employee bloqueia happy_hour.

### 2.8 Webhooks

**EFI PIX** `POST /webhooks/efi/pix/`:
- Auth: mTLS (proxy header `X-SSL-Client-Verify: SUCCESS`) + shared token (`X-Efi-Webhook-Token` ou `?token=`) via `hmac.compare_digest()`.
- **Sem skip flag em nenhum ambiente** — dev usa mesmo code path, apenas token diferente.
- Payload: `{pix: [{txid, endToEndId, valor}, ...]}`.
- `confirm_pix(txid, e2e_id, valor)` → Payman (idempotente via `get_by_gateway_id`) → dispatch `on_paid`.

**Stripe** `POST /webhooks/stripe/`: signature via `stripe.Webhook.construct_event()`.

### 2.9 Middleware + Context Processors

**Middleware**: `ChannelParamMiddleware` (captura `?channel=`), `OnboardingMiddleware` (redireciona staff para `/gestor/setup/` se sem Shop), `WelcomeGateMiddleware` (redireciona cliente autenticado sem nome para `/bem-vindo/`).

**Context processors**: `shop()`, `omotenashi()`, `cart_count()`.

### 2.10 Projections (read-side views)

`account`, `cart`, `catalog`, `checkout`, `order_tracking`, `payment`, `product_detail`, `dashboard`, `closing`, `kds`, `order_queue`, `pos`, `production`.

### 2.11 Web UI

Ver spec completo no chat (URL map, CartService, Checkout, Tracking, KDS, POS, Pedidos, HTMX+Alpine conventions, Penguin UI tokens).

### 2.12 Admin (Unfold)

Sidebar dinâmica + dashboard com KPIs + Chart.js + tabelas. `ChannelForm` com JSON por aspecto. `ShopAdmin` com color pickers e storefront_preview iframe. Pacotes contribuem `contrib/admin_unfold/` funcionando standalone.

### 2.13 API (DRF)

Endpoints `/api/v1/cart/`, `/api/v1/checkout/` (3/min), `/api/v1/availability/<sku>/` (cache 10s), `/api/v1/catalog/products/` (cursor 20), `/api/v1/tracking/<ref>/` (mesmo gate de sessao/cliente/staff do tracking HTML), `/api/v1/account/*`, `/api/v1/geocode/reverse` (30/min). Idempotency key no checkout. Error envelope consistente. Todas as responses carregam `X-API-Version: 1`. Path prefix `v1` é contrato: breaking changes vão em `v2` paralelo, nunca mutam `v1` in-place.

---

## 3. INSTÂNCIA (NELSON BOULANGERIE)

### 3.1 Papel e layout

`instances/nelson/` é Django app em `SHOPMAN_INSTANCE_APPS`. Conteúdo: `apps.py, modifiers.py, customer_strategies.py, management/commands/seed.py, static/, templates/`.

### 3.2 Bootstrap

`config/settings.py` wires: Daphne (primeiro), Unfold, Django core, terceiros, 8 cores + contribs, `shopman.shop`, instance apps via env. Middleware inclui `doorman.AuthCustomerMiddleware` + 3 middleware shopman. Auth backends: PhoneOTPBackend + ModelBackend. Templates com 3 context processors. PostgreSQL via `DATABASE_URL` e Redis via `REDIS_URL` formam o runtime canonico; SQLite/LocMem sao apenas fallback local. `REDIS_URL` configura `django.core.cache.backends.redis.RedisCache` e `EVENTSTREAM_REDIS` para SSE multi-worker.

### 3.3 Seed

`make seed`: 1 Shop, 13 produtos, 4 coleções, 4 listings, 5 canais configurados via dict literal no seed — `balcao` (confirmation=immediate, payment=counter), `delivery`/`whatsapp`/`web` (auto_confirm + [pix,card] + hold 30min), `ifood` (auto_cancel + external + locked editing). 4 positions (deposito/vitrine/producao/ontem), quants iniciais, 6 receitas, 3 customer groups, 5 promoções, 7 StockAlerts.

### 3.4 Superfícies de customização

Templates (app precedence), static, Shop tokens, canais/presets, adapters (settings), rules (DB admin), handlers custom (ready()), customer strategies, OmotenashiCopy, modifiers custom.

---

## 4. CENÁRIOS E2E POR POV

### 4.1 POV: Cliente final

**E2E cliente web pré-compra delivery**: home (OmotenashiContext) → menu (SSE stock-update) → PDP (add qty) → `availability.reserve` cria Hold → cart badge "Aguardando confirmação" → checkout (Google Places + slots) → OTP WhatsApp (manychat) → auto-create customer → CommitService → `on_commit` dispatch (adopt hold FIFO por qty, payment.initiate PIX, notif "order_received") → QR code → EFI webhook `on_paid` → stock.fulfill → tracking SSE → completed → loyalty.earn + fiscal.emit.

**E2E WhatsApp bot**: bot ManyChat cria AccessLink (audience=WEB_CHECKOUT, TTL 5min, source=MANYCHAT) → cliente clica → AccessLinkLoginView valida HMAC+single-use → Django login → redirect para checkout com cart pré-carregado.

**E2E balcão (POS)**: preset pos() → immediate confirm → stock.fulfill imediato.

**E2E recovery (kintsugi)**: availability.reserve shortage → CartUnavailableError com substitutes → UI modal "Acabou! Que tal..." com alternativas.

### 4.2 POV: Operador de pedidos

`/admin/operacao/pedidos/` tabs por status (polling/HTMX). Card NEW com timer Alpine verde/amarelo/vermelho. Auto-confirm countdown visível. Reject → CANCELLED → dispatch on_cancelled → release+refund+notif. Passa timer → Directive confirmation.timeout → ConfirmationTimeoutHandler → CONFIRMED.

### 4.3 POV: Cozinha (KDS)

HTMX polling 5s; Alpine timer 1s. Prep ticket com checkboxes por item + "Pronto". Timer amarelo em target, vermelho em 2×target + priority_high icon. `kds.on_all_tickets_done` → READY → dispatch on_ready.

### 4.4 POV: Caixa (POS)

Staff login → abrir caixa → POS board (grid + carrinho) → lookup phone → immediate confirm → fulfill → on_completed → loyalty.earn. Sangria / Fechar caixa reconcilia.

### 4.5 POV: Dono / gestor

Admin Unfold dashboard KPIs + charts + tabelas (pendentes, produção, estoque baixo, D-1, recentes, alerts, sugestão produção). Configura promoção no admin → aplicada automaticamente pelo modifier pipeline. Closing: qty_unsold por SKU → D-1 movido para "ontem"; perecível vira perda; DayClosing audit record.

### 4.6 POV: Desenvolvedor / integrador

Nova instância: `instances/minha_padaria/` + settings env. Swap adapter via `SHOPMAN_PAYMENT_ADAPTERS`. Handler custom em `ready()`. Standalone: `pip install shopman-stockman` + INSTALLED_APPS — StockService exposto sem shopman.shop.

---

## 5. ASPECTOS TRANSVERSAIS

### 5.1 Arquitetura

Composição não herança; sinais como contratos fracos + directives como firmes; ChannelConfig como parametrização completa; single writer multi readers; imutabilidade onde possível (Move, LoyaltyTransaction, OrderEvent, WorkOrderEvent, Order.snapshot, PaymentTransaction); JSON para flex + coluna para queries em escala.

### 5.2 UI/UX — Omotenashi + Mobile + WhatsApp

**3 portões**: Antecipar (Yosoku), Estar presente (Sonzai), Ressoar (Yoin). **5 testes**: invisível, antecipação, ma, calor, retorno. **5 lentes**: QUEM / QUANDO / ONDE / O QUÊ / COMO.

Copy patterns: "Bom dia, João. Croissants acabaram de sair do forno." "Ainda não chegamos aí" não "Fora da área". Mobile-first: breakpoints sm/md/lg, thumb zones, 48px touch, 16px+ body, bottom-nav. WhatsApp-first: OTP manychat default, AccessLink chat→web, templates curtos, roteamento origin_channel.

### 5.3 Simplicidade / Robustez / Elegância

Simplicidade: ~3 conceitos por Core, 8 aspectos ChannelConfig. Robustez: select_for_update em paths críticos, at-least-once + dedupe_key, idempotency keys, reentrancy guard, BOM snapshot, snapshot.lifecycle em Order. Elegância: uma facade por Core, uma resolução de adapter, uma porta dispatch, handlers idempotentes sem sagas.

### 5.4 Core enxuto / Flexibilidade / Agnosticidade

Core enxuto: Offerman sem noção de Channel (só `listing_ref` string); Stockman sem noção de Order (só `reference` metadata); Orderman sem noção de Stockman (directive); Payman sem FK para Order. Flexibilidade: policies per SKU, ChannelConfig cascade, Rules DB-driven, JSONField extensão. Agnóstico: adapters para payment/notification/stock/catalog/fiscal; mesmo código para balcão/delivery/WhatsApp/iFood — preset muda.

### 5.5 Onboarding / Adoção

Dia 1: `make install && migrate && seed && run` ⇒ rodando. `make dev` CSS watch + worker + server. O gate factual atual fica em [`../status.md`](../status.md): `make test` local e `Runtime Gate` remoto com PostgreSQL/Redis. ADRs documentam decisões. CLAUDE.md contrato para agentes.

### 5.6 Segurança

HMAC-SHA256 + constant-time para OTP/device/access link. Rate limit 3 dims. HttpOnly+SameSite cookies. CSRF middleware. Webhook EFI mTLS+token sem skip. Ratelimit checkout 3/min + geocode 30/min. Secrets server-only (Maps/Stripe/EFI). Error envelope sem stack. Authorization staff/login_required/opaque ref.

### 5.7 Documentação como produto

8 ADRs, 11 guides, reference (data-schemas canônico + glossary), business-rules 32KB partitura, omotenashi 27KB manifesto+operacional, plans archived+active, audit reports, CLAUDE.md.

### 5.8 Standalone vs orquestrado

Cada Core viável standalone (Offerman = e-commerce catálogo, Stockman = estoque, etc.). Orquestrado = comércio completo.

---

## 6. INVARIANTES NÃO-NEGOCIÁVEIS

### 6.1 Nomenclatura e tipos
- Personas: Offerman/Stockman/Craftsman/Orderman/Guestman/Doorman/Payman.
- `ref` (slug); exceção Product.sku. WorkOrder.ref é sequencial.
- Monetário `_q` centavos via monetary_mult/div ROUND_HALF_UP.
- Phone E.164 via normalize_phone.
- Namespace `shopman.*` PEP 420.

### 6.2 Dados
- JSONField keys catalogados em data-schemas.md antes de write.
- CommitService copia keys por lista explícita.
- Order.SEALED_FIELDS enforced com ImmutabilityError.
- Move/LoyaltyTransaction/OrderEvent/WorkOrderEvent/PaymentTransaction append-only.
- _recipe_snapshot congelado em plan().

### 6.3 Lifecycle
- dispatch(order, phase) única porta.
- Handlers idempotentes em ready() via register_all().
- Directives com dedupe_key, max 5, backoff 2^n.
- Reentrancy guard.

### 6.4 Estoque
- quants_eligible_for = scope gate único.
- Hold via select_for_update + recheck.
- is_active TTL real-time (sem cron dependence).
- D-1 bucket separado, remotos excluem "ontem".
- realize preserva TTL explícito.

### 6.5 Orquestração
- ChannelConfig cascade via deep_merge.
- Adapter 3-level resolution.
- Rules DB-driven cache 1h.
- 4 modos confirmação.
- Webhook sem skip.

### 6.6 UI
- HTMX↔server, Alpine↔DOM. Zero onclick/classList/document.getElementById.
- Planned-hold badges + countdown.
- Optimistic confirmation visível.
- SSE + polling 60s fallback.
- Copy Omotenashi; 48px touch; 16px+ body; WCAG AAA primary.

### 6.7 Auth
- HMAC-SHA256 + constant-time.
- Rate 3 dims.
- AccessLink single-use.
- TrustedDevice HttpOnly+SameSite.

### 6.8 Pagamento
- Single-shot capture.
- Multi partial refunds até exaurir.
- REFUNDED ≠ totalmente reembolsado.
- select_for_update em toda mutação.
- order_ref string.

### 6.9 Instância
- Django app em SHOPMAN_INSTANCE_APPS.
- Template shadow app precedence.
- Seed completo.
- Branding via Shop.
- Handler custom em ready().

---

## 7. FIDELITY CHECKLIST PARA REIMPLEMENTAÇÃO

### Gate 1 — Fundamentos
- 9 pacotes pip-installable criados.
- admin_unfold standalone por pacote.
- shopman.utils zero-dep.
- `make test` deve passar localmente; `Runtime Gate` deve passar no PR com PostgreSQL/Redis e build Docker. Ver [`../status.md`](../status.md).

### Gate 2 — Domínio vertical
- Offerman: bundle recursivo + cycle detection; min_qty cascade; two-level AND.
- Stockman: quants_eligible_for único; select_for_update + recheck; teste concurrency passa.
- Craftsman: _recipe_snapshot; optimistic rev; idempotency_key finish.
- Orderman: snapshot sealed; directives at-least-once; CommitService copia explícito.
- Guestman: ContactPoint source of truth; LoyaltyTransaction imutável; RFM opt-in.
- Doorman: HMAC + constant-time; rate 3 dims; HttpOnly cookie.
- Payman: TRANSITIONS dict; single-shot capture; multi partial refunds.

### Gate 3 — Orquestração
- ChannelConfig 8 aspectos com deep_merge.
- Lifecycle dispatch config-driven; 4 modos.
- Adapter 3-level.
- Rules DB cache 1h.
- Handlers ready().
- Webhooks idempotentes.

### Gate 4 — UI
- Penguin UI Industrial dinâmico.
- HTMX + Alpine only.
- Planned-hold transparency.
- SSE + polling fallback.
- Omotenashi copy.
- A11y 48/16/AAA.

### Gate 5 — Instância
- Nelson `make seed && run` out-of-box.
- 5 canais distintos.
- D-1 staff-only funcionando.
- 5 promoções + cupons.
- 5 surfaces separadas.

### Gate 6 — Documentação
- 8 ADRs.
- data-schemas canônico.
- business-rules 16+apêndice.
- omotenashi 3+5+5 + corolários + mapa.
- CLAUDE.md.

### Gate 7 — Nuances pro
- Manychat `+55` bug handling.
- ROUND_HALF_UP nunca banker's.
- Bundle expansion scale (2×5=10).
- Planned-hold TTL em materialização.
- immediate bloqueia sem availability_decision.approved.
- CommitService copia keys explicitamente.
- REFUNDED marcador não verdade.
- Attempt via F() atomic.
- ContactPoint sync bidirecional.
- Rule context rico.
- Signal reentrancy guard.
- Webhook sem skip.
- Admin forms de dataclasses.
- Django `{% comment %}` multi-linha.
- Tailwind classes existentes.
- Material Symbols tabela canônica.
- Projections separadas de admin/views.
- Zero residuals.

---

## Notas finais ao agente consumidor

1. Este spec é um contrato; desvio = ADR nova.
2. Core é sagrado; antes de alterar, leia serviços/handlers/testes.
3. JSONField é extensão com catálogo em data-schemas.md.
4. Omotenashi é infraestrutura, não decoração.
5. Test coverage é consequência; concorrência + contrato são não-negociáveis.
6. Persona naming é identidade; Offerman ≠ "Products".
