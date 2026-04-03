# RESTRUCTURE-APP-PLAN.md — Django Shopman

Reestruturação do shopman-app: de Handler/Directive/Registry para Flows/Services/Adapters/Rules.

**Data**: 2026-04-01
**Status**: Em aprovação
**Versão**: 3 (revisão final pós-iterações de design)

---

## Contexto

O shopman-core (Omniman, Stockman, Craftsman, etc.) é robusto, flexível e bem desenhado. O shopman-app (camada de orquestração) acumulou complexidade acidental: 18 handlers, 16 backends, 7-aspect ChannelConfig com cascata, registro em setup.py, dispatch em hooks.py, topics.py — tudo para coordenar o que, em essência, são chamadas a services do Core.

### Diagnóstico

| Problema | Evidência |
|----------|-----------|
| 13 de 18 handlers são wrappers finos (1 chamada de serviço) | PaymentCapture, NFCeEmit, LoyaltyEarn, FulfillmentCreate, etc. |
| Core subutilizado | CatalogService.price() e expand() ignorados, Listing lido diretamente |
| 600+ linhas de boilerplate de handler | Status management, payload passing, registry registration |
| Regras hardcoded em Python | Happy hour, employee discount, D-1 — sem visibilidade no admin |
| Fluxo requer navegar 8+ arquivos | hooks.py → topics.py → setup.py → handler → backend → service |
| ChannelConfig redundante com 7 aspects | Pipeline, confirmation, payment, stock, notifications, rules, flow |
| Cancelamento fragmentado em 4 lugares | Customer, operador, timeout confirmação, timeout pagamento |

### Solução

Separar radicalmente três preocupações:

1. **Coordenação** (QUANDO) → `flows.py` — Flow classes com herança Python
2. **Computação** (O QUE) → `services/` — Funções que chamam Core services + adapters
3. **Configuração** (QUANTO/QUEM) → `rules/` — Regras configuráveis via admin com RuleConfig no DB

### Princípios

- **Core é chamado, nunca contornado** — services DEVEM usar CatalogService, StockService, PaymentService, etc.
- **Semântica espelha o Core** — se Core diz `hold`, app diz `hold`. Se Core diz `fulfill`, app diz `fulfill`.
- **Directive do Core reusada como task queue** — sem modelo novo, sem redundância
- **Signal `order_changed` como contrato** — Flows recebem o signal do Core
- **Services são inteligentes** — cada service sabe se é sync ou async. Flow é puro domínio.
- **Adapters swappable via settings** — trocar provider = mudar uma linha em settings.py
- **Rules visíveis no admin** — operador vê, ativa/desativa, edita parâmetros

### Consistência Semântica

| Conceito | Core diz | App diz | Nota |
|----------|----------|---------|------|
| Reservar estoque | `StockService.create_hold()` | `stock.hold()` | Espelha Core |
| Efetivar reserva | `StockService.fulfill_hold()` | `stock.fulfill()` | Espelha Core |
| Liberar reserva | `StockService.release_hold()` | `stock.release()` | Espelha Core |
| Reverter estoque | Move com qty positiva | `stock.revert()` | `return` é reservado em Python |
| Criar intent | `PaymentService.create_intent()` | `payment.initiate()` | Verbo de domínio |
| Capturar pagamento | `PaymentService.capture()` | `payment.capture()` | Espelha Core |
| Estornar | `PaymentService.refund()` | `payment.refund()` | Smart no-op se não há pagamento |
| Garantir cliente | `CustomerService.get_or_create` | `customer.ensure()` | Verbo descritivo |
| Resolver preço | `CatalogService.price()` | `pricing.resolve()` | Inclui rules |
| Registrar pontos | `LoyaltyService.earn_points()` | `loyalty.earn()` | Espelha Core |

### Comportamento Sync/Async

Cada service sabe sua natureza. O Flow NÃO decide se é sync ou async — chama services e pronto.

