# SURFACE-QUALITY-PLAN — Elevar a superfície à qualidade do kernel

> Derivado da análise arquitetural v3/v3.1 (2026-04-21).
> Objetivo: aplicar a disciplina do kernel (pipeline claro, contratos explícitos,
> responsabilidade isolada) às surfaces storefront e backstage.

Data: 2026-04-21

---

## Relação com planos existentes

- **SPLIT-HARDENING-PLAN** (WP-H1 a WP-H6): continua válido. Este plano absorve
  WP-H6 (slim checkout.py) num escopo mais ambicioso (Intent extraction completa).
  Os WPs H1-H5 + H4 executam primeiro — são pré-requisito de higiene.
- **PROJECTION-UI-PLAN**: Fase 2-5 continua como está (projections já existem para
  catalog, cart, checkout, tracking). Este plano complementa com o lado de **entrada**
  (Intents) que o PROJECTION-UI-PLAN não cobre.
- **HARDENING-PLAN-2**: já concluído. Nenhuma sobreposição.

---

## Estrutura

```
Wave 0 — Higiene (SPLIT-HARDENING WP-H1…H5 + H4)
Wave 1 — Intent: checkout POST (substitui WP-H6)
Wave 2 — Intent: demais POSTs
Wave 3 — Omotenashi wiring nas projections
Wave 4 — Typed service results
```

---

## Wave 0 — Higiene do split

Executa SPLIT-HARDENING-PLAN WP-H1 a WP-H5 (Wave 1 paralela) + WP-H4 (Wave 2).
Sem alterações ao plano original. Referência: `docs/plans/SPLIT-HARDENING-PLAN.md`.

**Resumo rápido:**

| WP | Escopo | Complexidade |
|----|--------|-------------|
| WP-H1 | Purgar 84 templates/statics duplicados de shop/ | Baixa |
| WP-H2 | Criar adapters KDS + Alert, eliminar 10 imports diretos | Média |
| WP-H3 | Fix 33 referências stale + redistribuir tests | Baixa-Média |
| WP-H5 | Emagrecer _helpers.py (627L → ~370L) — extrair shop_status, hero, allergen, carrier | Média |
| WP-H4 | Testes arquiteturais (após WP-H2) | Média |

**Critério de saída:** `make test` green, zero imports cross-surface, zero template shadowing,
guardrails automatizados em CI.

---

## Wave 1 — Intent para o checkout POST

> Substitui e amplia WP-H6 do SPLIT-HARDENING-PLAN.
> É o maior ganho de qualidade por esforço no projeto inteiro.

### Contexto

`CheckoutView.post()` hoje: **~370 linhas** de lógica mista (L222-589).
Responsabilidades misturadas: parsing de formulário, normalização de phone, resolução
de customer, resolução de endereço salvo, validação de negócio (preorder, slot, stock,
minimum order, repricing), construção de checkout_data dict, loyalty redemption,
exception mapping, customer ensure, checkout defaults, redirect policy.

Após esta Wave: view ~100-120L (lógica HTTP), intent builder ~280L (lógica de domínio),
service ~95L (já existe, inalterado).

### WP-I1: Criar `storefront/intents/` e `CheckoutIntent`

**Entregáveis:**

1. **`storefront/intents/__init__.py`** — package

2. **`storefront/intents/types.py`** — dataclasses de Intent

```python
@dataclass(frozen=True)
class CheckoutIntent:
    """Intenção de checkout interpretada e validada."""
    session_key: str
    channel_ref: str
    customer_name: str
    customer_phone: str          # normalizado
    fulfillment_type: str        # "pickup" | "delivery"
    payment_method: str          # "pix" | "card" | "cash" | "counter"
    delivery_address: str | None
    delivery_address_structured: dict | None
    saved_address_id: int | None
    delivery_date: str | None
    delivery_time_slot: str | None
    notes: str | None
    loyalty_redeem: bool
    loyalty_balance_q: int       # 0 se não redimir
    stock_check_unavailable: bool
    idempotency_key: str

@dataclass(frozen=True)
class IntentResult:
    """Resultado de interpret_*(): intent válido OU erros."""
    intent: CheckoutIntent | None
    errors: dict[str, str]       # field → message
    form_data: dict              # para re-render em caso de erro
    repricing_warnings: list     # não-bloqueante
```

3. **`storefront/intents/checkout.py`** — `interpret_checkout(request, channel_ref) → IntentResult`

Extrai da CheckoutView.post():
- Phone parsing + normalization (L235-259)
- Name resolution via existing customer (L262-280)
- Session handle setup + stale session abandon (L289-305)
- Form field parsing (L308-314)
- Saved address resolution (L317-334)
- Payment method resolution + validation (L336-340)
- Minimum order check (L342-349)
- Address/form validation (L351-358)
- Repricing check (L361)
- Stock check (L364-371)
- Preorder validation (L403-404)
- Slot validation (L421)
- checkout_data dict construction (L440-478)
- Idempotency key generation (L479)

