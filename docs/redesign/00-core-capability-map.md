# Mapa de Capacidades do Core — Fundação do Redesign (Etapa A)

> Iniciativa [[project_excellence_refactor_initiative]]. Etapa **A (Fundação)**. Este doc mapeia,
> contrato a contrato, **o que o Core (packages/) + o orquestrador (shopman/shop/) já oferecem às
> superfícies** — pra que a nova arquitetura de superfícies (Loja Online · PDV · Agentic ·
> Backoffice) nasça **alavancando** o Core, e pra separarmos cirurgicamente *"o Core não cobre"* de
> *"o Core cobre, mas a superfície atual surfaceia mal"*. Fonte: leitura direta do código
> (2026-06-05). NÃO é proposta de arquitetura — é o inventário do que temos.

## ⭐ A grande conclusão (lê isto primeiro)
O Core/Kernel é **muito mais poderoso e config-driven do que a superfície atual aproveita**. O
contrato que as superfícies consomem já existe, maduro e desacoplado:
- **Lifecycle 100% config-driven** (zero herança — dict de fases + `ChannelConfig`). A superfície
  **nunca codifica regra de transição**: emite a mutação, o orquestrador resolve os efeitos.
- **`ChannelConfig`** (8+2 aspectos, cascata Channel←Shop←default, editável no Admin) parametriza
  TODO o comportamento por canal.
- **`SurfaceActionProjection`** já é um contrato canônico de *"o que esta superfície pode fazer
  agora"* (ref/label/href/method/payload_schema/idempotency/confirmation) — base perfeita pra UI
  projection-driven.
- **`remote_mutations` + `conversation` projection** já existem → fundação pronta pra **agentic/
  headless**.
- Acoplamento por **handle/UUID/string ref** (sem FK entre packages) → superfícies plugam sem
  importar ORM cruzado.

→ **Hipótese de trabalho pro redesign:** o "frankenstein" está em COMO as superfícies atuais
consomem esse contrato (context-building duplicado, inconsistente, lógica nas views/templates), não
no Core. A nova arquitetura deve ser um **consumidor fino, uniforme e projection-driven** desse
contrato. (A confirmar na etapa B, ao auditar as superfícies atuais.)

---

## Camada 1 — Fundação & Catálogo (`utils`, `refs`, `offerman`)

**utils** — primitivas puras: dinheiro em centavos `_q` (`monetary_mult/div`, `format_money` pt-BR),
`normalize_phone` (E.164 + repara bug ManyChat), `RefField` shim, `BaseError(code,message,data)`
(toda exceção do suite herda → superfície faz branch em `.code`), helpers de Unfold admin.

**refs** — "DNS do domínio": registro `(ref_type, value, scope)` → entidade, **sem GFK**. RefTypes
declarados em código (`register_ref_type`): uniqueness/normalização/validação/geração/cascata por
tipo. Services: `attach/resolve/resolve_object/transfer/deactivate`. **`transfer`** = mover refs
Session→Order no commit. **Generators**: sequence, date_sequence (reset diário — comandas), alpha_numeric,
short_uuid, checksum. **Bulk**: `cascade_rename` (renomeia em todas as colunas RefField),
`migrate_target` (merge de cliente/sessão), `deactivate_scope` (fechamento de dia). → superfície
nomeia mesa/pedido/token sem acoplamento, com unicidade escopada + geração + rename/close em massa.

**offerman** (só produtos vendáveis) — catálogo:
- **Product**: `sku` (RefField), `base_price_q`, `is_published`/`is_sellable` (gate comercial 2
  níveis com Listing), `keywords` (taggit → SEO/busca/substitutos), `nutrition_facts` (JSON validado
  ANVISA), `availability_policy` (`stock_only`/`planned_ok`/`demand_ok`), `unit_weight_g`,
  `shelf_life_days`, `image_url`. `is_bundle` (tem componentes), `reference_cost_q`/`margin_percent`
  (custo vem do CostBackend/Craftsman). Manager `.sellable()/.published()`.
- **Listing/ListingItem**: preço+disponibilidade **por canal** (`Listing.ref ↔ Channel.ref`, sem FK),
  `price_q`, `min_qty` (tiers de preço), validade temporal.
- **Collection/CollectionItem**: categoria hierárquica OU coleção temporal; `is_primary` (1 por
  produto). **ProductComponent**: composição de bundle.
