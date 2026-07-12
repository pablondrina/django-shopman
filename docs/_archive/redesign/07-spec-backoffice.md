# Spec — Backoffice [Etapa C · WP2]

> Iniciativa [[project_excellence_refactor_initiative]]. Pilar **Backoffice integrado**. Ancorada na
> [Arquitetura](04-architecture.md) (contrato `Projection`/`Action`/`Presentation`), na decisão
> [D5](02-confronto.md) (Unfold canônico p/ gestão + dedicado p/ operacional, um contrato), na
> [Auditoria](01-surface-audit.md) (o `admin_console` é o **gold standard**) e no [Mapa do Core](00-core-capability-map.md).
> Inclui as **capacidades de gestão** de sync de catálogo (WP10) e anúncios/automação (WP11).
> Benchmarks: [Shopify](../research/pos-benchmarks/shopify.md) (roles/permissões, notifications,
> section-based) · [STORES](../research/pos-benchmarks/stores.md) (ecossistema, onboarding por trilha) ·
> [Take.app](../research/pos-benchmarks/take-app.md) (dashboard multicanal, toggles = nosso Core).

## 0. Posição na arquitetura (inegociável)
O Backoffice tem **duas naturezas de trabalho** (D5), ambas consumindo o **mesmo contrato**:
- **Gestão/config/CRUD/relatórios → Unfold Admin canônico.** Paga permissões/CRUD/segurança/auditoria
  de graça. **É o gold standard do projeto** (`backstage/admin_console/` — `UnfoldModelAdminViewMixin +
  TemplateView` + projection registrada + service; zero query inline). Toda página Admin custom segue o
  **Unfold Canonical Gate** (ver `.codex/skills/unfold-admin-canonical/SKILL.md` e
  `docs/engineering/unfold_canonical_policy.md`).
- **Operacional real-time bespoke → UI dedicada.** KDS station e fila do operador (latência/foco que o
  Admin não serve bem).
- **Unificador:** as duas consomem a **`Projection` de dado + `Action[]`** do orquestrador, via **um
  transporte de comando** (REST `backstage/api/operations`). A `Presentation` vive em
  `backstage/presentation/` (consome `shop.projections`, nunca o Core, nunca `shop.services`). Integração
  = contrato + marca + navegação compartilhados, **não** template/código copiado.
- **Config-driven:** comportamento por `ChannelConfig`/`RuleConfig`, copy por `OmotenashiCopy`/
  `NotificationTemplate`, branding por `Shop`, permissões por doorman/`backstage/permissions.py`.

## 1. Tenets do Backoffice (regem cada tela)
1. **Natureza define a casa:** gerenciar/configurar = Unfold; operar real-time = dedicado; nunca o
   inverso ([[feedback_no_standalone_admin]] — standalone só pra wizard/KDS/POS).
2. **Um contrato projection+comando** — Admin custom e UI dedicada consomem `Projection`+`Action`; o
   lifecycle é **single-source** (`operator_orders.next_status_for`), nunca duplicado na Presentation.
3. **Permissões unificadas:** `backstage/permissions.py` **único** (mata as 5 cópias de `_can_*`); PIN/
   roles via doorman; **manager-approval por permissão** (D1, não 4 gates fixos).
4. **Config sem deploy:** os 4 eixos (`ChannelConfig`/adapters/`RuleConfig`/templates-copy) são editáveis
   no Admin — o backoffice **é** onde a loja se configura.
5. **CRM rico de 1ª classe:** Guestman (RFM/insights/loyalty/consent/merge) é poderoso — surfar bem, não
   só CRUD.
6. **Omotenashi + acessibilidade** também no operador (copy operacional acolhedora, alvos grandes no KDS).

## 2. Superfície A — Gestão (Unfold canônico)

### 2.1 Catálogo (Offerman)
- **Projection:** produtos/listings/coleções/bundles (preço-em-contexto, publicação 2-níveis
  `is_published`/`is_sellable`, keywords/SEO, nutrição ANVISA, peso, availability_policy).
- **Gestão:** CRUD via Unfold; coleções manual vs smart (condição); publicação **por canal** (Listing↔
  Channel). Custo vem do CostBackend/Craftsman (read-only no Offerman).

