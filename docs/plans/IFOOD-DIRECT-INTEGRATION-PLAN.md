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
- **WP-5 — Webhook assinado (opcional).** Se quiser push: validar `X-IFood-Signature`
  (HMAC-SHA256(raw body, client_secret) hex, `compare_digest`, **401** se inválido); trocar o
  token compartilhado atual. Senão, manter só polling.
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
- **⚠️ `catalog_projection_ifood` tem CONTRATO ERRADO** (`PUT .../items/{sku}` não existe assim,
  é stub). **WP-Catalog**: reescrever p/ o v2.0 (itens dentro de categorias, payload rico:
  produto + item + categoria). Verificar o endpoint exato de ingestão de item na doc/ao vivo.
- Credenciais de teste no `.env` local (`IFOOD_CLIENT_ID/SECRET/MERCHANT_ID`) — funcionando.

## Contratos (confirmar na doc oficial durante a implementação — o portal bloqueia bots)

- OAuth: `POST merchant-api.ifood.com.br/authentication/v1.0/oauth/token` (`grant_type=client_credentials`).
- Polling: `GET merchant-api.ifood.com.br/order/v1.0/orders:polling` (Bearer).
- Ack: `POST .../order/v1.0/orders:acknowledgment` `{ "acknowledgedEventIds": [...] }` → 202.
- Detalhe: `GET .../order/v1.0/orders/{id}`.
- Confirmar: `POST .../order/v1.0/orders/{id}/confirm` → 202. (idem dispatch/readyToPickup/requestCancellation)
- Webhook (se usado): header `X-IFood-Signature` = HMAC-SHA256(raw body, client_secret) hex.

## Ordem sugerida
WP-1 → WP-3 → WP-2 → WP-4 (esqueleto testável com mocks antes das credenciais) → WP-6 (com Pablo).
WP-5 só se optar por webhook.
