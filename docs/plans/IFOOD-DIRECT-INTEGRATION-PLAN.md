# Plano — Integração DIRETA com a API do iFood (Order Module)

> Decisão do Pablo (2026-06-30): conectar **direto na API de desenvolvedor do iFood**, não
> via integrador/hub. Isso é uma integração **multi-etapas** e **gated em homologação do
> iFood**. Este plano cobre arquitetura real, etapas, contratos e o que depende do Pablo.

## Realidade vs. o que tínhamos

O webhook atual ([`shopman/shop/webhooks/ifood.py`](../../shopman/shop/webhooks/ifood.py))
era um **stub de hub**: espera um payload **já normalizado** (items/customer/delivery inline)
e autentica por **token compartilhado**. **Não é** o protocolo cru do iFood. O iFood direto:

- **OAuth 2.0** (`client_credentials`): `POST https://merchant-api.ifood.com.br/authentication/v1.0/oauth/token`
  → Bearer token (expira ~6h, precisa refresh). client_id + client_secret do app no Portal.
- **Eventos leves** (só `id`, `code`, `orderId`, `merchantId`) — NÃO trazem o pedido inline.
  Recebidos por **polling** (recomendado) ou **webhook** (push, opcional).
- **Buscar o pedido**: `GET /order/v1.0/orders/{orderId}` → detalhes completos.
- **Devolver status**: `POST /order/v1.0/orders/{id}/confirm` (e `/dispatch`, `/readyToPickup`,
  `/requestCancellation`) → 202.
- **Homologação**: o iFood **certifica** a integração (envia eventos de teste, valida fluxo)
  antes de liberar produção. Sem homologação aprovada, não roda em prod.

## Decisão de arquitetura: Polling vs Webhook

| | **Polling** (recomendado iFood) | **Webhook** (push) |
|---|---|---|
| URL pública | **não precisa** | precisa HTTPS público + assinatura |
| Mecanismo | `GET orders:polling` a cada 30s + `POST orders:acknowledgment` | iFood faz POST assinado (HMAC `X-IFood-Signature`) |
| Robustez | alta (você controla o ritmo; reentrega o não-ack) | depende de uptime/entrega |
| Infra | um worker/cron de 30s | endpoint + validação de assinatura |

**Recomendação: polling-first.** Mais simples, robusto, sem URL pública, é o método primário
do iFood. Webhook fica como evolução opcional (aí sim entra o `X-IFood-Signature` HMAC + 401 —
ver [webhook-auth-status-codes](../reference/webhook-auth-status-codes.md)).

## Reaproveitamento (não jogar fora)

- **`ifood_ingest.ingest(payload)`** — recebe payload canônico e cria Order + dispara lifecycle.
  Reusar como destino final: depois de `GET /orders/{id}`, mapear iFood→canônico e chamar `ingest()`.
- **`webhook_idempotency`** — dedupe por evento; reusar no loop de polling (ack só após ingest).
- **`catalog_projection_ifood`** — push de catálogo já implementado (WP-GAP-15); só precisa do
  `catalog_api_token` real. Independente do fluxo de pedidos.
- **Channel `ifood`** + admin de simulação — mantêm-se para dev/teste.

## Etapas (WPs)

- **WP-1 — Auth + config.** `ifood_auth.py`: OAuth client_credentials + cache do token (TTL ~6h,
  refresh). Config `SHOPMAN_IFOOD`: `client_id`, `client_secret`, `merchant_id`. Testes com mock.
- **WP-2 — Loop de eventos (polling).** Service `ifood_events.poll()` + `acknowledge()`; command/cron
  de 30s (ou directive recorrente). Dedup via `webhook_idempotency`. Testes com mock de eventos.
- **WP-3 — Order fetch + mapeamento.** `GET /orders/{id}` → mapear schema real do iFood (items,
  customer, delivery, payments, fees) para o payload canônico do `ifood_ingest`. Testes com fixture
  de pedido real do iFood.
- **WP-4 — Callbacks de status.** Mapear lifecycle interno → `confirm`/`dispatch`/`readyToPickup`/
  `requestCancellation`. Handler que, em transições do Order, chama a API do iFood. Testes.