### 2.2 Clientes / CRM (Guestman)
- **Projection:** customer + contatos + grupos + **RFM/insights** (recency/frequency/monetary, segment,
  churn_risk, predicted_ltv, favorite_products) + loyalty (pontos/selos/tier) + timeline + consent (LGPD).
- **Gestão:** busca/lookup multicanal, **merge** (24h reversível), grupos→pricing (`listing_ref`),
  consentimento por canal. Surfar RFM/insights como painéis, não só tabela.

### 2.3 Pedidos (Orderman) — gestão
- **Projection:** orders (9 status canônicos), `order_tracking` (dado), histórico por cliente
  (`CustomerOrderHistoryService`).
- **Gestão:** busca/filtro/detalhe; ações via `Action` (cancelar/reembolsar/avançar) que delegam aos
  services. **Sem dirigir lifecycle na view** (teste `test_backstage_views_do_not_drive_order_lifecycle`).

### 2.4 Config (os 4 eixos) — o coração da configurabilidade
- **`ChannelConfig`** (8+2 aspectos, cascata Channel←Shop←default) — dataclass-driven no Admin
  ([[feedback_dataclass_driven_admin]]).
- **`RuleConfig`** (pricing/validação por canal, incl. os rule types genéricos D-1/Happy Hour drenados da
  instância — ver WP3).
- **adapters** (`Shop.integrations`) — seleção de provider por tipo/método.
- **`NotificationTemplate`** (por evento) + **`OmotenashiCopy`** (key/moment/audience) — copy/templates
  editáveis. Taxonomia de notificação por lifecycle (Shopify: Order processing / Ready for pickup…).
- **`Shop`** (singleton): branding OKLCH/fontes/logo, opening_hours, defaults, permissões custom.

### 2.5 Pagamentos (Payman)
- **Projection:** intents/transactions (captured/refunded total, reconcile gateway). 
- **Gestão:** visão de pagamentos/reembolsos; reconciliação. Webhook = retorno confiável (PCI SAQ A).

### 2.6 Produção (Craftsman) — planejamento
- **Projection:** recipes/BOM, WorkOrders (board/planning), `suggest(date)` (demanda→produção),
  `expected(sku,date)`.
- **Gestão:** planejar/ajustar produção em lote (board), sugestão dirigida por demanda. **WorkOrder =
  produção em LOTE antecipada**, nunca por-pedido ([[feedback_production_vs_sales]]).

### 2.7 Fechamento / caixa (relatórios)
- **Projection:** `closing`/`DayClosing`/`CashRegister*` (relatório de turno **com** o esperado — ao
  contrário do caixa cego do PDV).
- **Gestão:** fechamento de dia, conferência, relatórios.

### 2.8 Estoque (Stockman)
- **Projection:** quants/moves/holds/posições, **alertas below-minimum** (déficit acionável
  [[project_stock_ux_spec]] — 1-clique, não informacional).
- **Gestão:** receber/emitir, ajustar, resolver alerta acionável.

## 3. Superfície B — Operacional dedicado (real-time)

### 3.1 KDS station
- **Projection:** `kds` (tickets/fired_lines/estações), roteamento por receita/coleção/estação.
- **Presentation:** tela de cozinha dedicada (foco/latência), expedição. **Decisão:** o **KDS-no-Admin
  é vestígio** (`admin_console/kds.py` tabular) — **aposentar**; o KDS canônico é a station dedicada
  (`views/kds_station.py`). Uma casa só.
- **Comando:** `kds.fire_lines`/`unfire`/`cancel_tickets`/`expedition_action` via `shop.services`.

### 3.2 Fila do operador (orders queue)
- **Projection:** `order_queue` (fila) **consumindo `operator_orders.next_status_for`** — **lifecycle
  single-source** (mata `NEXT_STATUS_MAP`/`_next_status` duplicados na projection).
- **Presentation:** fila com `Action[]` (confirmar/rejeitar/avançar/cancelar/settle delivery cash).
- **Comando:** `operator_orders` via `shop.services`.

## 4. Capacidades de gestão dos subsistemas outbound

### 4.1 Sync de catálogo multi-canal (gestão do WP10)
- **Projection:** status de sync **por canal** (Google Merchant / Meta Catalog [IG + WhatsApp] / TikTok
  Shop), último sync, deltas pendentes (`last_projected_skus`), erros.
