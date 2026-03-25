# Pacotes de Trabalho — Django Shopman Suite

Cada pacote é auto-contido, dimensionado para uma sessão do Claude Code,
e inclui seu prompt de execução completo. Executar na sequência.

> **Filosofia SIREL**: Simples, Robusto, Elegante.
> Core = enxuto, agnóstico, à prova de futuro.
> App = implementação real, útil no dia a dia.

---

## Visão Geral

| WP | Nome | Tipo | Deps | Sessões |
|----|------|------|------|---------|
| S1 | Payments Core — Service Layer | Feature | — | 1 |
| S2 | Payments App — Backends + Handlers | Refactor | S1 | 1 |
| S3a | Revisão Semântica — Services + Fulfillment + Topics | Refactor | — | 1 |
| S3b | Revisão Semântica — Cleanup Legado (300+ ocorrências) | Refactor | S3a | 1–2 |
| S3c | Revisão Semântica — Eliminar Duplicatas + Docs | Refactor | S3b | 1 |
| S4 | APIs REST Completas | Feature | S1, S2 | 1 |
| S5 | Crafting ↔ Ordering (Discovery) | Design | — | 1 |
| S6 | Pricing Avançado | Feature | S3a | 1 |
| S7 | Fulfillment Lifecycle | Feature | S3a | 1 |
| S9 | Crafting ↔ Ordering (Implementação) | Feature | S5, S7 | 1 |
| S8 | Documentação Final + Presets | Docs | Todos | 1 |

---

## WP-S1 — Payments Core: Service Layer de Primeira Linha

**Objetivo:** Elevar o Payments core ao mesmo nível arquitetural dos demais cores,
com service layer, signals, exceptions e lifecycle completo.

**Estado atual do Payments core:**
- 2 models: `PaymentIntent` (ref, order_ref, method, status, amount_q, gateway*) e `PaymentTransaction` (FK→Intent, type, amount_q)
- Admin básico com inline
- 202 linhas de testes de model
- Sem service, sem signals, sem exceptions tipadas
- `__init__.py` usa `default_app_config` legado (pré-Django 3.2)
- Status choices: PENDING, AUTHORIZED, CAPTURED, FAILED, CANCELLED, REFUNDED
- Method choices: PIX, COUNTER, CARD, EXTERNAL
- Sem validação de transições no save() (qualquer status pode ir para qualquer outro)

**Padrões de referência (ler antes de implementar):**

| Componente | Arquivo de referência |
|------------|----------------------|
| Service mixin | `stocking/service.py` — Stock composto de 4 mixins |
| Service facade | `offering/service.py` — CatalogService com @classmethod |
| Signals | `ordering/signals/__init__.py` — order_changed |
| Exceptions | `ordering/exceptions.py` — InvalidTransition com code+context |
| Model transitions | `ordering/models/order.py` — TRANSITIONS dict + save() validation |
| Immutability | `stocking/models/move.py` — Move nunca é atualizado |

**Entregáveis:**

### 1. `payments/exceptions.py`
```python
class PaymentError(Exception):
    """Base para erros de pagamento."""
    # Codes:
    # INTENT_NOT_FOUND, INVALID_TRANSITION, ALREADY_CAPTURED,
    # ALREADY_REFUNDED, AMOUNT_EXCEEDS_CAPTURED, CAPTURE_EXCEEDS_AUTHORIZED,
    # INTENT_EXPIRED, GATEWAY_ERROR
```
Seguir o padrão de `ordering/exceptions.py` (code + message + context).

### 2. `payments/signals/__init__.py`
```python
payment_authorized = Signal()   # (intent, order_ref, amount_q, method)
payment_captured = Signal()     # (intent, order_ref, amount_q)
payment_failed = Signal()       # (intent, order_ref, error_code, message)
payment_cancelled = Signal()    # (intent, order_ref)
payment_refunded = Signal()     # (intent, order_ref, amount_q, transaction)
```

### 3. Revisar `payments/models/intent.py`
- Adicionar `TRANSITIONS` dict (como Fulfillment e Order fazem)
- Validar transições no `save()` (como Order faz)
- Auto-setar timestamps (`authorized_at`, `captured_at`, etc.) nas transições
- Adicionar helper `transition_status(new_status)` com select_for_update

**Mapa de transições do PaymentIntent:**
```
PENDING → AUTHORIZED, FAILED, CANCELLED
AUTHORIZED → CAPTURED, CANCELLED, FAILED
CAPTURED → REFUNDED (parcial ou total)
FAILED → (terminal)
CANCELLED → (terminal)
REFUNDED → (terminal)
```

### 4. Revisar `payments/models/transaction.py`
- Garantir imutabilidade: override `save()` para bloquear updates em registros existentes
- Verificar que `on_delete=PROTECT` está correto

### 5. `payments/service.py` — PaymentService
```python
class PaymentService:
    """
    Interface pública para operações de pagamento.

    Uso:
        from shopman.payments import PaymentService, PaymentError

        intent = PaymentService.create_intent("ORD-001", 1500, "pix")
        PaymentService.authorize(intent.ref, gateway_id="efi_123")
        tx = PaymentService.capture(intent.ref)
        PaymentService.refund(intent.ref, amount_q=500, reason="item danificado")
    """

    @classmethod
    def create_intent(cls, order_ref, amount_q, method, currency="BRL",
                      gateway="", expires_at=None, **gateway_data) -> PaymentIntent

    @classmethod
    def authorize(cls, ref, *, gateway_id="", **gateway_data) -> PaymentIntent

    @classmethod
    def capture(cls, ref, *, amount_q=None) -> PaymentTransaction

    @classmethod
    def refund(cls, ref, *, amount_q=None, reason="") -> PaymentTransaction

    @classmethod
    def cancel(cls, ref, *, reason="") -> PaymentIntent

    @classmethod
    def get(cls, ref) -> PaymentIntent

    @classmethod
    def get_by_order(cls, order_ref) -> QuerySet[PaymentIntent]

    @classmethod
    def get_active_intent(cls, order_ref) -> PaymentIntent | None
    # Retorna o intent não-terminal mais recente para o pedido
```