- **WP-5 — Webhook assinado (opcional) ✅ CONSTRUÍDO** (não verificado ao vivo — o portal bloqueia
  bots; revalidar o esquema exato de assinatura na homologação). `IFoodEventsWebhookView` em
  `webhooks/ifood_events.py`, rota `POST /api/webhooks/ifood/events/`: valida `X-IFood-Signature` =
  HMAC-SHA256(raw body, `webhook_hmac_secret` [default=client_secret]) hex via `compare_digest`,
  **401** se inválido/sem secret; reusa `ifood_events.process_events()` (mesmo caminho do polling).
  A view de simulação legada (`IFoodWebhookView`) fica intacta. Inerte até o secret ser setado.
- **WP-6 — Homologação.** Rodar os cenários de teste do iFood, ajustar, submeter à certificação.

## O que depende do Pablo (fora do código)

1. **App no Portal do Desenvolvedor do iFood** → `client_id` + `client_secret`.
2. **Merchant** associado ao app (merchant_id / UUID da loja).
3. **Escopos/módulos** habilitados (Order, Catalog, Merchant).
4. **Homologação** — passar a certificação do iFood (eles testam o fluxo). É o gate de produção.
5. (Se webhook) registrar a URL HTTPS — hoje `https://api.staging.nelsonboulangerie.com.br/api/webhooks/ifood/`.

## ✅ Verificado AO VIVO (2026-06-30) — app de teste + loja "Teste - Nelson Boulangerie"

Contra o ambiente real do iFood (não mais teórico):

- **⚠️ User-Agent próprio é OBRIGATÓRIO** — o WAF do iFood devolve `403` (corpo gzipado) para
  User-Agent genérico (python-requests/urllib). Usar um UA próprio em TODAS as chamadas.
