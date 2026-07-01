# Feeds de catálogo — Google Merchant & Meta (Frente 5)

> Superfícies **FEED** (`capability="feed"`) do hub cross-channel. Um feed é uma
> superfície alimentada por uma coleção (manual ou smart) que expõe um **feed RSS
> 2.0 público** que Google Merchant Center e Meta Commerce Manager buscam por
> agendamento. Pesquisa verificada (fontes primárias Google) — 2026-07-01.

## O que está pronto (feed PULL — sem credenciais)

- **Endpoint público**: `GET /feed/<ref>.xml` → RSS 2.0 com namespace `g:` do
  Google (`http://base.google.com/ns/1.0`). `shopman/shop/views/product_feed.py` +
  `templates/feed/products.xml`.
- Resolve a superfície (Channel `capability=feed` + `content.collection`), monta os
  itens da coleção (manual ou smart via `product_queryset`), formata no padrão
  verificado e serve o XML. Itens **sem imagem são omitidos** (image_link é
  obrigatório; item sem imagem seria reprovado).
- **Ambos os canais aceitam o mesmo XML Google-compatível** — um único feed serve
  Google Merchant e Meta.

### Atributos emitidos (spec verificada)
Obrigatórios: `g:id` (sku), `g:title` (≤150), `g:description` (≤5000), `g:link`,
`g:image_link`, `g:availability` (`in_stock`|`out_of_stock`), `g:price`
(`12.00 BRL`, ponto decimal). Mais: `g:condition=new`, `g:brand` (nome da loja),
`g:identifier_exists=no` (padaria artesanal sem GTIN — escape sancionado),
`g:product_type` e **`g:custom_label_0`** (= coleção primária → o análogo das smart
collections para segmentação de anúncios).

Fontes: support.google.com/merchants/answer/7052112 (product data spec), /6324448
(availability), /6324371 (price), /12631822 (formatos), /14987622 (RSS 2.0).

## Como o Pablo liga (sem código)
1. Criar um Channel `capability=feed`, `content.source=collection`,
   `content.collection=<ref>` (via Admin → aba "Superfície").
2. **Google Merchant Center**: Produtos → Fontes de dados → adicionar "busca
   agendada" apontando para `https://<dominio>/feed/<ref>.xml`. Verificar o domínio.
3. **Meta Commerce Manager**: Catálogo → Fontes de dados → "feed agendado" com a
   mesma URL (Meta aceita o XML Google).
4. Definir `SHOPMAN_STOREFRONT_URL` (base dos `g:link`) no deployment; verificar o
   domínio da loja nos dois painéis.

## O que falta (push near-real-time — CREDENCIAL, bloqueado no Pablo)
O feed pull atualiza no ritmo do fetch agendado do parceiro (horas). Para refletir
pausa/preço em **minutos**, é preciso o push por API — cada um um
`CatalogProjectionBackend` (como o iFood), env-gated/off por padrão:

- **Google**: Merchant API (sucessora da Content API for Shopping) —
  `products.insert/update`. Requer OAuth2 (service account) + Merchant ID + projeto
  no Google Cloud. developers.google.com/merchant.
- **Meta**: Catalog Batch API (`/{catalog_id}/items_batch`) para update de
  preço/disponibilidade near-real-time. Requer access token (System User), Catalog
  ID, Business Manager + app com permissão `catalog_management`.

Quando o Pablo prover as contas/credenciais, os adapters plugam na registry
canônica (Frente 1) e o auto-trigger já os alimenta — mesmo caminho do iFood.
⚠️ Pesquisa Meta ficou **parcial** (sub-agentes bateram no limite de sessão);
revalidar os endpoints/campos Meta antes de implementar o push.

## Estado
Feed pull ✅ (5 testes; verificado ao vivo com o catálogo Nelson). Push ⏳ (Pablo).