Cada bloco acima vira um **step nomeado** no interpret, análogo aos 9 steps do CommitService:

```python
def interpret_checkout(request: HttpRequest, channel_ref: str) -> IntentResult:
    """Interpreta o POST de checkout em um CheckoutIntent validado.

    Steps:
    1. Parse e normalize identity (phone, name)
    2. Resolve existing customer
    3. Claim session handle
    4. Parse fulfillment fields
    5. Resolve address (saved ou nova)
    6. Resolve payment method
    7. Validate business rules (minimum, preorder, slot, stock)
    8. Build checkout_data
    9. Resolve loyalty
    """
```

**O que NÃO entra no intent (fica na view):**
- Rate limit check (`request.limited`) — HTTP concern
- Cart empty check + redirect — HTTP flow
- `_render_with_errors()` — presentation
- Exception mapping de `checkout_process()` — HTTP error handling
- Customer ensure post-commit — side-effect de HTTP flow
- Checkout defaults save — side-effect de HTTP flow
- Cart session cleanup — session management
- Payment redirect vs tracking redirect — HTTP routing

4. **Refatorar `CheckoutView.post()`** para:

```python
def post(self, request: HttpRequest) -> HttpResponse:
    if getattr(request, "limited", False):
        return render(request, "storefront/partials/rate_limited.html", status=429)

    cart = CartService.get_cart(request)
    if not cart["items"]:
        # detect expired session...
        return redirect("storefront:cart")

    # ── Interpret ──
    result = interpret_checkout(request, channel_ref=CHANNEL_REF)
    if result.errors:
        return self._render_with_errors(request, cart, result.errors,
            result.form_data, result.repricing_warnings)

    # ── Process ──
    intent = result.intent
    try:
        commit_result = checkout_process(
            session_key=intent.session_key,
            channel_ref=intent.channel_ref,
            data=intent.checkout_data,
            idempotency_key=intent.idempotency_key,
        )
    except Exception as exc:
        mapped = self._map_checkout_error(exc)
        if mapped:
            return self._render_with_errors(request, cart, mapped, result.form_data)
        raise

    order_ref = commit_result["order_ref"]

    # ── Post-commit side effects ──
    self._ensure_customer(intent, order_ref)
    self._save_checkout_defaults(request, intent, order_ref)
    request.session.pop("cart_session_key", None)

    # ── Present ──
    if intent.payment_method in ("pix", "card"):
        if self._payment_initiated_ok(order_ref):
            return redirect("storefront:order_payment", ref=order_ref)
    return redirect("storefront:order_tracking", ref=order_ref)
```

5. **Simplificar `_render_with_errors()`**: hoje recebe 6-8 args avulsos + extra_form_data.
   Com IntentResult, recebe `result.form_data` (dict completo) — uma assinatura.

6. **Mover helpers privados** que NÃO são HTTP:
   - `_parse_address_data()` → `intents/checkout.py` (é parsing de POST → intent)
   - `_resolve_payment_method()` → `intents/checkout.py`
   - `_validate_checkout_form()` → `intents/checkout.py`
   - `_validate_preorder()` → `intents/checkout.py`
   - `_validate_slot()` → `intents/checkout.py`
   - `_check_repricing()` → `intents/checkout.py`
   - `_check_cart_stock()` → `intents/checkout.py`
   - `_get_session_held_qty()` → `intents/checkout.py`
   - `_is_closed_date()` → `intents/checkout.py`

   Helpers que SÃO HTTP ficam:
   - `_render_with_errors()` → view (presentation)
   - `_checkout_page_context()` → view (context assembly)
   - `_get_payment_methods()` → pode ficar na view ou ir para intent (decide no PR)
   - `_payment_method_available()` → intent (é validação de negócio)

7. **`address_picker` extraction** (originalmente WP-H6):
   - `_address_picker_context()` → `storefront/services/address_picker.py`
   - Unificar com `_account_picker_context()` de account.py

**Verificação:**
- `make test` green
- `wc -l storefront/views/checkout.py` < 250 (excluindo CheckoutOrderSummaryView e SimulateIFoodView)
- `wc -l storefront/intents/checkout.py` ~250-300
- Nenhum `request.POST.get` na view (tudo no intent)
- Checkout funcional end-to-end (manual smoke test)

**Complexidade:** Alta — é o refactor mais significativo da surface. ~600L movidas/reescritas.

**Dependência:** Nenhuma (pode rodar em paralelo com Wave 0, mas recomenda-se após WP-H5
para evitar conflitos em `_helpers.py`).

---

### WP-I1b: address_picker unificado

Extraído de WP-H6 original.