Regras do service:
- Toda operação state-changing usa `@transaction.atomic` + `select_for_update()`
- Toda transição emite o signal correspondente
- Capture sem amount_q = capture total autorizado
- Refund sem amount_q = refund total capturado
- Refund parcial: cria Transaction(type=REFUND, amount_q=parcial)
- Idempotência: se já está no status alvo, retorna sem erro (exceto capture/refund que criam transactions)

### 6. `payments/__init__.py`
```python
"""
Shopman Payments — Payment Lifecycle Management.

Uso:
    from shopman.payments import PaymentService, PaymentError

    intent = PaymentService.create_intent("ORD-001", 1500, "pix")
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
"""
```
Lazy imports, `__all__`, sem `default_app_config`.

### 7. Testes
- `test_service.py` — lifecycle completo (create → authorize → capture → refund)
- `test_transitions.py` — cada transição válida e inválida
- `test_signals.py` — cada signal é emitido no momento certo com os kwargs certos
- `test_exceptions.py` — cada code de erro testado
- `test_immutability.py` — Transaction não pode ser updated

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S1).

Tarefa: Criar o service layer completo para o Payments core.

IMPORTANTE: Leia PRIMEIRO estes arquivos de referência para entender os padrões:
- shopman-core/stocking/shopman/stocking/service.py (composição mixin, @classmethod)
- shopman-core/offering/shopman/offering/service.py (CatalogService facade)
- shopman-core/ordering/shopman/ordering/models/order.py (TRANSITIONS, save() validation, transition_status, timestamps)
- shopman-core/ordering/shopman/ordering/signals/__init__.py (signal patterns)
- shopman-core/ordering/shopman/ordering/exceptions.py (typed exceptions)
- shopman-core/stocking/shopman/stocking/models/move.py (immutability)
- shopman-core/payments/shopman/payments/models/intent.py (model atual)
- shopman-core/payments/shopman/payments/models/transaction.py (model atual)
- shopman-core/payments/shopman/payments/tests/test_models.py (testes atuais)
- shopman-core/payments/shopman/payments/__init__.py (precisa atualizar)
- shopman-core/payments/shopman/payments/admin.py (avaliar se precisa ajustes)

Depois implemente nesta ordem:
1. payments/exceptions.py — PaymentError com codes tipados
2. payments/signals/__init__.py — 5 signals (authorized, captured, failed, cancelled, refunded)
3. Revisar payments/models/intent.py — TRANSITIONS dict, save() validation, auto-timestamps, transition_status()
4. Revisar payments/models/transaction.py — imutabilidade no save()
5. payments/service.py — PaymentService completo
6. payments/__init__.py — exports modernos (sem default_app_config)
7. Testes: test_service.py, test_transitions.py, test_signals.py, test_exceptions.py, test_immutability.py

O core é AGNÓSTICO — não sabe nada sobre Efi, Stripe ou gateways.
O PaymentService gerencia o lifecycle do Intent + cria Transactions.
Backends externos chamam o service para registrar autorizações, capturas, etc.

Filosofia: SIREL — Simples, Robusto, Elegante.

Rode os testes do payments ao final:
  cd shopman-core/payments && python -m pytest -x -v
```

---

## WP-S2 — Payments App: Refatorar Backends + Handlers

**Objetivo:** Agora que o Payments core tem service layer (WP-S1), refatorar
os backends e handlers do App para delegar ao PaymentService.

**Estado atual:**
- `channels/backends/payment_mock.py` (256 linhas) — MockPaymentBackend com storage in-memory
- `channels/backends/payment_efi.py` (380 linhas) — EfiPixBackend com OAuth2/mTLS
- `channels/handlers/payment.py` (262 linhas) — 4 handlers (PixGenerate, PixTimeout, Capture, Refund)
- `channels/web/views/payment.py` (84 linhas) — Views de QR code + polling
- Tudo manipula models diretamente, sem passar pelo PaymentService
- Protocol PaymentBackend está em `ordering/protocols.py` (deveria migrar para payments/protocols.py ou channels/protocols.py)

**Entregáveis:**

### 1. Refatorar backends
Os backends continuam falando com o gateway externo, mas a persistência
passa pelo PaymentService:
- `create_intent()` → chama `PaymentService.create_intent()` + gateway API
- `capture()` → chama gateway + `PaymentService.capture()`
- `refund()` → chama gateway + `PaymentService.refund()`

### 2. Refatorar handlers
- Handlers usam `PaymentService` ao invés de queries diretas ao model
- Ouvem signals do core (ex: `payment_captured` → dispara próximo passo do pipeline)

### 3. Criar esqueleto StripeBackend
- `channels/backends/payment_stripe.py`
- Mesma interface que EfiPixBackend
- Suporta: create_intent (card com Stripe PaymentIntent), 3D Secure, capture, refund
- Pode ser stub por agora, mas com a estrutura correta para completar depois

### 4. Mover protocol PaymentBackend
- Os dataclasses de protocol (PaymentIntent DTO, CaptureResult, etc.) estão em `ordering/protocols.py`
- Avaliar: mover para `payments/protocols.py` no core? Ou manter em ordering?
- Decisão pragmática: se mover causa muitos import changes, criar re-exports

### 5. Refatorar webhooks
- Webhook de callback do gateway chama `PaymentService.authorize()`/`capture()`
- O signal emitido pelo service dispara o restante do pipeline

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S2).

Tarefa: Refatorar backends e handlers de pagamento para usar o PaymentService do core.

IMPORTANTE: Leia PRIMEIRO:
- shopman-core/payments/shopman/payments/service.py (PaymentService — criado em WP-S1)
- shopman-core/payments/shopman/payments/signals/__init__.py (signals — criados em WP-S1)
- shopman-core/ordering/shopman/ordering/protocols.py (PaymentBackend protocol + DTOs)
- shopman-app/channels/backends/payment_mock.py
- shopman-app/channels/backends/payment_efi.py
- shopman-app/channels/handlers/payment.py
- shopman-app/channels/web/views/payment.py
- shopman-app/channels/webhooks.py
- shopman-app/channels/protocols.py
- shopman-app/tests/test_payment_contrib.py
- shopman-app/tests/test_payment_handlers.py

Depois:
1. Refatorar MockPaymentBackend e EfiPixBackend para usar PaymentService
2. Refatorar todos os handlers de pagamento para usar PaymentService
3. Criar esqueleto StripeBackend (channels/backends/payment_stripe.py)
4. Avaliar se PaymentBackend protocol deve migrar de ordering/protocols.py
5. Refatorar webhooks para usar PaymentService
6. Atualizar todos os testes

Rode make test-shopman-app ao final. Zero regressões.
```