- **CatalogService** (a API): `get`, `unit_price`/`price` (cascata de tier), **`get_price(...) →
  ContextualPrice`** (cotação canônica: list vs final + adjustments + PricingBackend plugável),
  `expand` (bundle→componentes), `search`, **`get_sellable_products(ref)`/`get_published_products(ref)`**
  (QuerySets date-aware pra menu/listagem), `project_catalogs()` (push pra canais externos).
- **`find_substitutes(sku)`** (contrib) — fallback de indisponível (keywords×3 + coleção×2 + preço±30%).
  **Substituição, não cross-sell.**
- **Protocols** (extension): `CatalogBackend`, `PricingBackend`, `CostBackend`, `CatalogProjectionBackend`.
- **REST read API**: `/products/`, `/products/{sku}/price/`, `/collections/`, `/listings/`. (Headless/agentic-ready.)
- **Config**: `OFFERMAN` dict (backends de cost/pricing/projection swappable).

---

## Camada 2 — Estoque & Produção (`stockman`, `craftsman`)

**O contrato de disponibilidade (do qual storefront E PDV dependem):**
- **`quants_eligible_for(sku, *, channel_ref, target_date, allowed_positions, excluded_positions)`** —
  **scope gate único** compartilhado por *check* (leitura) e *reserve* (hold) → não podem divergir.
- **`availability_for_sku(s)(...)`** → dict canônico com buckets **ready / in_production / planned /
  d1**, `total_available`, `total_promisable`, `is_planned`, `positions[]`. Versão batch
  shape-idêntica pra grades de catálogo.
- **`promise_decision_for_sku(sku, qty, ...)` → PromiseDecision** (`approved`, `reason_code`) — o
  "posso prometer?" de uma linha de carrinho.
- **Política por SKU**: `stock_only` / `planned_ok` (default) / `demand_ok` (forward-sell/sob-demanda).
- **Reserve**: `StockHolds.hold/confirm/release/fulfill` (mesmo scope gate; FIFO; 1:1 hold:quant).
  Holds por `metadata.reference` (session→order: `retag_reference`).
- **`excluded_positions`** = estoque staff-only (D-1 escondido de canais remotos); `allowed_positions`+
  `safety_margin` vêm do canal via `CHANNEL_SCOPE_RESOLVER` (projeta `ChannelConfig.stock`).
- **Models**: Quant (sku×position×target_date×batch), Move (ledger imutável — único escritor de qty),
  Hold (reserva OU demanda flutuante), Position (`is_saleable`), Batch (lote/validade), StockAlert.
- **REST**: `availability/`, `availability/bulk/`, `promise/`, `positions/<ref>/quants/`,
  **`alerts/below-minimum/`** (déficit acionável), `receive/`, `issue/`, `moves/`, `holds/`.
- **Forward-sell first-class**: `demand_ok` → hold flutuante → `realize()` materializa (TTL +
  signal `holds_materialized`) → base da UX "Aguardando confirmação / Tudo pronto! Confirme".

**craftsman** (produção em LOTE antecipada — nunca por-pedido):
- **Recipe** (1 ativa por output_sku; BOM multinível depth-5), **WorkOrder** (`WO-YYYY-NNNNN`,
  lifecycle planned→started→finished→void, `source_ref` string ex `order:789`, `_recipe_snapshot`
  congelado), **WorkOrderEvent** (audit idempotente), **WorkOrderItem** (ledger material requirement/
  consumption/output/waste).
- **CraftService**: `plan/adjust/start/finish/void` + queries **`expected(sku,date)`** (alimenta
  "expected" da disponibilidade), `needs` (explosão BOM), **`suggest(date)`** (produção dirigida por
  demanda via DemandBackend), **`queue(...)`** (a projeção do chão de produção / KDS prep), `summary`.
- **Handoff produção→disponibilidade** (signal `production_changed` + `contrib/stockman` bridge):
  planned→quant planejado; started→quant `batch="started"` (vira in_production/expected);
  finished→`realize()` (planned/started → posição saleable, **migrando holds automaticamente**);
  voided→zera. → uma WorkOrder planejada **vira automaticamente disponibilidade vendável**.
- **Protocols**: InventoryProtocol (Stockman implementa), DemandProtocol (Orderman implementa),
  CatalogProtocol (Offerman). Config `CRAFTSMAN` (MODE graceful/strict, backends).

---

## Camada 3 — Pedidos (`orderman`) — o coração

**Kernel canal-agnóstico**: não conhece comida/BR/canais; tudo via `channel_ref` (string) +
`channel_config` (dict, resolvido pelo orquestrador). Extensão via **registry de protocols** ou
**chaves em JSONFields**.