- **OAuth ✅ (WP-1 feito, PR #24)**: `POST /authentication/v1.0/oauth/token`, form-urlencoded
  **camelCase** `grantType=client_credentials` + `clientId` + `clientSecret` → `{accessToken, expiresIn ~21599}`.
  Implementado em `shopman/shop/services/ifood_auth.py`.
- **Merchant ✅**: `GET /merchant/v1.0/merchants` (lista) e `/merchants/{id}` (detalhe). Loja de
  teste: `f36a17d0-e10b-4fdd-a16d-c8ffd866e59b` (status `DISABLED`).
- **Catalog leitura ✅**: `GET /catalog/v2.0/merchants/{mid}/catalogs` → catálogo
  `343e3649-18eb-4c08-99b4-4302df1cdf5e` (context `DEFAULT`, `AVAILABLE`);
  `GET .../catalogs/{catalogId}/categories` → categorias (ex.: "Categoria Item Normal"
  `1d097d39-0ce0-47a6-ad6b-1ab9f4d9692a", "Categoria Pizza"), com `items:[]`.
- **Estrutura real do catálogo**: Merchant → Catálogos → Categorias → Itens.
- **Catalog escrita ✅ (WP-Catalog feito)** — verificado AO VIVO empurrando 2 itens de teste p/
  "Categoria Item Normal":
  - **Upsert item**: `PUT /catalog/v2.0/merchants/{mid}/items` → `200`. Body = *FullItemDto*
    `{item:{id,productId,status,price:{value,originalValue},categoryId,externalCode,index,shifts},
    products:[{id,name,description,externalCode}]}`. `item.id`, `item.productId` e `products[0].id`
    **são UUIDs**; `item.productId == products[0].id`. UUIDs derivados por `uuid5(merchant_id, sku)`
    → upsert idempotente. `externalCode = sku` interno; `categoryId` mapeado por config
    (`catalog_category_map` + `catalog_default_category`).
  - **Disponibilidade/retract**: `PATCH /catalog/v2.0/merchants/{mid}/items/status` → `200`, body
    objeto único `{itemId:<uuid do item>, status:"AVAILABLE"|"UNAVAILABLE"}`.
  - Reescrito em `catalog_projection_ifood.py` usando `ifood_auth` (OAuth). `catalog_api_token`
    removido (era stub).
- Credenciais de teste no `.env` local (`IFOOD_CLIENT_ID/SECRET/MERCHANT_ID`) — funcionando.

## ✅ Order Module — paths verificados AO VIVO (2026-06-30)

⚠️ Os contratos abaixo **corrigem** a seção "Contratos" (que tinha `orders:polling` /
`orders:acknowledgment` — **não existem**, retornam `404 "no Route matched"`).

- **Polling de eventos**: `GET /order/v1.0/events:polling` → `200` (lista de eventos) ou `204`
  (nenhum). Header opcional `x-polling-merchants: <merchantId>` p/ filtrar. (Loja DISABLED →
  `204` ao vivo.)
- **Ack**: `POST /order/v1.0/events/acknowledgment`, body `[{"id": "<eventId>"}, ...]` → `202`.
  Body vazio → `400 "No events in request body"` (rota existe).
- **Detalhe**: `GET /order/v1.0/orders/{id}` (rota existe; id fake → `404 OrderNotFound`).
- **Status**: `POST /order/v1.0/orders/{id}/confirm` (e `/dispatch`, `/readyToPickup`,
  `/requestCancellation`) — rotas existem (id fake → `404 OrderNotFound`).
- **Motivos de cancelamento VERIFICADOS AO VIVO (2026-07-01)**: `GET /order/v1.0/orders/{id}/cancellationReasons`
  num pedido real devolve `[{cancelCodeId, description}]`. Lista válida capturada:
  `501` Problemas de sistema · `502` Duplicado · `503` Item indisponível/desatualizado ·
  `504` Sem entregadores · `506` Fora da área · `507` Golpe/trote · `508` Fora do horário ·
  `509` Dificuldades internas · `511` Área de risco · `512` Abrirá mais tarde · `523` Erro na promoção.
  `requestCancellation` é config-driven (`cancellation_default_code`), nunca chutado;
  **default setado = `501`** (env `IFOOD_CANCELLATION_CODE`, neutro). Staging/prod precisam do env var.
- **Callbacks WP-4 VERIFICADOS AO VIVO (2026-07-01)**: `confirm` → `readyToPickup` → `dispatch` →
  `requestCancellation` todos `202` contra pedidos de teste reais. Caminho de callback ponta-a-ponta OK.
- **🐛 BUG pego no e2e ao vivo (corrigido)**: `requestCancellation` com `reason` vazio → `400
  "Field 'reason' is required"`. Fix: `reason` nunca vazio (config `cancellation_default_reason`,
  default "Problemas de sistema na loja"). Reverificado `202`.

## ✅ E2E AO VIVO — pedido real → gestor → KDS (2026-07-01)

Stack local (Django :8000 + `ifood_poll --watch` + `process_directives --watch` + gestor Nuxt :3004 +
KDS Nuxt :3003). Gerado pedido de teste no Portal → `ifood_poll` ingeriu ao vivo:
- **Dados corretos**: `total_q=2700` (orderAmount), combo `line_total_q=1600` (opções+customizações),
  `is_test=True`, financeiro/pickupCode preservados. ✅
- **Gestor + KDS renderizam pedidos iFood ao vivo**; confirmar no gestor move o pedido pra PREPARO e
  cria ticket no KDS. ✅
- **⚠️ ACHADO IMPORTANTE (decisão p/ homologação)**: os pedidos **auto-gerados** do Portal usam SKUs
  **aleatórios** (ex.: 4994/1437, depois 4341/9274) que **não existem no nosso listing** → o
  `lifecycle.on_commit` **rejeita** (`not_in_listing`) e auto-cancela, disparando `requestCancellation`
  ao iFood. Em produção os pedidos referenciam o **nosso catálogo empurrado** (WP-Catalog), então
  batem. Mas **rever se auto-rejeitar+cancelar um pedido de marketplace já pago é o comportamento
  desejado** — talvez aceitar + alertar o operador seja melhor. Para demo do happy-path, usar pedido
  manual com produto do nosso catálogo empurrado (não o auto-gerado).
- **Schema do pedido VALIDADO AO VIVO (2026-07-01)** — capturei um pedido de teste real gerado pelo
  Developer Portal (`GET /orders/{id}` → `200`), fixture em `shopman/shop/tests/fixtures/ifood_order_real.json`.
  Descobertas que os mocks não pegavam e foram corrigidas no `map_order`:
  - **Combos**: `item.unitPrice` (base) ≠ `item.totalPrice` (inclui `optionsPrice`+`customizationPrice`).
    Usar `totalPrice` como `line_total_q`, senão subfatura. Opções têm `customizations` no 3º nível.
  - **`isTest: true`** — marcar (não entregar de verdade). Guardado em `order.data.ifood.is_test`.
  - **Financeiro** (`total.{subTotal,deliveryFee,additionalFees,benefits,orderAmount}`, `payments`)
    e `delivery.pickupCode` — preservados em `order.data.ifood.{totals,payments,pickup_code}`.
- **Como abrir a loja de teste**: ela fica `CLOSED` só por não estar conectada (`is-connected`); o
  horário já é 24/7. Basta o `ifood_poll --watch` rodando (mantém conectada) + botão "Gerar pedido de
  teste" no Portal (Menu Testes). O pedido cai no polling. Endereço da loja teste = Bujari/AC.
- ✅ **DECIDIDO + IMPLEMENTADO:** `Order.total_q` do pedido iFood = **`orderAmount` (grand total)**.
  `ifood_ingest.py`: `total_q = order_amount_q or items_subtotal_q` (fallback ao subtotal se ausente).
  Verificado ao vivo (`total_q=2700` = orderAmount). Taxas/breakdown ficam em `data.ifood.totals`.

## Contratos (confirmar na doc oficial durante a implementação — o portal bloqueia bots)

- OAuth: `POST merchant-api.ifood.com.br/authentication/v1.0/oauth/token` (`grant_type=client_credentials`).
- Polling: `GET merchant-api.ifood.com.br/order/v1.0/orders:polling` (Bearer).
- Ack: `POST .../order/v1.0/orders:acknowledgment` `{ "acknowledgedEventIds": [...] }` → 202.
- Detalhe: `GET .../order/v1.0/orders/{id}`.
- Confirmar: `POST .../order/v1.0/orders/{id}/confirm` → 202. (idem dispatch/readyToPickup/requestCancellation)
- Webhook (se usado): header `X-IFood-Signature` = HMAC-SHA256(raw body, client_secret) hex.

## ✅ UI de cancelamento (a) + gestão de cardápio (b) — 2026-07-01

- **(a) Seletor de motivo de cancelamento no gestor**: ao recusar/cancelar pedido iFood, o operador
  escolhe o motivo da lista real (`GET orders/<ref>/cancellation-reasons/` → live do iFood); o código
  trafega por `order.data.ifood_cancellation_code` até o `requestCancellation`. Outros canais = texto
  livre. Frontend em `orders-nuxt` (dialog condicional). Backend testado.
- **(b) Cardápio → iFood VERIFICADO AO VIVO**: editar no nosso sistema reflete no iFood — **preço**
  (R$15,90 refletiu), **pausar** (retract → UNAVAILABLE), **reativar** (→ AVAILABLE), **criar**.
  Nome/descrição vão no mesmo PUT (projetam junto).
  - **🐛 BUG pego no (b)**: `products[].image` inline (URL) → iFood **500**. Removido (v2.0 usa upload
    de imagem separado/`imagePath` — fora de escopo). Sem imagem: 200.
  - **⚠️ GAP (auto-trigger)**: hoje só `product_created` + `price_changed` disparam projeção
    automática. Editar **nome/descrição** ou **pausar** no admin NÃO re-projeta sozinho — falta um
    signal `product_updated` + wiring de disponibilidade→retract. Capability existe (projection
    empurra tudo); falta o gatilho. Follow-up.
  - **Eventual-consistency**: escritas de catálogo do iFood não são imediatas — PUT logo após criar
    pode dar 400 transitório; re-tentar resolve (o directive já dá retry).

## Ordem sugerida
WP-1 → WP-3 → WP-2 → WP-4 (esqueleto testável com mocks antes das credenciais) → WP-6 (com Pablo).
WP-5 só se optar por webhook.