---

## WP-S3a — Revisão Semântica: Services + Fulfillment + Topics

**Objetivo:** Resolver as 3 inconsistências semânticas mais impactantes,
todas localizadas e de baixo risco.

**Escopo:**

### 1. Padronizar nomes de Services
Atualmente:
- `Stock` (class) / `stock` (alias) — em `stocking/service.py`
- `Craft` (class) / `craft` (alias) — em `crafting/service.py`
- `VerificationService` — em `auth/services/verification.py`
- `CatalogService` — em `offering/service.py` ✅ já correto
- `PaymentService` — em `payments/service.py` ✅ já correto (após WP-S1)

Mudanças:
- `Stock` → `StockService`, manter `Stock = StockService` como alias
- `stock = Stock` → `stock = StockService` (alias de módulo mantido)
- `Craft` → `CraftService`, manter `Craft = CraftService` como alias
- `craft = Craft` → `craft = CraftService` (alias de módulo mantido)
- `VerificationService` → `AuthService`, manter `VerificationService = AuthService`
- Atualizar `__init__.py` de cada core para exportar os novos nomes

### 2. Alinhar Fulfillment com Order
Fulfillment.Status atual:
```
PENDING → IN_PROGRESS → SHIPPED → DELIVERED → CANCELLED
                          ^^
```
Deve ser:
```
PENDING → IN_PROGRESS → DISPATCHED → DELIVERED → CANCELLED
                          ^^
```
E o campo `shipped_at` → `dispatched_at`.

Isso alinha com `Order.Status.DISPATCHED` e com o vocabulário iFood.

**Atenção:** Precisa migration para renomear o campo e o choice value.

### 3. Criar `channels/topics.py`
Consolidar todas as magic strings de tópicos de directives em constantes:
```python
# channels/topics.py

# Stock
STOCK_HOLD = "stock.hold"
STOCK_RELEASE = "stock.release"

# Payment
PAYMENT_CAPTURE = "payment.capture"
PAYMENT_REFUND = "payment.refund"
PIX_GENERATE = "pix.generate"
PIX_TIMEOUT = "pix.timeout"

# Notification
NOTIFICATION_SEND = "notification.send"

# Fulfillment
FULFILLMENT_CREATE = "fulfillment.create"
FULFILLMENT_UPDATE = "fulfillment.update"

# Confirmation
CONFIRMATION_CHECK = "confirmation.check"

# Fiscal
FISCAL_EMIT = "fiscal.emit"

# Accounting
ACCOUNTING_REGISTER = "accounting.register"
```
E substituir todas as strings literais em handlers, hooks, config, presets e testes.

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S3a).

Tarefa: Revisão semântica parte 1 — Services, Fulfillment e Topics.

IMPORTANTE: Leia PRIMEIRO:
- shopman-core/stocking/shopman/stocking/service.py (Stock class)
- shopman-core/stocking/shopman/stocking/__init__.py (exports)
- shopman-core/crafting/shopman/crafting/service.py (Craft class)
- shopman-core/crafting/shopman/crafting/__init__.py (exports)
- shopman-core/auth/shopman/auth/services/verification.py (VerificationService)
- shopman-core/auth/shopman/auth/__init__.py (exports)
- shopman-core/ordering/shopman/ordering/models/fulfillment.py (SHIPPED status + shipped_at field)
- shopman-core/ordering/shopman/ordering/models/order.py (DISPATCHED — para referência)
- shopman-app/channels/handlers/ (todos — para encontrar magic strings)
- shopman-app/channels/hooks.py
- shopman-app/channels/config.py
- shopman-app/channels/presets.py

Depois:
1. Renomear Stock → StockService (manter alias Stock = StockService)
   - Atualizar stocking/service.py, stocking/__init__.py
   - Grep por "from shopman.stocking import stock" e "from shopman.stocking.service import Stock" — manter funcionando via aliases

2. Renomear Craft → CraftService (manter alias Craft = CraftService)
   - Atualizar crafting/service.py, crafting/__init__.py

3. Renomear VerificationService → AuthService (manter alias VerificationService = AuthService)
   - Atualizar auth/services/verification.py, auth/__init__.py

4. Fulfillment: SHIPPED → DISPATCHED, shipped_at → dispatched_at
   - Atualizar model, TRANSITIONS dict, migration
   - Grep por "shipped" em todo o projeto e atualizar
   - CUIDADO: criar migration para renomear campo e choice value

5. Criar channels/topics.py com constantes
   - Grep por strings literais de tópicos em handlers, hooks, config, presets, tests
   - Substituir todas as ocorrências
   - Verificar que nenhuma string literal sobrou