- **Session** (mutável, carrinho/comanda): `session_key` (estável, sobrevive ao commit),
  `channel_ref`, `(handle_type, handle_ref)` (dono — mesa/telefone/tab; **constraint: 1 sessão aberta
  por handle**), `state` (open/committed/abandoned), `pricing_policy` (internal/external),
  `edit_policy` (open/locked), **`rev`** (revisão monotônica = mecanismo central de staleness; toda
  edição bumpa, checks carimbam, commit rejeita rev divergente), `commit_token`.
  - **`data`** (JSON): zona sistema (`checks`, `issues`) + zona negócio (`customer`,
    `fulfillment_type`, `delivery_*`, `payment`, `coupon_code`, `manual_discount`, POS `tab_*`/
    `fired_lines`, `fiscal`, `receipt`…). Inventário em `docs/reference/data-schemas.md`.
  - **`Session.items`** = montado de **SessionItem** (linhas em TABELA, não JSON → queryável).
  - **SessionEvent** (audit append-only ancorado em `session_key` → sobrevive à deleção + contínuo
    no commit). Anti-fraude.
- **Order** (selado/imutável; `SEALED_FIELDS`): `ref` (`{CHANNEL}-{YYMMDD}-{CODE}`), `session_key`
  (herdado!), **9 status canônicos** (new→confirmed→preparing→ready→dispatched→delivered→completed +
  cancelled/returned), timestamps por status. **State machine override-able por canal**
  (`snapshot["lifecycle"]["transitions"]`). **`snapshot`** (selado 1x no commit: items/data/pricing/
  rev/commitment/lifecycle). **`data`** (chaves copiadas + enriquecidas pós-commit).
- **Verbos/Services:**
  - **`ModifyService.modify_session(...ops...)`** — verbo de edição. Ops: `add_line`/`remove_line`/
    `set_qty`/`replace_sku`/`set_data`(path whitelisted)/`merge_lines`. Bumpa rev, roda modifiers+
    validators(draft), zera checks, enfileira Directives dos checks.
  - **`ModifyService.move_lines(...)`** — transfer/split/merge de comanda; **congela preço** (não
    re-precifica), só recomputa total estrutural.
  - **`CommitService.commit(...idempotency_key...)`** — Session→Order. Valida frescor de checks
    (rev), holds não expirados, issues bloqueantes, validators(commit); **copia 11 chaves explícitas**
    data→order.data + computa `is_preorder`; sela snapshot. (Pra propagar nova chave: adicionar em
    `_do_commit`.)
  - **`SessionWriteService.apply_check_result(...)`** — write-back de checks stale-safe (carimba rev).
  - **`ResolveService.resolve(...issue_id, action_id...)`** — resolução de issue 1-clique (via
    IssueResolver registrado por source).
  - **`CustomerOrderHistoryService`** — CRM (link `order.data["customer_ref"]`, queryável).
  - Cancel/return/prepare = **`Order.transition_status()`** (state machine) + Directives (orquestração
    real vive no shop/).
- **Directive** (fila durável at-least-once): `topic` → handler; `payload` (schema por topic);
  `available_at` (agendamento: D-1, timeouts); `dedupe_key`; retry/backoff. Despacho signal-driven
  (on_commit) + worker fallback (`process_directives --watch`).
- **Registry** (5 extension points): `Validator`(stage draft/commit), `Modifier`(order, in-place),
  `DirectiveHandler`(topic), `IssueResolver`(source), `Check`. Quem registra = o orquestrador.
- **REST**: `POST /sessions` (get-or-open por handle), `/sessions/{key}/modify|resolve|commit`,
  `/orders`, `/orders/stream` (polling). `OperationSerializer` = gateway de validação de ops.

---

## Camada 4 — Cliente, Auth, Pagamento (`guestman`, `doorman`, `payman`)

**guestman** (identidade/CRM/loyalty):
- **Customer** (`uuid` = handle cross-package; `ref` CUST-…; group→`listing_ref` pricing),
  **ContactPoint** (source of truth de canais: whatsapp/phone/email/instagram; unique global por
  `(type, value_normalized)`; verificação), **ExternalIdentity**, **CustomerGroup**,
  **CustomerAddress** (Google Places, iFood-style, `place_id`/lat-long).
- **contrib**: loyalty (pontos+selos+tier), **insights** (RFM: recency/frequency/monetary, segment,
  churn_risk, predicted_ltv, favorite_products), identifiers (dedup multicanal), preferences,
  timeline, **consent** (LGPD opt-in por canal), **merge** (consolida tudo + reescreve
  `Order.data.customer_ref`, 24h reversível).
