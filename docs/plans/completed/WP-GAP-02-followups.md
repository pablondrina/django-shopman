# WP-GAP-02 — Follow-ups (dívida técnica registrada)

> Itens identificados durante a execução de [WP-GAP-02](WP-GAP-02-card-checkout.md). Não bloqueiam, mas merecem WP próprio para análise detalhada.

## 1. Refund antes do webhook `checkout.session.completed` (janela curta)

Entre `create_intent` (cria `CheckoutSession`) e o webhook `checkout.session.completed`, o `PaymentIntent.gateway_id` armazena o **session id** (`cs_...`), não o `payment_intent` id (`pi_...`). Se um cancelamento dispara `payment_efi`-style refund nessa janela:

```python
stripe.Refund.create(payment_intent="cs_test_xyz")  # ❌ inválido — cs_ não é pi_
```

**Janela**: alguns minutos no pior caso (Stripe entrega webhook em segundos típicos).

**Fix sugerido**: no `payment_stripe.refund`, se `intent.gateway_id` começa com `cs_`, fazer `stripe.checkout.Session.retrieve(cs_id)` para obter `session.payment_intent` e usar esse. Fallback gracioso quando `payment_intent` ainda é `None`.

## 2. `.env.example` + docs de deploy desatualizados

WP-GAP-02 introduziu:

- `SHOPMAN_DOMAIN` (env var) → `SHOPMAN_STRIPE["domain"]` — public origin para `success_url`/`cancel_url` do Stripe Checkout. Default `http://localhost:8000`.
- Em produção, `SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_stripe` precisa ser explicitado (default ainda é `payment_mock`).

Nada disso aparece em `.env.example` nem em `docs/getting-started/`. Risco real: deploy "funciona" em dev e quebra silenciosamente em prod (cliente vê botão indo para `localhost:8000` ou pagamento simulado).

**Fix sugerido**: WP DX curto adicionando entradas comentadas em `.env.example` + nota em `docs/reference/configuration.md` (ou onde estiver a referência canônica de envs).

## 3. `SHOPMAN_STRIPE["capture_method"]` virou setting morto

O setting era lido pelo adapter antigo (`stripe.PaymentIntent.create(capture_method=...)`). Com Checkout Session, o controle passa para `payment_intent_data={"capture_method": ...}` dentro da Session. O setting continua sendo lido mas nunca aplicado.

**Fix sugerido**: ou remover o setting (e o env `STRIPE_CAPTURE_METHOD`), ou repropagar dentro de `payment_intent_data` em `create_intent`. Se for manter capture manual no futuro, opção 2 é melhor.

## 4. Pre-existing flake `test_pickup_slots.py`

Falham contra `origin/main` (sem qualquer mudança deste WP):

- `GetEarliestSlotTests::test_bread_only_gets_first_slot`
- `GetEarliestSlotTests::test_cake_pushes_to_slot_12`

Mensagem: `slot-09 != slot-XX`. Suspeito de dependência de hora local (testes assumem janela de slot que muda durante o dia).

**Fix sugerido**: WP de saneamento — congelar `timezone.now()` via `freezegun`/`time-machine` ou ajustar setup do teste para um instante fixo.