Rode make test ao final. TODOS os ~1878 testes devem passar.
Se algo quebrar, corrija antes de considerar completo.
```

---

## WP-S3b — Revisão Semântica: Cleanup de Termos Legados

**Objetivo:** Eliminar 300+ ocorrências de termos legados espalhados pelo código.

**Contexto:** O projeto evoluiu por muitas iterações. Os nomes originais dos módulos
foram renomeados, mas resíduos ficaram em docstrings, comments, variáveis, nomes de
funções, constraint names e admin URLs.

**Levantamento completo dos resíduos (pelo grep da sessão anterior):**

### Termos → Substitutos

| Legado | Correto | Ocorrências | Risco |
|--------|---------|-------------|-------|
| `Attending` (em docstrings/titles) | `Customers` | ~85 .py, ~14 .md | Baixo (strings) |
| `Gating` (em docstrings/titles) | `Auth` | ~74 .py, ~23 .md | Baixo (strings) |
| `omniman_session_key` (variável) | `ordering_session_key` ou `cart_session_key` | ~12 ocorrências em cart.py | Médio (lógica) |
| `_guestman_available()` (função) | `_customers_available()` | ~52 ocorrências | Médio (lógica) |
| `_stockman_available()` (função) | `_stocking_available()` | ~18 ocorrências | Médio (lógica) |
| `OffermanPricingBackend` (classe) | `CatalogPricingBackend` | ~5 ocorrências | Médio (lógica) |
| `Doorman` (em comments/routes) | `Auth` | ~19 ocorrências | Baixo (strings) |
| `GatingCustomerInfo` (protocol) | `AuthCustomerInfo` | ~30 ocorrências | Alto (interface) |
| `GatingError` / `GateError` | Manter `GateError` (é o nome do pattern) | Avaliar | — |
| `guestman_` (constraint names) | `customers_` | Em migrations | Alto (DB) |
| `guestman_customer_change` (admin URLs) | `customers_customer_change` | Em admin.py | Alto (admin) |

### Estratégia por risco

**Baixo risco (fazer primeiro):**
- Docstrings, comments, títulos de módulos
- Substituir strings "Attending" → "Customers", "Gating" → "Auth", "Doorman" → "Auth"
- Renomear `guides/gating.md` → `guides/auth.md`

**Médio risco (fazer com cuidado):**
- Renomear funções: `_guestman_available()`, `_stockman_available()`, `OffermanPricingBackend`
- Renomear variável `omniman_session_key` → `cart_session_key` (grep em testes!)
- Renomear `GatingCustomerInfo` → `AuthCustomerInfo` (grep em testes e adapters)

**Alto risco (fazer por último, com migration):**
- Constraint names com `guestman_` prefix → precisam migration `RenameConstraint`
- Admin URL reverses → precisam atualizar `app_label` ou admin site registrations
- NÃO renomear constraints em planos .md — esses arquivos documentam o histórico

**O que NÃO mudar:**
- Arquivos de planejamento (REFACTOR-PLAN.md, RESTRUCTURE-PLAN.md, CONSOLIDATION-PLAN.md) — são registro histórico
- O nome `GateError` / `Gates` — é o nome do design pattern, não um resíduo

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S3b).

Tarefa: Limpar 300+ resíduos de termos legados em todo o codebase.

ESTRATÉGIA: Trabalhar de baixo risco para alto risco. Testar a cada etapa.

ETAPA 1 — Docstrings e comments (baixo risco):
- Grep por "Attending" (capital A) em .py e .md existentes — substituir por "Customers"
  EXCETO em REFACTOR-PLAN.md, RESTRUCTURE-PLAN.md, CONSOLIDATION-PLAN.md (histórico)
- Grep por "Gating" (capital G) — substituir por "Auth" (mesma regra)
- Grep por "Doorman" — substituir por "Auth" (em comments/docstrings)
- Grep por "Omniman" / "omniman" (em comments/docstrings) — substituir por "Ordering" / "ordering"
- Renomear docs/guides/gating.md → docs/guides/auth.md, atualizar refs em docs/README.md

ETAPA 2 — Nomes de funções e classes (médio risco):
- `_guestman_available()` → `_customers_available()` em:
  - shopman-app/channels/handlers/customer.py
  - shopman-app/channels/backends/customer.py
  - Todos os testes que mockam essas funções
- `_stockman_available()` → `_stocking_available()` em:
  - shopman-app/channels/backends/stock.py
  - shopman-app/channels/web/views/_helpers.py
- `OffermanPricingBackend` → `CatalogPricingBackend` em:
  - shopman-app/channels/backends/pricing.py
  - Atualizar __all__ e imports
- `omniman_session_key` → `cart_session_key` em:
  - shopman-app/channels/web/cart.py
  - shopman-app/channels/web/views/checkout.py
  - Testes em shopman-app/tests/web/test_web_cart.py
- `GatingCustomerInfo` → `AuthCustomerInfo` em:
  - shopman-core/auth/shopman/auth/protocols/customer.py
  - Todos os arquivos que importam GatingCustomerInfo
  - Manter alias GatingCustomerInfo = AuthCustomerInfo para backward-compat

ETAPA 3 — Constraints e admin URLs (alto risco):
- Constraint names com "guestman_" em models/ do customers core:
  - Avaliar se precisa RenameConstraint migration
  - Se as migrations vão ser resetadas, apenas mudar no model e squash
- Admin URL reverses (guestman_customer_change, etc):
  - Depende do app_label no admin.py — verificar antes de mudar

Rode make test após CADA ETAPA. Se algo quebrar, corrija antes de prosseguir.
```

---

## WP-S3c — Revisão Semântica: Eliminar Duplicatas + Atualizar Docs

**Objetivo:** Eliminar módulos duplicados e atualizar docs de referência.

**Escopo:**

### 1. Eliminar `StorefrontConfig` duplicado
- `shop/models.py` tem `Shop` (singleton com config JSON completo)
- `channels/web/models.py` tem `StorefrontConfig` (singleton com branding web)
- Migrar campos exclusivos de StorefrontConfig → `Shop.config["web_branding"]` ou `Channel.config`
- Eliminar model StorefrontConfig + migration
- Atualizar context_processors e templates

### 2. Eliminar `channels/confirmation.py` duplicado
- `channels/confirmation.py` duplica lógica de `channels/config.py` (ChannelConfig)
- Unificar em `ChannelConfig.effective()` ou similar
- Atualizar todos os call-sites

### 3. Atualizar docs de referência
- `docs/reference/glossary.md` — adicionar termos de Payments, remover refs legadas
- `docs/reference/signals.md` — adicionar payment_* signals, corrigir nomes de módulos
- `docs/reference/protocols.md` — atualizar PaymentBackend, corrigir nomes legados
- `docs/reference/settings.md` — atualizar configs
- `docs/reference/errors.md` — adicionar PaymentError

### 4. Atualizar `__title__` e docstrings dos `__init__.py`
- `customers/__init__.py` diz "Shopman Attending" → "Shopman Customers"
- `auth/__init__.py` diz "Shopman Gating" → "Shopman Auth"

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S3c).

Tarefa: Eliminar duplicatas e atualizar documentação de referência.

IMPORTANTE: Leia PRIMEIRO:
- shopman-app/shop/models.py (Shop singleton)
- shopman-app/channels/web/models.py (se existe StorefrontConfig)
- shopman-app/channels/web/context_processors.py
- shopman-app/channels/confirmation.py
- shopman-app/channels/config.py (ChannelConfig)
- shopman-app/channels/confirmation_hooks.py
- docs/reference/glossary.md
- docs/reference/signals.md
- docs/reference/protocols.md
- docs/reference/settings.md
- docs/reference/errors.md
- shopman-core/customers/shopman/customers/__init__.py
- shopman-core/auth/shopman/auth/__init__.py