- **Services**: `get_by_phone/email`, `validate(ref)` (popula Session), `search`,
  **`IdentifierService.find_or_create_customer(type,value)`** (resolução cross-canal canônica),
  **`ManychatService.sync_subscriber`**, `suggest_address` (cascata iFood), `ConsentService.has_consent`
  (gate pré-envio), `InsightService.recalculate`. **REST**: CustomerViewSet + LookupView (phone/email/
  external) + InsightsSummary.

**doorman** (auth — **mandato de governança atrito-vs-segurança**, tudo parâmetro):
- **VerificationCode** (OTP, só hash HMAC), **AccessLink** (magic link / bridge chat→web),
  **TrustedDevice** (skip-OTP via cookie), **PinCredential** (PIN por User, surface-agnostic POS/KDS/
  step-up; lockout/rotação), **CustomerUser** (bridge Customer↔User).
- **Services**: `AuthService.request_code/verify_for_login`, `AccessLinkService.create_token/exchange/
  send_access_link`, `DeviceTrustService`, `PinCredential.verify/set_for`. Primitiva cripto:
  `hmac_matches`/`pin_matches` (compare_digest). **Plaintext nunca armazenado.**
- **Config** `DOORMAN` dict (TTL/attempts/rate-limit/cooldown/lockout, `AUTO_CREATE_CUSTOMER`,
  `PRESERVE_SESSION_KEYS` = carrega carrinho no login) — **atrito ajustável sem código**.
- Adapter `AUTH_ADAPTER` + `CUSTOMER_RESOLVER` + senders (manychat/sms/email). Gates G7-G12.
- PIN consumido por `backstage/services/operator.py` (`eligible_operators`, `verify_operator_pin`,
  `verify_manager_pin`).

**payman** (pagamento — gateway-agnóstico):
- **PaymentIntent** (`order_ref` string, sem FK; state machine no model: pending→authorized→captured→
  refunded/failed/cancelled; idempotency_key) + **PaymentTransaction** (movimento imutável: capture/
  refund/chargeback).
- **PaymentService**: `create_intent/authorize/capture/refund/cancel/fail` + `captured_total/
  refunded_total` (fonte da verdade) + **`reconcile_gateway_status(...)`** (snapshot cumulativo;
  normaliza vocab Stripe+Efi). Signals `payment_*`.
- **Webhook é o único caminho confiável de retorno** (PCI SAQ A). Gateways concretos vivem FORA
  (shop/adapters/payment_efi|stripe|mock) via `PaymentBackend` protocol.

---

## Camada 5 — Orquestrador (`shopman/shop/`) — o contrato principal das superfícies

**4 eixos de configurabilidade (runtime, sem deploy):** `ChannelConfig` · `adapters` · `RuleConfig` ·
`templates/copy`.

- **Lifecycle** (`lifecycle.py`, 100% config-driven): signal `order_changed` → `dispatch(order,
  phase)` (envolto em `on_commit`). **10 fases** (on_commit/confirmed/paid/preparing/ready/dispatched/
  delivered/completed/cancelled/returned) que orquestram customer.ensure, stock hold/fulfill/release,
  payment, KDS dispatch, fiscal, loyalty, notifications, fulfillment. **Guards públicos**:
  `ensure_confirmable` (exige `availability_decision.approved`), `ensure_payment_captured`.
  Confirmação por modo (immediate/auto_confirm/auto_cancel/manual) via Directive `confirmation.timeout`
  agendada respeitando calendário (`next_operational_deadline`).
- **Production lifecycle** — mesmo padrão pra WorkOrders (variantes standard/forecast/subcontract).
- **`ChannelConfig`** (`config.py`) — **CONTRATO CENTRAL**. Cascata `Channel.config ← Shop.defaults ←
  default`, validado no Admin. **8+2 aspectos:** (1) Confirmation (mode/timeout/stale_alert), (2)
  Payment (method/timing), (3) Fulfillment (timing), (4) Stock (hold_ttl/safety_margin/positions/
  check_on_commit/low_stock_threshold), (5) Notifications (backend/fallback_chain/routing), (6)
  Pricing (internal/external), (7) Editing (open/locked), (8) Rules (validators/modifiers/checks
  tri-state), +lifecycle (transitions override), +UX (`handle_label`/`handle_placeholder`).