| Service | Natureza | Por quê |
|---------|----------|---------|
| `stock.hold()` | **Sync** | Precisa do resultado antes de responder ao cliente |
| `stock.fulfill()` | **Sync** | Efetivação de reserva — precisa confirmar |
| `stock.release()` | **Sync** | Liberação imediata |
| `stock.revert()` | **Sync** | Devolução ao estoque |
| `payment.initiate()` | **Sync** | Precisa do QR/intent para mostrar ao cliente |
| `payment.capture()` | **Sync** | Captura efetiva |
| `payment.refund()` | **Sync** | Estorno direto (smart no-op se não há pagamento) |
| `customer.ensure()` | **Sync** | Precisa do customer_ref para o pedido |
| `fulfillment.create()` | **Sync** | Cria registro de fulfillment |
| `notification.send()` | **Async** | Cria Directive — não bloqueia request |
| `loyalty.earn()` | **Async** | Cria Directive — pode falhar sem impacto |
| `fiscal.emit()` | **Async** | Cria Directive — retry automático |
| `fiscal.cancel()` | **Async** | Cria Directive — retry automático |
| `kds.dispatch()` | **Sync** | Cria tickets — precisa estar pronto para o KDS |
| `cancellation.cancel()` | **Sync** | Transiciona status — Flow.on_cancelled cuida do resto |

### Estrutura Alvo

```
shopman/
├── models/
│   ├── shop.py                # Shop (singleton), NotificationTemplate
│   ├── rules.py               # Promotion, Coupon, RuleConfig
│   ├── alerts.py              # OperatorAlert
│   ├── kds.py                 # KDSInstance, KDSTicket
│   └── closing.py             # DayClosing
│
├── services/                  # Lógica de negócio — USA Core services
│   ├── stock.py               # hold, fulfill, release, revert → StockService + CatalogService.expand()
│   ├── payment.py             # initiate, capture, refund → PaymentService
│   ├── customer.py            # ensure → CustomerService
│   ├── notification.py        # send (async via Directive) → adapter
│   ├── fulfillment.py         # create, update → Core Fulfillment
│   ├── loyalty.py             # earn (async via Directive) → LoyaltyService
│   ├── fiscal.py              # emit, cancel (async via Directive) → adapter
│   ├── pricing.py             # resolve → CatalogService.price() + Rules engine
│   ├── cancellation.py        # cancel — ponto único para todos os paths
│   ├── kds.py                 # dispatch, on_all_tickets_done
│   └── checkout.py            # process — validação + commit + enrichment
│
├── adapters/                  # Swappable via settings
│   ├── __init__.py            # get_adapter(type, method=, channel=)
│   ├── stock_internal.py      # → Stockman
│   ├── payment_efi.py         # → EFI PIX
│   ├── payment_stripe.py      # → Stripe card
│   ├── payment_mock.py        # → dev/test
│   ├── notification_manychat.py  # → ManyChat (WhatsApp)
│   ├── notification_email.py  # → SMTP
│   └── notification_console.py   # → dev/test
│
├── rules/                     # Regras configuráveis via admin
│   ├── engine.py              # Avalia rules ativas por contexto
│   ├── pricing.py             # D1, Promotion, Employee, HappyHour
│   └── validation.py          # BusinessHours, MinOrder
│
├── flows.py                   # BaseFlow → Local/Remote/Marketplace + dispatch()
│
├── webhooks/                  # Entrada externa — split por provider
│   ├── __init__.py            # URL routing
│   ├── efi.py                 # PIX callbacks
│   ├── stripe.py              # Card callbacks
│   ├── ifood.py               # Marketplace orders
│   └── manychat.py            # WhatsApp events
│
├── admin/                     # Unfold admin
│   ├── shop.py                # Shop admin + branding
│   ├── rules.py               # Promotion, Coupon, RuleConfig admin
│   ├── orders.py              # Order admin extensions
│   ├── alerts.py              # OperatorAlert admin
│   ├── kds.py                 # KDS admin
│   ├── tasks.py               # Directives audit (readonly)
│   └── dashboard.py           # KPIs, charts, tables
│
├── web/                       # Cliente (HTMX + Alpine)
│   ├── views/
│   ├── templates/
│   └── static/
│
├── api/                       # REST (DRF)
│
├── apps.py                    # Signal wiring + handler registration (~25 loc)
└── tests/
```