Depois:
1. Avaliar StorefrontConfig vs Shop — migrar ou eliminar
2. Avaliar confirmation.py vs config.py — unificar
3. Atualizar TODOS os docs de referência com estado real do código
4. Corrigir __title__ e docstrings nos __init__.py dos cores

Rode make test ao final.
```

---

## WP-S4 — APIs REST Completas

**Objetivo:** Expor APIs REST para todos os cores e criar endpoints de
carrinho/checkout no App.

**Estado atual:**
- Expostos: `api/ordering/`, `api/offering/`, `api/webhooks/`
- Faltam: customers, stocking, auth, payments
- Não existe API de carrinho/checkout (tudo via HTMX web views)

**Escopo:**

### 1. Customers API (core)
- Verificar se `customers/api/` já existe no core
- Se sim, apenas expor em `project/urls.py`
- Se não, criar: list, retrieve, create, update, search
- Filtros: grupo, status, documento

### 2. Stocking API (core)
- Verificar se `stocking/api/` já existe no core
- Endpoints: availability check (sku + qty), quant listing, alert listing

### 3. Auth API (core)
- Endpoint: `POST request_code` (phone/email), `POST verify_code`
- Retorna customer info + session/token

### 4. Payments API (core)
- Read-only: get intent status, list intents by order
- Criação é via handlers/backends, não via API

### 5. Cart/Checkout API (App)
- `POST /api/cart/items/` — add item
- `PATCH /api/cart/items/{line_id}/` — update qty
- `DELETE /api/cart/items/{line_id}/` — remove
- `GET /api/cart/` — get cart
- `POST /api/checkout/` — commit order
- Session key via header ou cookie

### 6. Registrar rotas em `project/urls.py`

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S4).

Tarefa: Completar APIs REST de todos os cores + criar API de carrinho/checkout.

Verifique primeiro o que já existe (api/ dirs em cada core):
- shopman-core/customers/shopman/customers/api/
- shopman-core/stocking/shopman/stocking/api/
- shopman-core/auth/shopman/auth/ (views existentes?)
- shopman-core/payments/shopman/payments/ (sem api/ ainda)

Para cada core que já tem api/, apenas exponha em project/urls.py.
Para os que não têm, crie views DRF + serializers + urls.
Para o App, crie Cart/Checkout API (channels/api/).

Use drf-spectacular para schema/docs (já configurado).
Siga os padrões existentes em offering/api/ e ordering/api/.

Rode make test ao final.
```

---

## WP-S5 — Integração Crafting ↔ Ordering (Discovery + Design)

**Objetivo:** Entender o modelo de negócio real para produção e projetar
a integração Crafting ↔ Ordering. **NÃO IMPLEMENTAR — apenas design.**

**Contexto CRÍTICO:**
- O Crafting core está completo: Recipe, WorkOrder, plan/close/void/adjust
- Integração com Stocking existe: `crafting/contrib/stocking/` (handles production_changed → stock realize)
- MAS: Crafting NÃO está conectado ao ciclo de pedidos
- O usuário disse: "Nem sempre é o pedido que cria a ordem de produção"
- Modelo de negócio é diferente do padrão e precisa ser entendido

**Estado atual do Crafting:**
- `craft.plan(recipe, quantity, date)` → cria WorkOrder
- `craft.close(wo, produced=N)` → finaliza, chama InventoryProtocol (consume ingredients, receive output)
- Signal `production_changed` → `contrib/stocking/handlers.py` → cria/realiza Quants no Stocking
- `source_ref` no WorkOrder: pode ser "order:789", "forecast:Q1", "manual:operador"
- Demand backend: `OmnimanDemandBackend` consulta histórico de pedidos para sugerir produção
- Nenhum handler automático liga pedido → WorkOrder

**Perguntas que a sessão deve fazer ao usuário:**
1. Como funciona a produção na prática?
   - Produz de manhã (batch planning) e vende o dia todo? (padaria clássica)
   - Ou produz sob demanda quando chega pedido? (confeitaria custom)
   - Ou ambos? (linha regular + encomendas especiais)

2. WorkOrder é criado por quem?
   - Operador via admin? (manual)
   - Sistema automático baseado em estoque/demanda? (MRP)
   - Pedido específico? (sob demanda)

3. Quando um pedido entra e não tem estoque físico, o que acontece?
   - Hold de demanda (quant futuro)?
   - Recusa o pedido?
   - Cria WorkOrder automático?

4. O hold de demanda (target_date futuro) é usado em que situação?
   - "Reservar 50 croissants para sexta" = hold de demanda
   - Quando o WO fecha, realize converte → estoque real

5. Existe "programação de produção" diária?
   - `craft.suggest()` usa histórico para recomendar
   - Operador aprova/ajusta e executa `craft.plan()`

6. Como a padaria Nelson opera na prática?

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S5).

ESTE PACOTE É DE DISCOVERY — NÃO implemente nada.

Leia o Crafting core completo para entender as capacidades:
- shopman-core/crafting/shopman/crafting/service.py (4 verbos: plan, adjust, close, void)
- shopman-core/crafting/shopman/crafting/services/ (scheduling, execution, queries)
- shopman-core/crafting/shopman/crafting/models/ (Recipe, WorkOrder, WorkOrderItem, WorkOrderEvent)
- shopman-core/crafting/shopman/crafting/protocols/ (InventoryProtocol, DemandProtocol)
- shopman-core/crafting/shopman/crafting/contrib/stocking/ (produção → estoque)
- shopman-core/crafting/shopman/crafting/contrib/demand/ (demanda → sugestões)
- shopman-core/stocking/shopman/stocking/service.py (plan, replan, realize, hold, fulfill)

Depois, PERGUNTE ao usuário as 6 questões listadas no WP-S5 do WORKPACKAGES.md.

Com base nas respostas, documente:
- O fluxo real de produção do negócio
- Pontos de integração necessários (Crafting ↔ Ordering ↔ Stocking)
- Proposta de design: signals, handlers, configuração
- O que pode ficar no Core vs o que fica no App
- ADR draft com a decisão

