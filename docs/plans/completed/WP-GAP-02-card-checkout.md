# WP-GAP-02 — Card checkout via Stripe Checkout (redirect, delegação total)

> Entrega incremental para remediar gap identificado em [docs/reference/system-spec.md](../reference/system-spec.md). Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma (Stripe webhook já verificado real)
**Severidade original**: 🔴 Alta. Backend Stripe + webhook prontos, só falta ligar checkout ao Stripe Checkout hospedado.

---

## Contexto

### Decisão de arquitetura (registrada)

**Delegação total ao Stripe via Stripe Checkout hospedado.** Servidor Shopman cria um `CheckoutSession` via API, retorna a URL pública do Stripe, cliente clica botão e é redirecionado para `checkout.stripe.com` — UI inteira é do Stripe. Após pagamento, Stripe redireciona para `success_url` nosso. PCI scope = **SAQ A**. Sem stripe.js no nosso HTML, sem iframe Elements, sem Appearance API, sem Alpine component de pagamento. A "UI card" do nosso lado é um botão que dispara redirect.

Esta decisão substitui proposta inicial de PaymentElement/iframe — simplificação deliberada.

### O que já existe

- Payman aceita `method=CARD` em `PaymentIntent.Method`.
- Adapter `payment_stripe` em [shopman/shop/adapters/payment_stripe.py](../../shopman/shop/adapters/payment_stripe.py) implementa o protocol (verificar se cria `PaymentIntent` direto ou `CheckoutSession`).
- `SHOPMAN_PAYMENT_ADAPTERS["card"] = "shopman.shop.adapters.payment_stripe"` registrado.
- Webhook real em [shopman/shop/webhooks/stripe.py](../../shopman/shop/webhooks/stripe.py) — signature verify, lookup intent, dispatch `on_paid`.
- `STRIPE_PUBLISHABLE_KEY` + `STRIPE_SECRET_KEY` em [config/settings.py](../../config/settings.py).
- CSP permite `api.stripe.com` (não precisa de `js.stripe.com` neste modelo, mas já está se precisar fallback).
- Canais `remote`/`delivery`/`web` aceitam `method=["pix","card"]` via `Channel.config`.

### O que está faltando (de fato, escopo mínimo)

1. Adapter `payment_stripe.create_intent` deve criar um **Stripe Checkout Session** (não apenas `PaymentIntent`), retornando `session_url` em `gateway_data`. Verificar signature atual e ajustar se estiver só com `PaymentIntent`.
2. `payment.initiate(order)` no orquestrador ([shopman/shop/services/payment.py](../../shopman/shop/services/payment.py)) deve persistir `checkout_url` em `order.data["payment"]["checkout_url"]` para o front renderizar.
3. Template [storefront/payment.html](../../shopman/shop/templates/storefront/payment.html) com branch `{% if method == "card" %}` que renderiza **botão único** `<a href="{{ order.data.payment.checkout_url }}">Pagar com cartão</a>` — zero JavaScript necessário.
4. `success_url` configurado para `/pedido/{ref}/confirmacao/`; `cancel_url` para `/pedido/{ref}/pagamento/` (volta à seleção).
5. Webhook `stripe.py`: verificar se processa evento `checkout.session.completed` além de `payment_intent.succeeded`. Se não, adicionar.
6. Selector de método no checkout: confirmar que já renderiza "cartão" como opção quando canal tem `method=["pix","card"]`.

---

## Escopo

### In

- Ajustar adapter `payment_stripe.py` para usar Stripe Checkout Session (API `stripe.checkout.Session.create()`).
- Passar metadata `{"order_ref": order.ref}` na session para idempotência no webhook.
- Template `_payment_card.html` mínimo (botão redirect + copy Omotenashi + instrução de segurança).
- Branch no `payment.html` por método.
- Webhook handler para `checkout.session.completed`.
- Testes:
  - `payment.initiate` com `method=card` persiste `checkout_url` em `order.data`.
  - View renderiza botão apontando para URL correta.
  - Webhook `checkout.session.completed` → `PaymentService.authorize + capture` → `dispatch(order, "on_paid")`.
  - Regressão PIX continua funcionando.

### Out

- Stripe Elements / PaymentElement / iframe — **explicitamente fora** (decisão de delegação total).
- Appearance API / customização visual do Stripe — fora; UX custom-de-nós é o botão que leva lá.
- Wallet / salvar cartão / SetupIntent — WP futuro.
- Apple Pay / Google Pay button — WP futuro.
- Parcelamento — fora.

---

## Entregáveis

### Novos arquivos

- `shopman/shop/templates/storefront/_payment_card.html` (~20 linhas):
  ```html
  <div class="flex flex-col gap-4">
    <div class="text-base">
      {% omotenashi "payment_card_intro" %}
      {# fallback/copy: "Você será levado ao ambiente seguro do Stripe. Voltamos assim que confirmar." #}
    </div>
    <a href="{{ order.data.payment.checkout_url }}"
       class="btn btn-primary text-center py-4 text-lg">
      Pagar com cartão
    </a>
    <p class="text-sm text-neutral">
      Pagamento processado pelo Stripe. Shopman nunca recebe dados do seu cartão.
    </p>
  </div>
  ```