### Hierarquia de Flows

```
BaseFlow                         # Ciclo completo — 10 fases, todo pedido
├── LocalFlow                    # Presencial — confirmação imediata, sem pagamento digital
│   ├── PosFlow                  # Balcão
│   └── TotemFlow                # Autoatendimento
├── RemoteFlow                   # Remoto — pagamento obrigatório, notificação ativa
│   ├── WebFlow                  # E-commerce
│   ├── WhatsAppFlow             # WhatsApp (via ManyChat)
│   └── ManychatFlow             # ManyChat genérico
└── MarketplaceFlow              # Marketplace — pagamento externo, confirmação pessimista
    └── IFoodFlow                # iFood
```

### BaseFlow Completo

```python
class BaseFlow:
    """Ciclo completo — 10 fases do lifecycle de um pedido."""

    def on_commit(self, order):
        services.customer.ensure(order)
        services.stock.hold(order)
        self.handle_confirmation(order)

    def handle_confirmation(self, order):
        mode = order.channel_config("confirmation_mode", "immediate")
        timeout = order.channel_config("confirmation_timeout", 300)
        if mode == "immediate":
            order.confirm()
        elif mode == "optimistic":
            schedule(auto_confirm, order, delay=timeout)
        elif mode == "pessimistic":
            schedule(auto_cancel, order, delay=timeout)

    def on_confirmed(self, order):
        services.payment.initiate(order)
        services.notification.send(order, "order_confirmed")

    def on_paid(self, order):
        if order.status == "cancelled":
            # Race condition: pagamento chegou depois do cancelamento
            services.payment.refund(order)
            services.alerts.create(order, "payment_after_cancel")
            return
        services.stock.fulfill(order)
        services.notification.send(order, "payment_confirmed")

    def on_processing(self, order):
        services.kds.dispatch(order)
        services.notification.send(order, "order_processing")

    def on_ready(self, order):
        services.fulfillment.create(order)
        services.notification.send(order, "order_ready")

    def on_dispatched(self, order):
        services.notification.send(order, "order_dispatched")

    def on_delivered(self, order):
        services.notification.send(order, "order_delivered")

    def on_completed(self, order):
        services.loyalty.earn(order)
        services.fiscal.emit(order)

    def on_cancelled(self, order):
        services.stock.release(order)
        services.payment.refund(order)
        services.notification.send(order, "order_cancelled")

    def on_returned(self, order):
        services.stock.revert(order)
        services.payment.refund(order)
        services.fiscal.cancel(order)
        services.notification.send(order, "order_returned")
```

### Channel Config Simplificado

```python
# Flat, sem redundância, sem pipeline
channel.config = {
    "flow": "web",                              # qual Flow class usar
    "confirmation_mode": "optimistic",          # immediate | optimistic | pessimistic
    "confirmation_timeout": 300,                # segundos
    "payment": ["pix", "card"],                 # métodos aceitos
    "stock_hold_ttl": 30,                       # minutos
    "notification_adapter": "manychat",         # adapter primário
    "notification_fallback": ["email"],          # fallback chain
    "listing_ref": "cardapio-web",              # qual catálogo
}

# Settings globais — mapeamento method → adapter (um lugar, sem redundância)
SHOPMAN_PAYMENT_ADAPTERS = {
    "pix": "shopman.adapters.payment_efi",
    "card": "shopman.adapters.payment_stripe",
    "counter": None,
    "external": None,
}
```

### apps.py — Wiring (~25 linhas)