- `_address_picker_context()` de checkout.py (78L) e `_account_picker_context()` de account.py (~similar)
  → `storefront/services/address_picker.py`
- Função unificada: `build_address_picker_context(addresses, *, form_data=None, preselected_id=None)`
- Checkout e account chamam com parâmetros diferentes

**Complexidade:** Baixa. Pode ser feito junto com WP-I1 ou separado.

---

## Wave 2 — Intent para os demais POSTs

> Mesma extração, views menores. Cada WP é independente.

### WP-I2: Cart intents

**Escopo:** `cart.py` tem 5 POSTs: AddToCartView, CartSetQtyBySkuView, QuickAddView, ApplyCouponView, RemoveCouponView.

Todos são simples (10-30L cada). O ganho principal é **consistência**: todo POST segue
o padrão `intent = interpret_X(request); result = process(intent); return present(result)`.

**Entregáveis:**
- `storefront/intents/cart.py` com `interpret_add_to_cart()`, `interpret_set_qty()`,
  `interpret_apply_coupon()`
- Simplificação das views

**Complexidade:** Baixa — views já são curtas. Ganho é de padronização.

### WP-I3: Account intents

**Escopo:** `account.py` tem 10 POSTs (profile update, address CRUD, notification prefs,
food prefs, data export, account delete). Cada um 10-40L.

**Entregáveis:**
- `storefront/intents/account.py` com `interpret_profile_update()`, `interpret_address_create()`,
  `interpret_address_update()`, etc.

**Complexidade:** Baixa-Média — muitos métodos pequenos.

### WP-I4: Auth intents

**Escopo:** `auth.py` tem 4 POSTs (LoginView, RequestCodeView, VerifyCodeView, WelcomeView).
LoginView e WelcomeView fazem phone parsing similar ao checkout.

**Entregáveis:**
- `storefront/intents/auth.py` com `interpret_login()`, `interpret_verify_code()`, etc.
- Reusar phone normalization do checkout intent (extrair para `intents/_phone.py` se necessário)

**Complexidade:** Baixa.

### WP-I5: Payment + Tracking intents

**Escopo:** `payment.py` tem 1 POST (MockPaymentConfirmView). `tracking.py` tem 2 POSTs
(OrderCancelView, ReorderView).

**Entregáveis:**
- `storefront/intents/order.py` com `interpret_cancel()`, `interpret_reorder()`

**Complexidade:** Baixa.

---

## Wave 3 — Omotenashi wiring nas projections

> Não é feature nova. É conectar dados que já existem.

### Estado atual

- `OmotenashiContext` é injetado via context processor (`context_processors.py` L79)
- Projection builders NÃO acessam `OmotenashiContext`
- `build_catalog()` consulta `popular_skus()` e `happy_hour_state()` diretamente
- `favorite_category` retorna `None` (context.py L258: "to be filled by customer_summary")

### WP-O1: favorite_category no CatalogProjection

**O que faz:** Top category nos últimos 90 dias do customer → `CatalogProjection.favorite_category_ref`.
O builder consulta `OmotenashiContext.from_request(request)` para obter o customer, depois
query em OrderItem aggregation.

**Onde muda:**
- `storefront/projections/catalog.py` — builder recebe favorite e anota na projection
- `storefront/omotenashi/context.py` — `favorite_category` deixa de retornar None
- Template: highlight na seção correspondente (`x-bind:class` com Alpine)

**Complexidade:** Baixa (~15L no builder, ~20L na query).

### WP-O2: reorder_suggestion

**O que faz:** Se `days_since_last_order > 7`, injetar itens do último pedido como sugestão
no `HomeProjection` (ou `CatalogProjection`).

**Onde muda:**
- `storefront/projections/catalog.py` — campo `reorder_items: list[CatalogItemProjection]`
- Query: último Order do customer → OrderItems → map para CatalogItemProjection
- Template: seção "Pedir de novo?" condicional

**Complexidade:** Baixa-Média (~30L no builder, template novo).

### WP-O3: urgency_badge e birthday_banner

**O que faz:**
- `urgency_badge`: se `moment == "fechando"` → badge "Últimos pedidos" no header
- `birthday_banner`: se `is_birthday` → banner de aniversário

**Onde muda:**
- Ambos já são dados do `OmotenashiContext` — basta o template consumir
- Talvez incluir no `CatalogProjection` para não depender do context processor

**Complexidade:** Baixa (~10L cada).

### Decisão arquitetural: context processor vs builder

O context processor **continua** para dados puramente cross-projection:
- `greeting`, `shop_hint`, `moment` (usados no layout, não numa projection específica)

Dados que pertencem a UMA projection movem para o builder:
- `favorite_category` → CatalogProjection builder
- `reorder_items` → CatalogProjection builder (ou HomeProjection)