- Testes em `shopman/shop/tests/web/test_payment_card.py` e `shopman/shop/tests/test_stripe_webhook_checkout.py`.

### Edições

- [shopman/shop/adapters/payment_stripe.py](../../shopman/shop/adapters/payment_stripe.py) `create_intent(order_ref, amount_q, currency, metadata)`:
  - Chamar `stripe.checkout.Session.create(...)` com:
    - `payment_method_types=["card"]`.
    - `mode="payment"`.
    - `line_items=[{"price_data": {"currency": currency.lower(), "product_data": {"name": f"Pedido {order_ref}"}, "unit_amount": amount_q}, "quantity": 1}]`.
    - `success_url=f"{settings.DOMAIN}/pedido/{order_ref}/confirmacao/"`.
    - `cancel_url=f"{settings.DOMAIN}/pedido/{order_ref}/pagamento/"`.
    - `metadata={"order_ref": order_ref, **(metadata or {})}`.
  - Retornar `GatewayIntent(intent_id=session.payment_intent, ..., metadata={"checkout_url": session.url})`.
- [shopman/shop/services/payment.py](../../shopman/shop/services/payment.py) `initiate`:
  - Após `adapter.create_intent(...)`, se `gateway_intent.metadata.get("checkout_url")`, persistir em `order.data.setdefault("payment", {})["checkout_url"]`.
- [shopman/shop/templates/storefront/payment.html](../../shopman/shop/templates/storefront/payment.html):
  - `{% if payment.method == "card" %}{% include "storefront/_payment_card.html" %}{% elif payment.method == "pix" %}{% include "storefront/_payment_pix.html" %}{% endif %}`.
- [shopman/shop/webhooks/stripe.py](../../shopman/shop/webhooks/stripe.py):
  - Adicionar handler para `event.type == "checkout.session.completed"`: extrair `metadata.order_ref` + `payment_intent` ID, chamar `PaymentService.authorize + capture` (se adapter não fizer automaticamente), dispatch `on_paid`.

---

## Invariantes a respeitar

- **Zero captura server-side**: nenhum campo de cartão toca Shopman. Review rigoroso.
- **PCI SAQ A**: só referenciamos URL Stripe externa. Zero iframe, zero stripe.js (exceto se futuramente decidirmos reativar Elements).
- **Idempotência**: webhook lookup via `metadata.order_ref` OR `payment_intent` gateway_id — mesmo padrão que PIX EFI.
- **`STRIPE_SECRET_KEY` server-only**.
- **Webhook é a verdade**: `success_url` pode ser chamado sem ter recebido webhook ainda — template de confirmação deve degradar graciosamente ("Recebemos seu pagamento, confirmando...") e listener SSE/polling pega o `on_paid` quando chega.
- **HTMX + Alpine only**: este WP nem toca JS. Template é static + anchor tag.
- **Omotenashi copy**: "ambiente seguro do Stripe", "voltamos assim que confirmar" — tom acolhedor + transparência (C3). Sem promessas piegas.
- **48px touch target** no botão principal; 16px+ body.
- **LGPD**: `checkout_url` em `order.data` expira após uso (é session_id Stripe). Ainda assim, não persistir em logs em plaintext.

---

## Critérios de aceite

1. Cliente em canal `delivery` escolhe `método=cartão` → checkout submit → redireciona para `/pedido/{ref}/pagamento/` que mostra botão "Pagar com cartão".
2. Clique no botão → redirect para `checkout.stripe.com/c/pay/cs_test_...` hospedado.
3. Cartão de teste `4242 4242 4242 4242` → Stripe redireciona para `/pedido/{ref}/confirmacao/`.
4. Webhook `checkout.session.completed` dispara → `PaymentIntent.status=CAPTURED` → dispatch `on_paid` → tracking mostra "Pagamento confirmado".
5. Cancelar no Stripe → redirect para `/pedido/{ref}/pagamento/` permitindo escolher PIX ou tentar cartão novamente.
6. Network tab: zero request de Shopman com dados de cartão.
7. Regressão: fluxo PIX não alterado (`checkout.session.completed` não é confundido com PIX webhook EFI).
8. `make test` verde.

---

## Referências

- Decisão: [.claude memory: project_card_payment_delegated_stripe.md](/Users/pablovalentini/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/project_card_payment_delegated_stripe.md).
- [shopman/shop/adapters/payment_stripe.py](../../shopman/shop/adapters/payment_stripe.py).
- [shopman/shop/webhooks/stripe.py](../../shopman/shop/webhooks/stripe.py).
- Docs Stripe: `stripe.com/docs/api/checkout/sessions/create` e `stripe.com/docs/payments/checkout/fulfill-orders` (padrão de webhook fulfillment).
- Test cards: `stripe.com/docs/testing#cards`.
- [docs/reference/system-spec.md](../reference/system-spec.md) §2.4 Adapters, §2.8 Webhooks.