```python
def ready(self):
    from shopman.ordering.signals import order_changed
    from shopman.flows import dispatch

    # 1. Core signal → Flows
    @receiver(order_changed)
    def on_order_changed(sender, order, event_type, **kwargs):
        if event_type == "created":
            dispatch(order, "on_commit")
        elif event_type == "status_changed":
            dispatch(order, f"on_{order.status}")

    # 2. Check handlers — contrato do ModifyService (Core cria Directives para checks)
    registry.register_directive_handler(StockCheckHandler(get_adapter("stock")))

    # 3. Async task handlers — services criam Directives, handlers executam
    registry.register_directive_handler(NotificationHandler())
    registry.register_directive_handler(FiscalHandler())
    registry.register_directive_handler(LoyaltyHandler())

    # 4. Stock signals (Core ↔ Core bridge)
    holds_materialized.connect(stock_receivers.on_holds_materialized)
    production_changed.connect(stock_receivers.on_production_changed)
    post_save.connect(stock_receivers.on_move_created, sender=Move)
```

---

## WP-R0: Documento Base + Django App Skeleton

**Objetivo**: Criar a estrutura de diretórios do novo `shopman/` app e configurar no Django.

### Entregáveis

1. Criar `shopman/` como Django app com `apps.py`
2. Criar estrutura de diretórios conforme "Estrutura Alvo" acima
3. Cada `__init__.py` com docstring explicando a responsabilidade do módulo
4. `apps.py` com `ShopmanConfig` — **NÃO conectar signals ainda** (WP-R4 faz isso)
5. Registrar app em `INSTALLED_APPS` do `project/settings.py`
6. Settings iniciais: `SHOPMAN_PAYMENT_ADAPTERS`, `SHOPMAN_NOTIFICATION_ADAPTERS`, `SHOPMAN_STOCK_ADAPTER`
7. Arquivo `adapters/__init__.py` com `get_adapter()` funcional
8. **NÃO remover** shop/ e channels/ — coexistência durante migração

### Critério de Sucesso

- `make run` funciona com o novo app registrado (mesmo que vazio)
- `get_adapter("payment", method="pix")` retorna o módulo correto
- Zero funcionalidade quebrada (app novo coexiste com o antigo)

---

## WP-R1: Models — Migração + RuleConfig

**Objetivo**: Migrar todos os models para `shopman/models/`, adicionando `RuleConfig`.

### Entregáveis

1. `models/shop.py` — Shop (singleton), NotificationTemplate
2. `models/rules.py` — Promotion, Coupon + **RuleConfig (NOVO)**:
   ```python
   class RuleConfig(models.Model):
       code = models.CharField(max_length=80, unique=True)
       rule_path = models.CharField(max_length=200)
       label = models.CharField(max_length=120)
       enabled = models.BooleanField(default=True)
       params = models.JSONField(default=dict, blank=True)
       channels = models.ManyToManyField("ordering.Channel", blank=True)
       priority = models.IntegerField(default=0)
       class Meta:
           ordering = ["priority"]
   ```
3. `models/alerts.py` — OperatorAlert
4. `models/kds.py` — KDSInstance, KDSTicket
5. `models/closing.py` — DayClosing
6. Migrações Django (usar `db_table` meta para compatibilidade)

### Critério de Sucesso

- `make migrate` sem erros
- Models acessíveis via `from shopman.models import Shop, RuleConfig`
- Testes de model passam

---

## WP-R2: Adapters — Backends como Módulos

**Objetivo**: Migrar backends de `channels/backends/` para `shopman/adapters/`.

### Entregáveis

1. `adapters/__init__.py` — `get_adapter(type, method=None, channel=None)`:
   - Channel `payment_overrides` → settings global → default
2. `adapters/stock_internal.py` — `check_availability()`, `create_hold()`, `fulfill_hold()`, `release_holds()`, `get_alternatives()`
3. `adapters/payment_efi.py` — `create_intent()`, `capture()`, `refund()`, `cancel()`, `get_status()`
4. `adapters/payment_stripe.py` — idem
5. `adapters/payment_mock.py` — idem (dev/test)
6. `adapters/notification_manychat.py` — `send()`, `is_available()`
7. `adapters/notification_email.py` — idem
8. `adapters/notification_console.py` — idem (dev/test)
9. Testes de contrato por adapter