Salve o resultado em docs/decisions/adr-007-crafting-ordering-integration.md (DRAFT).
NÃO implemente código — apenas projete e documente.
```

---

## WP-S6 — Pricing Avançado

**Objetivo:** Explorar o potencial completo do Offering core para pricing
e implementar regras de negócio no App.

**Estado atual:**
- `CatalogService.price()` suporta: preço base, listing price, min_qty
- O App só usa lookup direto de base_price_q
- ListingItem tem campo min_qty que não está sendo explorado
- D-1 discount existe como lógica ad-hoc em `_helpers.py`

**Escopo:**

### 1. Pricing modifier que respeita min_qty
- Se qty >= ListingItem.min_qty, aplica preço do item com maior min_qty que atinge
- Cascata: 1 un = R$5, 3+ = R$4, 10+ = R$3.50

### 2. Promoções (model no App)
- `Promotion(name, type=PERCENT|FIXED, value, valid_from, valid_until, skus[], collections[], min_order_q)`
- Modifier que aplica promoções ativas

### 3. Cupons (model no App)
- `Coupon(code, promotion FK, max_uses, uses_count, is_active)`
- Endpoint para aplicar cupom
- Modifier que aplica desconto

### 4. D-1 discount formalizado
- Mover de `_helpers.py` para pricing modifier configurável

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S6).

Tarefa: Implementar pricing avançado no App layer.

Leia PRIMEIRO:
- shopman-core/offering/shopman/offering/service.py (CatalogService.price, min_qty)
- shopman-core/offering/shopman/offering/models/listing.py (ListingItem.min_qty)
- shopman-app/channels/backends/pricing.py (backends atuais)
- shopman-app/channels/web/views/_helpers.py (D-1 discount)

Implemente:
1. Pricing modifier que respeita min_qty do ListingItem (cascata)
2. Model Promotion + modifier
3. Model Coupon + endpoint + modifier
4. Formalizar D-1 como modifier configurável

Rode make test ao final.
```

---

## WP-S7 — Fulfillment Lifecycle Completo

**Objetivo:** Completar o ciclo de fulfillment com handlers, auto-sync com Order,
e notificações.

**Pré-requisito:** WP-S3a (Fulfillment.SHIPPED já renomeado para DISPATCHED).

**Estado atual:**
- Fulfillment model: PENDING → IN_PROGRESS → DISPATCHED → DELIVERED → CANCELLED (após WP-S3a)
- FulfillmentCreateHandler apenas cria com status PENDING
- Não há handlers para transições subsequentes
- Não há auto-sync entre Fulfillment e Order status

**Escopo:**

### 1. Handler `fulfillment.update`
- Directive payload: `{fulfillment_id, new_status, tracking_code?, carrier?}`
- Executa transição no model
- Auto-seta timestamps

### 2. Auto-sync Order ↔ Fulfillment
- Fulfillment → DISPATCHED: Order → DISPATCHED (se `flow.auto_sync_fulfillment`)
- Fulfillment → DELIVERED: Order → DELIVERED (se configurado)
- Configurável via `ChannelConfig.flow`

### 3. Notificações por transição
- DISPATCHED → notificação com tracking info
- DELIVERED → notificação de confirmação

### 4. Tracking info
- Enricher: quando carrier é conhecido, gerar tracking_url automaticamente

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S7).

Tarefa: Completar o lifecycle de Fulfillment no App.

Leia PRIMEIRO:
- shopman-core/ordering/shopman/ordering/models/fulfillment.py
- shopman-core/ordering/shopman/ordering/models/order.py (Status, transitions, transition_status)
- shopman-app/channels/handlers/ (todos, especialmente fulfillment.py se existir)
- shopman-app/channels/hooks.py (on_order_lifecycle)
- shopman-app/channels/config.py (ChannelConfig)
- shopman-app/channels/topics.py (constantes — criadas em WP-S3a)

Implemente:
1. Handler fulfillment.update para transições
2. Auto-sync Fulfillment ↔ Order (configurável via ChannelConfig.flow)
3. Notificações por transição de fulfillment (DISPATCHED, DELIVERED)
4. Tracking URL auto-generation quando carrier é conhecido

Rode make test ao final.
```

---

## WP-S8 — Documentação Final + Presets Enriquecidos ✅

**Objetivo:** Atualizar toda a documentação para refletir o estado final
do sistema e enriquecer presets com pipelines completos.

**Escopo:**

### 1. `docs/architecture.md`
- Incluir `shop/` app
- Incluir Payments core
- Atualizar diagrama de camadas
- Remover referências a nomes legados

### 2. `docs/reference/` (todos)
- `protocols.md` — PaymentBackend atualizado, nomes corretos
- `settings.md` — configs de shop, channels
- `signals.md` — payment_* signals, nomes de módulos corretos
- `commands.md` — seed, cleanup commands
- `errors.md` — PaymentError, todos os códigos

### 3. `docs/guides/`
- Novo: `payments.md` — guia de integração de pagamentos
- Atualizar: `offering.md`, `auth.md` (ex-gating), `customers.md` (ex-attending)

### 4. Presets enriquecidos
- Cada preset com pipeline completo (quais handlers executam, em que ordem)
- Documentar: "o que cada preset faz de diferente"

### 5. ADR-006: Payments Core Design
- Por que service layer agnóstico
- Por que protocols vivem em ordering (ou payments)
- Trade-offs de Intent model vs inline em Order.data

### 6. CLAUDE.md
- Atualizar estrutura do projeto
- Garantir que reflete o estado real pós-refatoração

**Prompt de execução:**

```
Leia CLAUDE.md e WORKPACKAGES.md (WP-S8).

Tarefa: Atualizar TODA a documentação e enriquecer presets.

Leia o estado atual de CADA doc em docs/ e compare com o código implementado.
Para cada doc desatualizado:
- Identifique o que mudou
- Atualize com o estado real
- Remova referências a termos legados

Crie docs novos:
- docs/guides/payments.md
- docs/decisions/adr-006-payments-core-design.md

Enriqueça presets.py com pipelines completos e documentação inline.
Atualize CLAUDE.md com estrutura real do projeto.