- **Gestão (Unfold):** ligar/desligar canal, **full-sync**, **retração**, ver status/erros. Credenciais
  via `Shop.integrations`/settings. O sync incremental é signal-driven (`product_created`/`price_changed`
  → re-project); a gestão **observa e dispara**, não reimplementa.
- **Alavanca Core:** `CatalogService.project_catalogs()` + `CatalogProjectionBackend` +
  `PROJECTION_BACKENDS` (adapter iFood já existe como referência). **Core sagrado** — só adapters + config.

### 4.2 Anúncios sensíveis a contexto/tempo + automação (gestão do WP11)
- **Projection:** templates de anúncio (copy interpolada com contexto ao vivo — ex.: "fornada saiu", "só
  X croissants"), canais social (Google Posts / IG Stories / Threads / TikTok), regras de automação
  (gatilho→ação) por canal.
- **Gestão (Unfold) — MVP manual fácil → automação:**
  - **Compor + disparar** (manual): selecionar canais, **preview com contexto ao vivo**, disparar.
  - **Camada de regras de automação** (gatilho→ação, config-driven, on/off por canal — espelha
    `RuleConfig`). Gatilhos = eventos que o Core já emite (`holds_materialized` / Move "Recebido de
    produção" / `StockAlert` / `business_calendar`). Ação = `social.post` (directive + handler + adapters).
  - Consentimento/limites onde aplicável.
- **Alavanca Core:** directive/handler/template + **subsistema novo** de marketing (adapters social +
  templates de anúncio + regras de automação). **Core sagrado** — vive no shop/adapters + config.

## 5. Cross-cutting (config-driven, não hardcoded)
- **Permissões:** `backstage/permissions.py` único; doorman PinCredential/roles; manager-approval por
  permissão. Onboarding por trilha/canal (STORES) como padrão de ativação.
- **Copy/templates:** `OmotenashiCopy` + `NotificationTemplate`.
- **Branding:** `Shop` tokens.
- **Tudo via Unfold canônico** quando é gestão (componentes `{% component "unfold/..." %}`, nunca
  classes copiadas; modal só via `admin_console/unfold/modal.html`).

## 6. O que o Backoffice NÃO faz (anti-frankenstein)
- **Não tem 3 transportes de mutação** (HTMX-HTML / Admin-custom / REST): **um transporte** (REST +
  `Action`); a tela POS-HTMX para de montar HTML.
- **Não duplica lifecycle** (`order_queue` consome `operator_orders.next_status_for`).
- **Não copia helper de permissão 5×** (`backstage/permissions.py` único).
- **Não mantém KDS em 2 casas** (aposentar o KDS-no-Admin; station dedicada é canônica).
- **Não registra Admin por reflexão lazy** (`admin.site._registry[Order]` + `admin_view`) — segue o
  contrato oficial Unfold (`UnfoldModelAdminViewMixin`/`TemplateView`/`permission_required`/
  `.as_view(model_admin=...)`).
- **Não dirige lifecycle na view** nem importa o Core (delega a `shop.services`; lê `shop.projections`).
- **Não reimplementa sync/anúncios no Core** — adapters + config; Offerman/directives já têm o contrato.

## 7. Alavancas do Core que o Backoffice consome (referência)
- Gestão: Offerman (CatalogService), Guestman (insights/loyalty/consent/merge), Orderman
  (order_tracking/customer_orders), Payman (PaymentService/reconcile), Craftsman (CraftService
  suggest/queue/expected), Stockman (alerts below-minimum), `ChannelConfig`/`RuleConfig`/adapters/
  `NotificationTemplate`/`OmotenashiCopy`/`Shop`.
- Operacional: `kds`, `operator_orders.next_status_for` (single-source), `order_queue`, `closing`,
  `CashRegister*`.
- Outbound: `CatalogService.project_catalogs()`/`CatalogProjectionBackend` (WP10); directive `social.post`
  + adapters + templates + regras de automação (WP11).
- Auth/permissão: doorman PinCredential/roles; `backstage/permissions.py`.

## 8. Aberto (decidir na implementação / com Pablo)
- Onboarding guiado por trilha (STORES) — escopo do MVP.
- Painéis de RFM/insights (quais cortes surfacear primeiro).
- WP10: ordem dos canais (Google Merchant → Meta → TikTok?) e modelo de credenciais.
- WP11: catálogo inicial de gatilhos→ações e limites de frequência/consentimento.