### Critério de Sucesso

- Todos os adapters satisfazem contratos documentados
- `get_adapter()` resolve corretamente com e sem channel override

---

## WP-R3: Services — O Coração da Arquitetura

**Objetivo**: Criar services encapsulando lógica de negócio. Cada service documenta qual Core service usa.

### Entregáveis

1. `services/stock.py` — `hold(order)`, `fulfill(order)`, `release(order)`, `revert(order)`
   - USA `CatalogService.expand()` para bundles
   - USA `StockService` via adapter
   - Migrar lógica de StockHoldHandler (~140 loc) e StockCommitHandler (~40 loc)

2. `services/payment.py` — `initiate(order)`, `capture(order)`, `refund(order)`
   - `refund()` é smart no-op se não há pagamento
   - USA `PaymentService` do Core
   - Migrar lógica de PixGenerateHandler, CardCreateHandler, PaymentCaptureHandler

3. `services/customer.py` — `ensure(order)`
   - USA `CustomerService` do Core
   - Estratégia por channel type (strategy pattern leve)
   - Migrar de CustomerEnsureHandler (~160 loc)

4. `services/notification.py` — `send(order, template)` (ASYNC — cria Directive)
   - Fallback chain + consent check
   - Migrar de NotificationSendHandler (~220 loc)

5. `services/fulfillment.py` — `create(order)`, `update(fulfillment, status)`
   - Tracking URL enrichment

6. `services/loyalty.py` — `earn(order)` (ASYNC — cria Directive)

7. `services/fiscal.py` — `emit(order)`, `cancel(order)` (ASYNC — criam Directives)

8. `services/pricing.py` — `resolve(item, channel)`
   - USA `CatalogService.price()` do Core + Rules engine

9. `services/cancellation.py` — `cancel(order, reason, actor)`
   - **Ponto único** para todos os paths de cancelamento
   - Transiciona status → Flow.on_cancelled cuida das consequências

10. `services/kds.py` — `dispatch(order)`, `on_all_tickets_done(order)`
    - Cria tickets por collection/recipe
    - Auto-transiciona para READY quando todos tickets done

11. `services/checkout.py` — `process(session, channel, data)`
    - Validação + ModifyService + CommitService.commit() + enrichment

### Regra Arquitetural

```python
# Todo service DOCUMENTA quais Core services usa:
"""
Stock orchestration service.
Core: StockService (holds), CatalogService (expand)
Adapter: get_adapter("stock") → stock_internal
"""
```

### Critério de Sucesso

- Cada service testável isoladamente (adapter mockado)
- Nenhum service importa de `channels/` ou `shop/`
- Lógica de TODOS os handlers migrada sem perda

---

## WP-R4: Flows — Coordenação de Lifecycle

**Objetivo**: Implementar flows.py com hierarquia completa e conectar ao signal do Core.

### Entregáveis

1. `flows.py` com:
   - `@flow(name)` decorator + `_registry` dict
   - `dispatch(order, phase)` + receptor para `on_paid` (via webhook, não status)
   - `BaseFlow` — 10 fases completas (ver seção "BaseFlow Completo" acima)
   - `LocalFlow(BaseFlow)` → `PosFlow`, `TotemFlow`
   - `RemoteFlow(BaseFlow)` → `WebFlow`, `WhatsAppFlow`
   - `MarketplaceFlow(BaseFlow)` → `IFoodFlow`

2. `apps.py` atualizado com wiring completo (ver seção "apps.py" acima):
   - Signal `order_changed` → `dispatch()`
   - Check handlers (contrato ModifyService)
   - Async task handlers (notification, fiscal, loyalty)
   - Stock signals (Core ↔ Core bridge)

3. **Desconectar** `on_order_lifecycle` antigo de `channels/hooks.py`

### Critério de Sucesso