- **Services** (~60): por superfície —
  - *Storefront*: `cart` (add/update/remove/coupon), `sessions`, `checkout` (process/defaults/
    pickup_slots), `pricing`, `*_context` (storefront/catalog/cart/checkout/customer).
  - *PDV*: `pos` (close_sale/review_sale/open|save|clear|rename|move_pos_tab/fire|cancel_fired/
    register_pos_tab/validate_manager_approval), `pos_intent`.
  - *KDS*: `kds` (dispatch/fire_lines/unfire/cancel_tickets/expedition_action).
  - *Pedidos/operador*: `availability` (decide/check/reserve/planned holds), `stock`, `payment`,
    `customer.ensure`, `cancellation`, `fulfillment`, `notification`, `loyalty`, `fiscal`,
    `operator_orders` (confirm/reject/advance/cancel/settle_delivery_cash), `order_tracking`
    (projection rica).
  - **Agentic/headless**: **`remote_mutations.run_idempotent_mutation`**, **`conversation.
    build_order_conversation → RemoteConversationProjection`**.
- **Adapters** (`get_adapter(type, method)`; resolução `Shop.integrations` → settings → default):
  payment (efi/stripe/mock), notification (manychat/email/sms/console), stock, catalog
  (+projection_ifood), promotion, fiscal, production, customer, kds, alert, pos, otp.
- **Rules** (`RuleConfig` no DB, 2 camadas: handlers estáticos boot-time + rules dinâmicas DB com
  channels/priority/enabled/whitelist). Modifiers (`modifiers.py`, ordem 10→85): pricing.item,
  discount ("maior desconto ganha"), session_total, employee_discount, delivery_fee, loyalty_redeem,
  manual_discount. Validators: BusinessHours/DeliveryZone/MinimumOrder.
- **Models**: **Shop** (singleton; branding OKLCH/fontes/logo, `opening_hours`, **`defaults`** =
  nível-loja do ChannelConfig, **`integrations`** = seleção de adapters, ~15 permissões custom),
  **Channel** (`config`), **RuleConfig**, **NotificationTemplate** (editável por evento),
  **OmotenashiCopy** (override de copy por key/moment/audience).
- **Projections** (`projections/types.py`): **`SurfaceActionProjection`** (⭐ ação canônica:
  ref/kind/label/priority/enabled/reason/href/method/payload_schema/idempotency/confirmation),
  `Availability` (enum+labels PT), OrderItem/OrderSummary/Timeline/OrderProgressStep/Fulfillment,
  PaymentMethodOption/PickupSlot/SavedAddress/AddressAutocomplete, label maps PT. Projeções ricas em
  services (order_tracking, payment_status, conversation).
- **Webhooks**: efi/pix, stripe, ifood → `dispatch(order, "on_paid")` / ingestão marketplace.
- **Notifications**: registry + `notify(event, recipient, context, backend) → NotificationResult`;
  cadeia de fallback + filtro de consentimento + Directive `notification.send`.
- **SSE push**: `_sse_emitters` (canal `stock-{ref}` em mudança de Hold/Move/Product/ListingItem) →
  storefront/PDV refrescam sem polling.

---

## Síntese — as alavancas que a nova arquitetura de superfícies deve consumir
1. **`ChannelConfig`** (8+2 aspectos) — todo comportamento por canal, editável no Admin.
2. **`Shop.integrations` / `SHOPMAN_*_ADAPTERS`** — troca de provider sem código.
3. **`RuleConfig`** — pricing/validação editáveis no DB por canal.
4. **`NotificationTemplate` + `OmotenashiCopy`** — copy/templates por evento/momento/audiência.
5. **`SurfaceActionProjection`** — contrato uniforme de "ações disponíveis agora" (web/PDV/agentic).
6. **`remote_mutations` + `conversation`** — base idempotente headless/agentic.
7. **Sessions/orders + availability + catalog/pricing + auth/customer + payments** — todos via
   services + REST, desacoplados por handle/UUID/ref.

**Pergunta-guia pra etapa B (confronto) e a auditoria das superfícies atuais:** cada feature de
benchmark que queremos → **qual alavanca acima já entrega?** Se nenhuma → é candidato a (raro)
refactor de Core, com autorização. Quase sempre será "a superfície atual não consome a alavanca
direito".

## Pendente da Etapa A
- [ ] **Observação Odoo POS** (densidade/ergonomia/caixa — benchmark PDV ao vivo).
- [ ] **Observação Shopify Agentic** (pilar agentic) + conversa "pedido-como-mensagem"/WhatsApp.
- [ ] (Etapa B) Auditoria das **superfícies atuais** (storefront/backstage/POS) — confirmar a
  hipótese do "frankenstein" (consumo ruim do contrato, não falha do Core).
</content>