NÃO invente features — documente apenas o que existe no código.
```

---

## WP-S9 — Crafting ↔ Ordering: Implementação (ADR-007)

**Objetivo:** Implementar os gaps identificados no ADR-007 para completar a integração
entre produção planejada e pedidos antecipados (encomendas).

**Pré-requisito:** WP-S5 (ADR-007 aprovado), WP-S7 (fulfillment completo).

**Referência:** `docs/decisions/adr-007-crafting-ordering-integration.md`

**O que já funciona (90% do fluxo):**
- `StockHoldHandler` cria holds com `target_date` para pedidos futuros
- `on_holds_materialized` auto-comita sessions quando `realize()` converte estoque planejado → físico
- `confirmation_hooks.on_order_created` dispara pagamento (PIX QR / card intent)
- `craft.suggest()` incorpora encomendas via `DemandBackend.committed()`
- `stock.hold()` vincula ao Quant planejado quando disponível
- Fermata: session fica OPEN aguardando materialização

**O que falta (gaps do ADR-007):**

### 1. Margem de segurança na disponibilidade planejada (CRÍTICO)

**Problema:** `StockingBackend.check_availability()` retorna `stock.available()` sem
descontar a margem de segurança. Para estoque físico (balcão), isso é aceitável.
Para estoque **planejado** (encomendas), pode causar overselling.

**Exemplo:**
```
Planejado: 100 croissants para sexta
Já encomendados: 30 (holds de demanda)
Margem segurança: 20% = 20
Disponível correto: 100 - 30 - 20 = 50
Disponível atual (bug): 100 - 30 = 70 ← vende 20 a mais que deveria
```

**Implementação:**

Em `channels/backends/stock.py`, método `check_availability()`:
```python
def check_availability(self, sku, quantity, target_date=None, **kwargs):
    available = stock.available(sku, target_date=target_date)

    # Aplicar margem de segurança para estoque planejado (encomendas)
    if target_date and target_date > date.today():
        margin = get_safety_margin(self.channel)
        available = max(Decimal("0"), available - margin)

    return AvailabilityResult(
        available=available >= quantity,
        available_qty=available,
        ...
    )
```

**`get_safety_margin()` já existe** em `channels/confirmation.py` (linhas 111-131).
Faz cascata: product_data → channel config → settings → 0.

**Configuração via `ChannelConfig.stock.safety_margin`** (já existe no dataclass, valor padrão 0).
O preset Nelson deve definir um valor sensato (ex: 20 = 20 unidades).

**Atenção:** A margem é em **unidades absolutas** por SKU, não percentual.
O `craft.suggest()` já tem seu próprio `SAFETY_STOCK_PERCENT` para o planejamento.
A margem aqui é "quanto reservar para venda no balcão" — conceito diferente.

### 2. Release de holds planejados no cancelamento (ALTO)

**Problema:** `_on_cancelled()` em `confirmation_hooks.py` envia notificação mas
**não libera os holds de demanda**. Se o cliente cancela uma encomenda, os holds
planejados ficam pendurados até expirar (ou nunca, se TTL foi removido para holds planejados).

**Implementação:**

Em `channels/confirmation_hooks.py`, método `_on_cancelled()`:
```python
def _on_cancelled(order, channel):
    # Liberar holds de demanda associados ao pedido
    session_key = order.data.get("session_key")
    if session_key:
        backend = get_stock_backend(channel)
        backend.release_holds_for_reference(session_key)

    # Notificação existente continua
    _enqueue_notification(order, "order_cancelled", channel)
```

**`release_holds_for_reference()`** já existe em `StockingBackend` (linhas 201-224).
Faz batch release de todos os holds com `metadata.reference == session_key`.

**Verificar:** Se a Order já tem `data["holds"]` com hold_ids explícitos, pode ser mais
preciso liberar por hold_id. Avaliar qual abordagem é mais robusta.

### 3. TTL da fermata — timeout de sessions com holds planejados (MÉDIO)

**Problema:** Se a produção nunca materializa (WO cancelado/adiado), a session
fica pendurada indefinidamente. O hold planejado teve seu `expires_at` removido
pelo `StockingBackend.create_hold()` (linha 109-113).

**Implementação:**

Ouvir o signal `production_changed` com status `voided`:
```python
# channels/handlers/_stock_receivers.py

@receiver(production_changed)
def on_production_voided(sender, work_order, status, **kwargs):
    """Quando produção é cancelada, notificar sessions em fermata."""
    if status != "voided":
        return

    sku = work_order.output_ref
    target_date = work_order.scheduled_date

    # Buscar holds de demanda vinculados a Quants planejados desse SKU/data
    holds = Hold.objects.filter(
        quant__product__sku=sku,
        quant__target_date=target_date,
        status="pending",
    )

    for hold in holds:
        session_key = hold.metadata.get("reference")
        if session_key:
            # Notificar cliente: "produção cancelada, pedido não poderá ser atendido"
            _notify_fermata_cancelled(session_key, sku, target_date)
            # Liberar hold
            stock.release(f"hold:{hold.pk}", reason="Produção cancelada")
```

**Alternativa mais simples:** Definir TTL longo (48h) em holds planejados ao invés
de remover `expires_at`. Assim, se nada acontecer em 48h, o hold expira sozinho.
Implementar via config: `ChannelConfig.stock.planned_hold_ttl_hours = 48`.

### 4. Testes — Cenários do ADR-007

**Cenário 1:** Venda normal (estoque físico) — já testado, apenas validar.

**Cenário 2:** Encomenda antecipada (pré-planejamento)
```python
def test_advance_order_creates_demand_hold(self):
    """Pedido com delivery_date futuro cria hold de demanda."""
    session = create_session(delivery_date=friday)
    handler = StockHoldHandler(session, channel)
    result = handler.handle(sku="croissant", qty=50)
    assert result.is_planned is True
    # Hold existe sem quant físico

def test_suggest_includes_advance_orders(self):
    """suggest() contabiliza encomendas via committed()."""
    # Criar hold de demanda para sexta
    stock.hold(50, croissant, target_date=friday)
    suggestions = craft.suggest(friday)
    # committed=50 deve aparecer no cálculo
    assert suggestions[0].basis["committed"] == 50

def test_fermata_autocommit_on_materialization(self):
    """Session em fermata auto-comita quando produção materializa."""
    # Setup: session com hold planejado
    # Action: craft.close() → realize()
    # Assert: session comitada, order criado