- Order criada → signal → dispatch → BaseFlow.on_commit() → services chamados
- Order → CONFIRMED → Flow.on_confirmed() → payment initiated
- Services async (notification, fiscal, loyalty) criam Directives e handlers processam
- Race condition "payment after cancel" tratada em on_paid
- `make test` para flows: cada flow class, cada fase

### Nota Crítica

Este WP é o **cutover**. Tudo anterior coexiste com o sistema antigo. A partir daqui, o novo app assume.

---

## WP-R5: Rules Engine — Regras Configuráveis via Admin

**Objetivo**: Engine de rules com RuleConfig no DB e admin.

### Entregáveis

1. `rules/engine.py`:
   - `get_active_rules(channel, stage)` com cache (invalidado em save signal)
   - Integração com Core Registry (registra rules ativas como modifiers/validators no boot)

2. `rules/pricing.py`:
   - `D1Discount`, `PromotionDiscount`, `EmployeeDiscount`, `HappyHour`
   - Cada rule: code, label, default_params, condition(), apply()

3. `rules/validation.py`:
   - `BusinessHours`, `MinimumOrder`
   - Cada rule: code, label, default_params, check()

4. `admin/rules.py`:
   - RuleConfig admin (toggle, params editor, canal filter)
   - Promotion/Coupon admin

5. Seed de RuleConfigs padrão

### Critério de Sucesso

- Operador desativa rule → efeito imediato no próximo pedido
- Operador edita parâmetros → efeito imediato
- Rules filtradas por canal

---

## WP-R6: Admin — Dashboard + Operacional

**Objetivo**: Migrar admin para shopman/admin/ com Unfold.

### Entregáveis

1. `admin/shop.py` — Shop admin (singleton, branding, colors)
2. `admin/orders.py` — Order extensions (fulfillment, payment)
3. `admin/alerts.py` — OperatorAlert admin
4. `admin/kds.py` — KDS admin
5. `admin/tasks.py` — Directives audit (readonly, filterable)
6. `admin/dashboard.py` — KPIs, charts, tables

### Critério de Sucesso

- Admin funcional com dashboard de KPIs reais
- Directives visíveis e filtráveis
- RuleConfig editável

---

## WP-R7: Web + API + Webhooks — Migração de Views

**Objetivo**: Migrar views para shopman/web/, shopman/api/, shopman/webhooks/.

### Entregáveis

1. `web/views/` — catalog, cart, checkout, payment, tracking, auth, account, KDS, POS
   - Checkout usa `services.checkout.process()` (lógica extraída da view)
   - Cancellation usa `services.cancellation.cancel()` (unificado)
2. `web/templates/` — migrar (imports mudam)
3. `api/views/` — cart, catalog, tracking, account
4. `webhooks/` — split por provider:
   - `webhooks/efi.py` — PIX callbacks → `services.payment` + Flow dispatch
   - `webhooks/stripe.py` — Card callbacks
   - `webhooks/ifood.py` — Marketplace orders
   - `webhooks/manychat.py` — WhatsApp events

### Critério de Sucesso

- Storefront funcional: cart → checkout → payment → tracking
- Customer self-cancel funcional via `services.cancellation.cancel()`
- Webhooks processam callbacks corretamente
- API funcional

---

## WP-R8: Testes + Cleanup

**Objetivo**: Migrar testes, garantir cobertura, remover código antigo.

### Entregáveis

1. Migrar testes existentes para `shopman/tests/`
2. Novos testes:
   - `test_flows.py` — cada flow class, cada uma das 10 fases
   - `test_services.py` — cada service com adapter mockado
   - `test_adapters.py` — contrato de cada adapter
   - `test_rules.py` — cada rule isolada + engine + admin toggle
   - `test_cancellation.py` — 4 paths convergem para 1 service
   - `test_race_conditions.py` — payment after cancel, concurrent operations
3. Testes de integração: flow completo web (cart → checkout → payment → tracking)
4. **Remover**: `shop/`, `channels/` inteiros (handlers, backends, config, presets, hooks, topics, setup)

