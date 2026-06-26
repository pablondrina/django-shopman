# CATALOG-SYNC-EXTERNO-PLAN — Sincronização com catálogos externos

> Sincronizar o catálogo da Nelson para **Google Merchant Center**, **Meta
> (Instagram/Facebook) Shopping** e **WhatsApp Catalog**. Frente **v1** (🆕,
> Onda 1 · canais externos) do [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md).

**Status**: 🟡 Plano proposto (2026-06-26) — groundwork; aguarda revisão do Pablo +
credenciais/contas externas (bloqueio).

---

## Achado-chave: a fundação já existe

A pesquisa reversa mostrou que o projeto **já tem o padrão de projeção de
catálogo** — só falta os canais novos. Reusar, não reinventar:

- **Protocolo** `CatalogProjectionBackend` (`project()` + `retract()`):
  [`packages/offerman/shopman/offerman/protocols/projection.py`](../../packages/offerman/shopman/offerman/protocols/projection.py).
- **Padrão-ouro** já implementado: o adapter iFood
  [`shopman/shop/adapters/catalog_projection_ifood.py`](../../shopman/shop/adapters/catalog_projection_ifood.py)
  (project/retract + rate-limit) + management command `sync_catalog_ifood`.
- **Payload neutro** pronto: `catalog_exports.build_catalog_export()`
  ([`shopman/shop/services/catalog_exports.py`](../../shopman/shop/services/catalog_exports.py))
  e `ProjectedItem` (sku, name, description, price_q, image_url, category,
  keywords, metadata).
- **Categorias** hierárquicas (`Collection`/`CollectionItem`, `is_primary`) →
  mapeáveis para `google_product_category`.
- **API REST** de catálogo (produtos/coleções/preços) já existe.

## Gaps reais (o que falta)

1. **Campos de produto para feed** (Google/Meta exigem): hoje não há campo
   estruturado para **GTIN/EAN**, **brand** (vive solto em `metadata['brand']`),
   **condition**, **google_product_category**. Decidir: campos dedicados no
   `Product` (migração no Core — discutir) vs. dataclass tipada em
   `Product.metadata` (padrão do projeto, sem migração). **Recomendo metadata
   tipada** (`ProductFeedAttributes` dataclass, como `NutritionFacts`), evitando
   migração no Core.
2. **Imagens**: hoje são URLs externas (`image_url` + `metadata['gallery']`).
   Feed exige URL pública estável → **cruza com "media persistente" (Spaces/S3)**
   do backlog. Sem isso, depende de CDN externa já configurada.
3. **Adapters dos 3 canais** + management commands + config.
4. **Disponibilidade**: feed precisa de `availability` (in stock/out) — já
   derivável de `catalog_context.availability_for_sku()`.

---

## Arquitetura proposta (push, como iFood)

Seguir o padrão existente — um adapter por canal implementando
`CatalogProjectionBackend`:

- `shopman/shop/adapters/catalog_projection_google.py` — Content API for Shopping
  (products batch).
- `shopman/shop/adapters/catalog_projection_meta.py` — Catalog Batch API (Meta).
- `shopman/shop/adapters/catalog_projection_whatsapp.py` — WhatsApp Catalog
  (Meta Graph; compartilha catálogo Meta — **provável reuso do adapter Meta**;
  confirmar se WhatsApp Catalog == Meta Catalog vinculado ao número).
- Management commands `sync_catalog_{google,meta}` (`--full`/`--dry-run`), espelho
  de `sync_catalog_ifood`.
- Config `SHOPMAN_GOOGLE` / `SHOPMAN_META` (merchant/catalog id, token) — via env.

> Alternativa **pull** (feed XML/CSV servido por endpoint que o Google/Meta puxa)
> é mais simples de operar (sem token de escrita) mas tem latência de catálogo.
> **Recomendo push** para consistência com iFood; reavaliar se a conta externa
> favorecer feed URL.

## Arcos propostos

- **Arc 1 · Atributos de feed** — `ProductFeedAttributes` (GTIN, brand, condition,
  google_product_category) como dataclass em `Product.metadata` + form no admin +
  expor em `ProjectedItem`/`catalog_exports`. Sem migração no Core.
- **Arc 2 · Adapter Meta + WhatsApp Catalog** — um adapter Meta (Catalog Batch);
  confirmar vínculo WhatsApp↔Meta catalog. Management command + config + testes
  (espelho de `test_catalog_exports`).
- **Arc 3 · Adapter Google Merchant** — Content API; command + config + testes.
- **Arc 4 · Disponibilidade + agendamento** — sync incremental no lifecycle
  (produto publicado/despublicado/preço muda → projeta) + full sync agendado.

## Invariantes

- **Core sagrado**: preferir dataclass em `metadata` a migração no `Product`.
  Se campo estrutural/queryable for inevitável (GTIN para busca), discutir antes.
- Reusar `CatalogProjectionBackend` + `catalog_exports` — não criar fluxo paralelo.
- Adapters swappable por config (padrão do projeto).

## Bloqueios no Pablo

- Contas/credenciais: Google Merchant Center, Meta Business (Catalog), número
  WhatsApp Business vinculado ao catálogo Meta.
- Decisão de **media persistente** (Spaces/S3) se as imagens não estiverem já em
  CDN pública estável.
- Confirmar GTIN: padaria artesanal pode não ter GTIN — Google aceita
  `identifier_exists: false` para produtos sem GTIN (pães caseiros). Definir.

## Referências

- [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md)
- `catalog_projection_ifood.py` (padrão) · `catalog_exports.py` · `protocols/projection.py`
- `packages/offerman/shopman/offerman/models/{product,collection}.py`