```

**Cenário 3:** Encomenda tardia (pós-planejamento, com margem)
```python
def test_late_order_respects_safety_margin(self):
    """Pedido pós-planejamento desconta margem de segurança."""
    # Setup: 100 planejados, 30 já encomendados, margem=20
    stock.plan(100, croissant, friday, vitrine)
    stock.hold(30, croissant, target_date=friday)  # encomendas existentes
    channel.config["stock"]["safety_margin"] = 20

    backend = StockingBackend(channel)
    result = backend.check_availability("croissant", 10, target_date=friday)
    assert result.available is True
    assert result.available_qty == 50  # 100 - 30 - 20

def test_late_order_rejected_when_over_margin(self):
    """Pedido pós-planejamento rejeitado quando excede disponível."""
    # Setup: 100 planejados, 30 já encomendados, margem=20
    # Disponível: 50
    backend = StockingBackend(channel)
    result = backend.check_availability("croissant", 60, target_date=friday)
    assert result.available is False
```

**Cenário 4:** Cancelamento libera holds
```python
def test_cancel_releases_planned_holds(self):
    """Cancelar encomenda libera holds de demanda."""
    # Setup: session com hold planejado
    # Action: order cancelado
    # Assert: hold liberado, stock disponível restaurado
```

**Cenário 5:** Produção cancelada notifica fermata
```python
def test_voided_production_notifies_fermata_sessions(self):
    """Produção voided libera holds e notifica sessions em fermata."""
    # Setup: session em fermata, WO planejado
    # Action: craft.void(wo)
    # Assert: hold liberado, session notificada
```

**Prompt de execução:**

```
Leia CLAUDE.md, WORKPACKAGES.md (WP-S9) e docs/decisions/adr-007-crafting-ordering-integration.md.

Tarefa: Implementar os gaps do ADR-007 para completar a integração Crafting ↔ Ordering.

IMPORTANTE: Leia PRIMEIRO estes arquivos para entender o estado atual:
- shopman-app/channels/backends/stock.py (StockingBackend.check_availability — GAP #1)
- shopman-app/channels/confirmation.py (get_safety_margin — já existe, não integrado)
- shopman-app/channels/confirmation_hooks.py (_on_cancelled — GAP #2)
- shopman-app/channels/handlers/_stock_receivers.py (on_holds_materialized — funciona)
- shopman-app/channels/handlers/stock.py (StockHoldHandler — funciona)
- shopman-app/channels/config.py (ChannelConfig.stock.safety_margin — já existe)
- shopman-core/stocking/shopman/stocking/services/holds.py (hold — para referência)
- shopman-core/stocking/shopman/stocking/services/planning.py (realize — para referência)
- shopman-core/crafting/shopman/crafting/services/queries.py (expected, suggest — para referência)
- shopman-core/crafting/shopman/crafting/signals/__init__.py (production_changed — para GAP #3)

Depois implemente nesta ordem:

1. GAP #1 — Margem de segurança em check_availability():
   - Em StockingBackend.check_availability(), quando target_date é futuro,
     subtrair get_safety_margin(channel) do available
   - Usar max(0, available - margin) para não ficar negativo
   - get_safety_margin() já existe em channels/confirmation.py — apenas chamar

2. GAP #2 — Release de holds no cancelamento:
   - Em _on_cancelled() de confirmation_hooks.py, chamar
     backend.release_holds_for_reference(session_key) antes da notificação
   - release_holds_for_reference() já existe no StockingBackend
   - Extrair session_key de order.data["session_key"]

3. GAP #3 — TTL da fermata (produção cancelada):
   - Ouvir signal production_changed no _stock_receivers.py
   - Quando status="voided", buscar holds de demanda vinculados ao SKU/data
   - Liberar holds e notificar sessions em fermata
   - Adicionar planned_hold_ttl_hours ao ChannelConfig.stock (default: 48)

4. Atualizar preset Nelson:
   - Definir safety_margin sensato (ex: 10 unidades)
   - Definir planned_hold_ttl_hours (ex: 48)

5. Testes para os 5 cenários do ADR-007:
   - test_advance_order_creates_demand_hold
   - test_suggest_includes_advance_orders
   - test_fermata_autocommit_on_materialization
   - test_late_order_respects_safety_margin
   - test_late_order_rejected_when_over_margin
   - test_cancel_releases_planned_holds
   - test_voided_production_notifies_fermata_sessions

6. Atualizar ADR-007: mudar status de DRAFT para ACCEPTED,
   marcar gaps como "Implementado em WP-S9"

Princípios:
- Todo código novo fica no App layer (channels/) — NUNCA no Core
- O Crafting core NÃO importa nada do Ordering
- Reutilizar o que já existe (get_safety_margin, release_holds_for_reference, etc.)
- SIREL: Simples, Robusto, Elegante

Rode make test-shopman-app ao final. Zero regressões.
```

---

## Notas de Execução

### Ordem recomendada de execução

```
S1 (Payments Core)     ←── primeiro, maior valor
  ↓
S2 (Payments App)      ←── depende de S1
  ↓
S3a (Semântica leve)   ←── pode rodar antes ou depois de S1/S2
  ↓
S3b (Cleanup legado)   ←── mecânico, mas grande
  ↓
S3c (Duplicatas+Docs)  ←── depende de S3a/S3b
  ↓
S4 (APIs)              ←── depende de S1/S2
  ↓
S5 (Crafting Discovery) ←── pode rodar a qualquer momento
  ↓
S6 (Pricing)           ←── depende de S3a (topics)
  ↓
S7 (Fulfillment)       ←── depende de S3a (DISPATCHED rename)
  ↓
S9 (Crafting ↔ Ordering) ←── implementa ADR-007, depende de S5/S7
  ↓
S8 (Docs Final)        ←── depois de tudo
```

### Convenções para todas as sessões
- **Ler CLAUDE.md** sempre — contém as regras ativas do projeto
- **`ref` not `code`** — identificadores textuais são `ref`
- **Centavos com `_q`** — valores monetários são inteiros em centavos
- **Zero resíduos** — ao renomear, limpar TUDO
- **SIREL** — Simples, Robusto, Elegante
- **Rodar testes** ao final de cada pacote