### Critério de Sucesso

- `make test` verde com 100% dos testes migrados
- Zero imports de `shop.` ou `channels.`
- Zero arquivos residuais

---

## WP-R9: Polish + Monitoring + Documentação

**Objetivo**: Ajustes finais, monitoramento, docs.

### Entregáveis

1. **Batch shelf-life task**: Directive periódica que verifica `Batch.objects.expiring_before(today + 1)` → cria OperatorAlert
2. **Core service usage audit**: verificar TODOS os services usam Core services
3. Atualizar `CLAUDE.md` com nova estrutura
4. Atualizar `docs/reference/data-schemas.md`
5. Criar `docs/guides/flows.md` (substituindo channels.md)
6. Seed command adaptado
7. Mover planos concluídos para `docs/plans/completed/`

### Critério de Sucesso

- `make test` verde, `make lint` limpo, `make seed` + `make run` funcionais
- Documentação reflete nova arquitetura

---

## Ordem de Execução

```
WP-R0  Skeleton          (independente)
  ↓
WP-R1  Models            (depende de R0)
  ↓
WP-R2  Adapters          (depende de R0)
  ↓
WP-R3  Services          (depende de R1 + R2)
  ↓
WP-R4  Flows + Wiring    (depende de R3 — CUTOVER)
  ↓
WP-R5  Rules Engine      (depende de R1 + R3)
  ↓
WP-R6  Admin             (depende de R1 + R5)
  ↓
WP-R7  Web + API         (depende de R3 + R4)
  ↓
WP-R8  Testes + Cleanup  (depende de TUDO)
  ↓
WP-R9  Polish + Docs     (depende de R8)
```

### Estimativas

| WP | Escopo | Estimativa |
|----|--------|------------|
| R0 | Skeleton + settings | 1 sessão |
| R1 | Models + RuleConfig | 1 sessão |
| R2 | Adapters | 1-2 sessões |
| R3 | Services (o mais denso) | 2-3 sessões |
| R4 | Flows + wiring + cutover | 1-2 sessões |
| R5 | Rules engine + admin | 1-2 sessões |
| R6 | Admin + dashboard | 1-2 sessões |
| R7 | Web + API + webhooks | 2-3 sessões |
| R8 | Testes + cleanup | 2-3 sessões |
| R9 | Polish + docs | 1 sessão |
| **Total** | | **13-20 sessões** |

### Estratégia de Coexistência

- **R0 a R3**: novo app coexiste com shop/ e channels/. Zero quebra.
- **R4**: CUTOVER — desconecta hooks.py, conecta flows.py. Ponto de não retorno.
- **R5 a R7**: migra UI e rules (incremental).
- **R8**: cleanup — remove código antigo.

---

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Migração quebra funcionalidade | Coexistência até R4, testes em cada WP |
| Services ficam complexos | Regra: service ≤ 150 loc |
| Rules engine adiciona latência | Cache com invalidação em save() |
| Flow hierarchy profunda demais | Max 3 níveis. Composição > herança |
| Cancelamento fragmentado | `services.cancellation.cancel()` unifica 4 paths |
| Race condition payment/cancel | Tratada explicitamente em `BaseFlow.on_paid()` |
| KDS auto-transition | `services.kds.on_all_tickets_done()` transiciona para READY |
| Stock signals perdidos | Conectados explicitamente em apps.py |
| Adapter sem type-check | Testes de contrato por adapter |

---

## Áreas Fora de Escopo (futuro)

| Área | Status | Quando |
|------|--------|--------|
| Delivery zones / shipping | Não modelado | Quando necessário — adicionar adapter + service |
| Recurring orders | Não modelado | Futuro — novo model + service |
| Multi-tenancy | Single shop | Não planejado |
| Promotions como Core app | Em app layer | Avaliar após estabilização |
| Rename Core apps (Omniman, etc.) | Cosmético | Quando quiser, sem impacto funcional |