Dados ambíguos (usados no layout E em projections): duplicar é ok — o OmotenashiContext
é frozen e barato.

---

## Wave 4 — Typed service results

> Eleva o kernel e o orquestrador. Não bloqueia nenhuma Wave anterior.

### WP-T1: CheckoutResult

**O que faz:** `checkout.process()` passa a retornar `CheckoutResult` em vez de `dict`.

```python
@dataclass(frozen=True)
class CheckoutResult:
    order_ref: str
    payment_initiated: bool
    payment_error: str | None
```

**Onde muda:**
- `storefront/services/checkout.py` — return type
- `storefront/views/checkout.py` — consume typed result em vez de `result["order_ref"]`

**Complexidade:** Baixa.

### WP-T2: CommitResult no kernel

**O que faz:** `CommitService.commit()` retorna `CommitResult` em vez de `dict`.

```python
@dataclass(frozen=True)
class CommitResult:
    order_ref: str
    order_id: int
    committed_at: datetime
    snapshot: dict          # commitment_snapshot
```

**Onde muda:**
- `packages/orderman/services/commit.py` — return type + dataclass
- Todos os callers de `CommitService.commit()` (checkout.process, tests)

**Complexidade:** Média — toca no kernel, precisa de cuidado.
**Regra CLAUDE.md:** Este é um caso justificado de mudança no kernel — o contrato melhora
sem quebrar funcionalidade. O dict retornado hoje já tem exatamente esses campos.

### WP-T3: LifecyclePhaseResult

**O que faz:** `dispatch()` passa a retornar resultado estruturado para observabilidade.

Escopo menor: não precisa ser result object completo. Pode começar com logging
estruturado + métricas. Avaliar necessidade real antes de implementar.

**Complexidade:** Média-Alta. **Decisão: avaliar após Wave 1-2.**

---

## Ordem de execução recomendada

```
              ┌─────────┐
              │ Wave 0  │  SPLIT-HARDENING H1-H5 (paralelo)
              └────┬────┘
                   │
              ┌────▼────┐
              │ WP-H4   │  Testes arquiteturais (após H2)
              └────┬────┘
                   │
         ┌────────▼────────┐
         │ Wave 1: WP-I1   │  Intent checkout (o big refactor)
         │         WP-I1b  │  address_picker unificado
         └────────┬────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
┌───▼───┐   ┌───▼───┐   ┌───▼───┐
│ WP-I2 │   │ WP-I3 │   │ WP-I4 │  Wave 2 (paralelo)
│ cart  │   │account│   │ auth  │
└───┬───┘   └───┬───┘   └───┬───┘
    └─────────────┼─────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
┌───▼───┐   ┌───▼───┐   ┌───▼───┐
│ WP-O1 │   │ WP-O2 │   │ WP-O3 │  Wave 3 (paralelo)
│favcat │   │reorder│   │badges │
└───┬───┘   └───┬───┘   └───┬───┘
    └─────────────┼─────────────┘
                  │
         ┌───────▼────────┐
         │ Wave 4: T1, T2 │  Typed results
         └────────────────┘
```

**Solo dev note:** "paralelo" aqui significa "sem dependência entre si" — executa
sequencialmente mas em qualquer ordem. Commits vão direto em main.

---

## Estimativa

| Wave | WPs | Arquivos novos | Arquivos editados | Complexidade |
|------|-----|---------------|-------------------|-------------|
| 0 | H1-H5, H4 | 3 | ~120 (maioria deletes) | Média |
| 1 | I1, I1b | 4 | ~5 | Alta |
| 2 | I2-I5 | 4 | ~8 | Baixa-Média |
| 3 | O1-O3 | 0 | ~6 | Baixa |
| 4 | T1-T2 | 0 | ~4 | Média |

**Wave 0 + Wave 1** são o core do plano. Juntas, resolvem ~80% da dívida de qualidade
da surface. Waves 2-4 são polimento incremental — cada uma se paga sozinha.

---

## Critério de "kernel quality" (v3.1 calibrado)

Toda view POST segue:

```python
def post(self, request):
    # HTTP guards (rate limit, auth, empty cart) — fica na view
    intent_result = interpret_X(request, ...)
    if intent_result.errors:
        return self.present_errors(intent_result)
    result = process_X(intent_result.intent)
    # Post-commit side effects — fica na view
    return self.present_result(result)
```

Toda view GET segue:

```python
def get(self, request):
    projection = build_X(request, ...)
    return render(request, template, {"x": projection})
```

View resultante: **~100-120L** para checkout (não 15). Lógica HTTP legítima
(session management, rate limiting, flash messages, redirect policy) permanece na view.

**O benchmark se aplica à lógica de domínio na view:** parsing, validação de negócio,
resolução de entidades, construção de data dicts. Se está na view e não é HTTP →
deveria estar no intent ou no service.
