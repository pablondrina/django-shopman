# Feeds de catálogo — Google Merchant & Meta (Frente 5)

> Superfícies **FEED** (`capability="feed"`) do hub cross-channel. Um feed é uma
> superfície alimentada por uma coleção (manual ou smart) que expõe um **feed RSS
> 2.0 público** que Google Merchant Center e Meta Commerce Manager buscam por
> agendamento. Pesquisa **verificada** (fontes primárias Google + Meta) — 2026-07-01.

## O que está pronto (feed PULL — sem credenciais)

- **Endpoint público**: `GET /feed/<ref>.xml` → RSS 2.0 com namespace `g:` do Google
  (`http://base.google.com/ns/1.0`). `shopman/shop/views/product_feed.py` +
  `templates/feed/products.xml`.
- **Platform-aware**: `?platform=meta` emite `availability` no formato Meta
  (`in stock`/`out of stock`, com espaço); default = Google (`in_stock`/`out_of_stock`,
  underscore). É o **único** campo que diverge; o resto do XML `g:` é idêntico e serve
  os dois.
- Resolve a superfície (Channel `capability=feed` + `content.collection`), monta os
  itens da coleção (manual ou smart via `product_queryset`) e serve o XML. Itens **sem
  imagem são omitidos** (image_link é obrigatório; item sem imagem seria reprovado).

### Como o Pablo liga (sem código)
1. Admin → Channel `capability=feed`, `content.source=collection`, `content.collection=<ref>`.
2. Definir `SHOPMAN_STOREFRONT_URL` (base dos `g:link`) no deployment; verificar o domínio.
3. **Google Merchant Center**: Produtos → Fontes → busca agendada → `https://<dom>/feed/<ref>.xml`.
4. **Meta Commerce Manager**: Catálogo → Fontes → feed agendado → `https://<dom>/feed/<ref>.xml?platform=meta`.

## Spec verificada — Google (fontes primárias `support.google.com/merchants`)
- Formato: RSS 2.0, `xmlns:g="http://base.google.com/ns/1.0"`, `channel` → `item` com `g:`.
- Obrigatórios: `g:id`, `g:title` (≤150), `g:description` (≤5000), `g:link`, `g:image_link`,
  `g:availability` (`in_stock`|`out_of_stock`), `g:price` (`12.00 BRL`, ponto decimal).
- `g:condition=new`; `g:brand` (nome da loja) + `g:identifier_exists=no` (padaria artesanal
  sem GTIN — escape sancionado); `g:product_type` + **`g:custom_label_0`** (= coleção primária
  → o análogo das smart collections para segmentação de anúncios).
- Fontes: /answer/7052112 (spec), /6324448 (availability), /6324371 (price), /12631822, /14987622.

## Spec verificada — Meta (fontes primárias `developers.facebook.com` + `facebook.com/business/help`)
- **Aceita o MESMO RSS 2.0 `g:`** (namespace Google) — schema deliberadamente Google-compatível.
  Também aceita CSV/TSV/XLSX/Google Sheets.
- **Divergência-chave = `availability`**: Meta usa **`in stock`/`out of stock` (espaço, minúsculo)**;
  Google usa underscore. Verificado **verbatim** no doc primário Meta (help/120325381656392).
  Meta *pode* tolerar underscore no import RSS, mas o canônico é com espaço → emitimos espaço no
  `?platform=meta`.
- `condition`: `new`|`refurbished`|`used` (bakery = sempre `new`). `price`: `12.00 BRL` (igual Google).
- Limites: `id` ≤100, `title` ≤200 (recomendado <65), `description` ≤9999, `brand` ≤100.
- **Checkout on-platform é US-only** → loja BR usa "check out on website" (link-out) + tagging + ads.
  Não usar `quantity_to_sell_on_facebook`.
- **Food**: pão/doces são physical goods, permitidos; sem campo específico de perecível; evitar
  claims medicinais; álcool é restrito (linha à parte).

## O que falta (push near-real-time — CREDENCIAL, bloqueado no Pablo)
O feed pull atualiza no ritmo do fetch agendado (Google/Meta: **mínimo 1h**). Para refletir
pausa/preço em **minutos**, é preciso o push por API — cada um um `CatalogProjectionBackend`
(como o iFood), env-gated/off por padrão, alimentado pelo auto-trigger que já existe:

### Google — Merchant API (sucessora da Content API for Shopping)
- `products` insert/update. Auth: OAuth2 **service account** + Merchant ID + projeto Google Cloud.
- developers.google.com/merchant. Pinar a versão; Content API está em deprecação.

### Meta — Catalog **items_batch** (near-real-time)
- `POST https://graph.facebook.com/v25.0/{catalog_id}/items_batch`, body `{item_type:"PRODUCT_ITEM",
  allow_upsert:true, requests:[{method:CREATE|UPDATE|DELETE, retailer_id:<sku>, data:{...}}]}`.
  **≤5.000 requests/call, ≤100 calls/h/catalog**. ⚠️ `data.price` no batch pode ser minor-units
  inteiro + `currency` (vs `"25.00 BRL"` string do feed) — **confirmar por versão**; dois serializers.
- **Product Sets** (o análogo smart-collection p/ ads): `POST /v25.0/{catalog_id}/product_sets` com
  `filter` JSON (operadores eq/neq/contains/i_contains/is_any/gt/lt/…; campos brand/availability/
  price/**custom_label_0..4**/product_type/retailer_id). Nossas coleções mapeiam via `custom_label_0`.
- **Auth**: **System User access token** (server-to-server, long-lived) + Catalog ID; permissões
  `catalog_management` (+ dependência `business_management`). **Sem App Review** para gerir o próprio
  catálogo (single-tenant). Setup: Business Manager → Catalog → System User → assign catalog (task
  MANAGE) → gerar token. developers.facebook.com/docs/marketing-api/catalog-batch/reference.

⚠️ Flags a revalidar no Graph API Explorer antes de codar o push Meta: strings exatas dos operadores
de `filter`; convenção de `data.price` (minor-units vs string) na versão pinada; `item_type` para o
tipo de catálogo. (Ver relatórios de pesquisa 2026-07-01.)

## Estado
Feed pull ✅ (platform-aware Google+Meta; 6 testes; verificado ao vivo com o catálogo Nelson).
Push ⏳ (Pablo: credenciais Google Cloud/Merchant + Meta Business/System User).
