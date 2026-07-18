# SOCIAL-PIM-SPECS — Micro PIM focado em redes sociais

> **Status:** 📋 Specs (análise, sem implementação). Aguarda OK do Pablo antes de qualquer código.
> **Data:** 2026-07-18
> **Escopo:** centralizar os dados de produto necessários às plataformas sociais/comerciais e
> **controlar disponibilidade por plataforma de forma ultra fácil** — um "micro PIM" (Product
> Information Management enxuto), não um PIM enterprise.
> **Não implementa nada.** Define modelos, endpoints, UI, projeções, UX e faseamento.

**Leia antes:** [CROSS-CHANNEL-CATALOG-HUB-PLAN](CROSS-CHANNEL-CATALOG-HUB-PLAN.md) (master),
[CATALOG-FEEDS-GOOGLE-META](CATALOG-FEEDS-GOOGLE-META.md) (feeds pull prontos),
[CATALOG-SYNC-EXTERNO-PLAN](CATALOG-SYNC-EXTERNO-PLAN.md) (adapters propostos),
[PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md) (gate de escopo).

---

## 0. TL;DR

Um micro PIM social **não é um app novo**. É a combinação de três coisas que o projeto já
tem quase prontas:

1. **Dados (PIM)** — os campos que as plataformas exigem (marca, GTIN, categoria taxonômica,
   mídia, hashtags) vivem em `Product.metadata` via um **dataclass tipado**
   (`ProductSocialAttributes`), no padrão já usado por `nutrition_facts` e `metadata["fiscal"]`.
   **Zero migração no Core**, zero campo de canal no `Product`.
2. **Disponibilidade por plataforma** — **reusa** `ListingItem` (estado por canal) e `Showcase`
   (recorte por feed). Nada de reinventar visibilidade global.
3. **Sincronização** — cada plataforma é um `CatalogProjectionBackend` (como o iFood), alimentado
   pelo **auto-trigger** que já existe (PR #25). Estado de sync por plataforma num modelo novo e
   fino (`CatalogSyncState`) no orquestrador.

A UI "ultra fácil" é uma **matriz produto × plataforma** no Gestor (orders-nuxt), com um clique
para publicar/pausar e um selo de status de sync por plataforma. Config (regras, mapa de
categorias, Showcase) fica no Admin/Unfold.

> **Meta unifica 3 plataformas.** Instagram Shopping, Facebook Shop e WhatsApp Catalog leem o
> **mesmo Meta Commerce Catalog**. Um adapter Meta cobre os três; o WhatsApp é um *recorte
> curado* (limite de 500 produtos). Restam Google e TikTok Shop como catálogos próprios.

---

## 1. Princípios & invariantes (o que NÃO pode ser contrariado)

Herdados das decisões já tomadas no hub cross-channel — o micro PIM **estende**, não redesenha:

| Invariante | Origem | Consequência para o PIM social |
|---|---|---|
| **`ListingItem` = objeto de projeção por canal** (product × listing, com `is_published`/`is_sellable`/`price_q` próprios). | HUB Frente 1/3 | Disponibilidade "publica no IG, esconde no iFood" é membership de Listing/Showcase + flags no ListingItem. **Nunca** um campo de canal no `Product`. |
| **Visibilidade nunca é flag global.** Disponibilidade = par (item × contexto). | HUB | Publicar por plataforma = habilitar a plataforma como destino + estado por-item, não `Product.is_on_instagram`. |
| **Display/feed = `shop.Showcase`** (`kind` = menuboard/google/meta), NÃO o modelo morto `Channel.capability/content`. | HUB "Refactor Expositor" | Feeds Google/Meta/TikTok-feed vivem em `Showcase`. Adicionar `kind` para TikTok/WhatsApp se necessário. |
| **Dois eixos: CANAL × COLEÇÃO.** Bulk roteia pelo eixo coleção. | HUB | "Toda a coleção 'Pães' vai pro Instagram" = operação por coleção. Smart collections (`rule`) roteiam sozinhas. |
| **Projeção = `CatalogProjectionBackend` (`project`/`retract`)** em Offerman; registry `OFFERMAN["PROJECTION_BACKENDS"]` por `listing_ref`; adapter concreto no shop por dotted-path. | HUB Frente 1 | Meta/Google/TikTok = novos adapters no mesmo contrato. |
| **Core é sagrado.** Preferir dataclass em `metadata` a migração no `Product`. | ADR / CATALOG-SYNC | Campos PIM sociais = `ProductSocialAttributes` em `Product.metadata`. |
| **Auto-trigger retract-aware** (signal → Directive idempotente → re-lê estado atual → project/retract). | HUB PR #25 | Reusar. **Ampliar** `_PROJECTABLE_FIELDS` para disparar em mudança de mídia/marca/keywords (gap hoje). |
| **Pull-first é a realidade** (feed RSS pronto); push é credential-gated e off por default. | CATALOG-FEEDS | Push social entra como adapters `off by default`, atrás de env, sem bloquear o resto. |

**Anti-metas** (o que este micro PIM **não** é): não é um DAM completo, não é tradução i18n de
catálogo, não é gestão de variantes rica (cor/tamanho) — bakery tem SKUs simples. Escopo = o
mínimo para publicar bem e controlar disponibilidade sem dor.

---

## 2. Estado atual — o que o Offerman + orquestrador JÁ suportam

Mapa verificado no código (`packages/offerman/…`, `shopman/shop/…`).

### 2.1 `Product` (`models/product.py`) — campos e relevância social

| Campo | Serve a catálogo social? |
|---|---|
| `uuid`, `sku` (RefField, único) | ✅ id estável / retailer_id / externalCode. |
| `name` (200) | ✅ title. |
| `short_description` (255), `long_description` (Text) | ✅ description (`long or short`). |
| `keywords` (taggit `TaggableManager`) | ✅ tags/SEO; campo de smart collection; vira `ProjectedItem.keywords`. |
| `unit`, `unit_weight_g` | Parcial (unit projetado; peso não). |
| `base_price_q` (centavos) | Preço-base (o **preço por canal** vem do `ListingItem`). |
| `availability_policy` (`stock_only`/`planned_ok`/`demand_ok`) | ✅ política de disponibilidade (Stockman). |
| `is_published`, `is_sellable` (indexados) | ✅ gates de disponibilidade (ANDed com ListingItem). |
| `image_url` (URLField 500) | ⚠️ **imagem ÚNICA**. |
| `metadata` (JSON) | ✅ **loja de extensão PIM de fato** — ver 2.2. |
| `nutrition_facts` (JSON, dataclass `NutritionFacts`) | Padrão a copiar (dataclass validado em `clean()`). |

**Gatilho de projeção** (`product.py:206-222`): `_PROJECTABLE_FIELDS = (name, short_description,
long_description, is_published, is_sellable)`. `save()` emite `product_created`/`product_updated`.
⚠️ Mudar `image_url`/`keywords`/`metadata` **não** dispara re-projeção hoje.

### 2.2 `Product.metadata` — chaves já em uso (o PIM informal de hoje)

- `metadata["fiscal"]` = `{profile, ncm, cest}` (Fiscalman, via `contrib/offerman`).
- `metadata["brand"]` — **marca só existe aqui** (sem coluna, sem validação, passa verbatim no export).
- `metadata["gallery"]` = lista de URLs extras (lida por `catalog_exports._images`, depois removida do payload).
- Dietético: `allergens`, `dietary_info`, `serves`, `approx_dimensions`, `allows_next_day_sale`.
- `metadata["external_id"]` — passthrough preservado.

> **Fato-chave:** `catalog_exports._product_metadata()` repassa **todo** `product.metadata` (menos
> `gallery`) para os adapters. Qualquer chave nova aqui chega downstream de graça. **Mas** o
> `ProjectedItem` do `get_projection_items` só injeta metadata do *listing*, não do produto —
> os adapters de projeção (iFood) hoje ignoram `metadata`. Isso precisa mudar (ver 7.6).

### 2.3 `Listing` / `ListingItem` — preço & visibilidade por canal

- `Listing` (ref == `Channel.ref` por convenção; `projection_metadata` JSON guarda
  `last_projected_skus` para detectar remoções).
- `ListingItem` = product × listing com `price_q`, `is_published`, `is_sellable`, `min_qty` próprios.
  `save()` emite `price_changed` e `availability_changed`.
- **Disponibilidade em 2 níveis:** live num canal ⇔ `Product.is_published AND Product.is_sellable
  AND ListingItem.is_published AND ListingItem.is_sellable`.

### 2.4 `Collection` (+ smart) — roteamento e categoria

- `rule` JSONField → `is_smart`; `product_queryset()` resolve por regra ou por `CollectionItem`s.
- Campos de regra: `keyword, sku, name, unit, base_price_q, is_published, is_sellable, collection`.
  Ops: `eq, ne, lt, lte, gt, gte, in, contains`.
- `CollectionItem.is_primary` → coleção primária vira **categoria externa** (`ProjectedItem.category`
  → mapeada por config no adapter). É o análogo de "product set"/`custom_label_0` do Google/Meta.

### 2.5 `Showcase` (`shop.Showcase`) — feeds prontos (pull)

- `kind` ∈ menuboard/google/meta; `collections` (refs); `paused_skus()` (camada de pausa local).
- Feed público `GET /feed/<ref>.xml` (RSS 2.0, namespace `g:`), `?platform=meta` diverge só em
  `availability`. Produto sem `image_url` é omitido.

### 2.6 Projeção & auto-trigger (o motor)

- Protocolo `CatalogProjectionBackend.project(items, *, channel, full_sync)` / `retract(skus, *, channel)`
  → `ProjectionResult{success, projected, errors, channel}`.
- `ProjectedItem(sku, name, description, unit, price_q, is_published, is_sellable, category, image_url, keywords, metadata)`.
- Adapter-ouro: `catalog_projection_ifood.py` — UUID determinístico `uuid5` (re-sync = upsert),
  `status AVAILABLE/UNAVAILABLE` inline, retract dedicado (`PATCH /items/status`), categoria via
  `catalog_category_map`, **sem imagem inline** (fluxo separado).
- Auto-trigger (`handlers/catalog_projection.py`): signals → Directive `CATALOG_PROJECT_SKU` (dedupe
  SHA-256) → handler re-lê estado atual → upsert se published+sellable, senão retract → 429 requeue.
- Reconciliação por listing (`project_listing`): diff vs `last_projected_skus` retrata SKUs sumidos.
- Export neutro `catalog_exports.build_catalog_export()` (imagens em tupla, metadata completo,
  `tags`, status active/paused/inactive).

### 2.7 contrib existentes

`import_export/` (CSV/XLSX por SKU), `substitutes/` (substituição), `admin_unfold/`. **Nenhum
contrib social/feed/PIM ainda.** (Fiscalman é o modelo de "contrib que estende o Product admin
via metadata" — o `social` deve segui-lo.)

---

## 3. Requisitos por plataforma (pesquisa 2026)

> Meta unifica **Instagram Shopping + Facebook Shop + WhatsApp Catalog + Marketplace + Ads** num
> único Commerce Catalog. Google e TikTok são catálogos próprios. Checkout on-platform (Meta/TikTok)
> é restrito a alguns países — no BR o padrão é **link-out** (fechar no site).

### 3.1 Matriz de campos (obrigatório ✅ / opcional ○ / n/a —)

| Campo canônico | Google Merchant | Meta (IG/FB) | WhatsApp Catalog | TikTok Shop |
|---|---|---|---|---|
| id / retailer_id (= SKU) | ✅ `id` | ✅ `id`/`retailer_id` | ✅ `retailer_id` (=SKU) | ✅ SKU |
| title (nome) | ✅ ≤150 | ✅ ≤200 | ✅ | ✅ |
| description | ✅ ≤5000 | ✅ ≤9999 (rec 200-500), texto puro | ✅ ≤5000 | ✅ |
| link (URL do produto) | ✅ | ✅ | ○ (link-out) | ✅ (storefront TikTok) |
| image_link | ✅ | ✅ 500×500+ | ✅ | ✅ |
| additional images | ○ | ○ (até ~10) | ○ **até 10** | ○ (múltiplas) |
| price | ✅ `12.00 BRL` (ponto) | ✅ `12.00 BRL` | ✅ (moeda pelo país do SIM) | ✅ |
| sale_price / effective_date | ○ | ○ | — | ○ (promoções) |
| **availability** | ✅ `in_stock`/`out_of_stock` (underscore) | ✅ `in stock`/`out of stock`/`available for order` (espaço) | ✅ | ✅ inventory count |
| condition | ○ (`new`) | ✅ `new`/`refurbished`/`used` | ○ | ○ |
| **brand** | ✅ (nome da loja) | ✅ ≤100 | ○ | ○ |
| **gtin** (ou `identifier_exists=no`) | ✅ se existir; senão `identifier_exists:no` + `mpn` | ○ | ○ | ○ |
| mpn | ○ (obrig. sem GTIN) | ○ | — | — |
| **google_product_category** | ✅ (taxonomia) | ○ (`google_product_category`) | — | ✅ (categoria TikTok própria) |
| product_type (categoria da loja) | ○ | ○ (`fb_product_category`) | — | ○ |
| custom_label_0..4 | ○ (= coleção → ads) | ○ (Product Sets) | — | — |
| item_group_id (variantes) | ○ | ○ | — | ✅ (variants) |
| color/size/gender/age_group | ○ (✅ p/ vestuário) | ○ | — | ○ |
| shipping / weight | ○ | ○ | — | ✅ (logística) |

**Padaria artesanal (Nelson):** sem GTIN → `identifier_exists:no` (Google) é o escape sancionado;
`brand` = nome da loja; `condition` = sempre `new`. Vestuário-only attrs (color/size/gender/age)
não se aplicam.

### 3.2 Enums de disponibilidade (o campo que mais diverge)

| Estado interno | Google | Meta / WhatsApp | iFood | TikTok |
|---|---|---|---|---|
| disponível | `in_stock` | `in stock` | `AVAILABLE` | inventory > 0 |
| esgotado / pausado | `out_of_stock` | `out of stock` | `UNAVAILABLE` | inventory = 0 / status |
| encomenda (preorder) | `preorder`/`backorder` | `available for order` | — | — |

> O micro PIM tem **um estado canônico** (published+sellable+stock) e cada adapter serializa para
> o enum da sua plataforma (já é assim no feed pull; replicar no push).

### 3.3 API / auth / limites por plataforma

- **Google Merchant API** (sucessor da Content API for Shopping): `products.insert/update/delete`;
  OAuth2 service account + Merchant ID + projeto GCP. **Fixar a versão** (Content API depreciando).
  *Pull (feed RSS) já funciona hoje sem credencial.*
- **Meta Catalog `items_batch`**: `POST graph.facebook.com/v25.0/{catalog_id}/items_batch` com
  `{item_type:"PRODUCT_ITEM", allow_upsert:true, requests:[{method:CREATE|UPDATE|DELETE,
  retailer_id:<sku>, data:{…}}]}`. ≤5000 requests/call, ≤100 calls/h/catálogo. **System User token**
  (server-to-server, long-lived) + Catalog ID; permissão `catalog_management`. Sem App Review para
  catálogo próprio. ⚠️ `data.price` no batch pode ser inteiro em unidades-menores + moeda (vs
  string `"12.00 BRL"` no feed) — **dois serializers**; confirmar por versão.
  - **Meta Product Sets** (análogo de smart collection p/ ads): `POST /{catalog_id}/product_sets`
    com `filter` JSON (ops eq/neq/contains/i_contains/is_any/gt/lt; fields brand/availability/price/
    `custom_label_0..4`/product_type/retailer_id). Coleções → `custom_label_0`.
- **WhatsApp Catalog**: é **o mesmo Meta Catalog** ligado ao número (WABA + Business Manager).
  Limites duros: **500 produtos/catálogo**, **1 catálogo por WABA**, até 10 imagens, `retailer_id`=SKU.
  → precisa de **recorte curado** (Product Set / `Showcase(kind=whatsapp)`) quando o catálogo passar
  de 500. *A reutilização do adapter Meta precisa ser confirmada em homologação.*
- **TikTok Shop** (LIVE no Brasil, 2026): Products API (create/update/remove) via **Global Partner
  Portal** (não-US); precisa de titles/desc/images/pricing/variants/SKUs/inventory + servidor com
  webhooks. **Peso de integração ≈ iFood** (marketplace transacional completo, não só feed). Avaliar
  se entra na v1 ou fica em ondas posteriores.

---

## 4. Gaps concretos (o que falta para o micro PIM social)

| # | Gap | Hoje | Impacto |
|---|---|---|---|
| G1 | **GTIN/EAN/barcode** | inexistente | Google recomenda; sem ele, `identifier_exists:no`. Estrutural p/ marketplaces. |
| G2 | **Marca (brand)** | só `metadata["brand"]` solto | Sem validação, não filtrável, não é campo de smart collection. |
| G3 | **Categoria taxonômica** (`google_product_category` / categoria TikTok) | derivada da coleção primária + mapa por config | Sem código taxonômico por produto; feed manda só `product_type`/`custom_label_0`. |
| G4 | **Mídia rica** | `image_url` único + `metadata["gallery"]` sem tipo | Sem modelo de mídia, alt-text, papel/ordem por imagem, vídeo, formato por plataforma. |
| G5 | **Publicar/despublicar por plataforma** no produto | via Listing/Showcase separados | Não há opt-in por-plataforma nem "publica no IG, some no iFood" num lugar só. |
| G6 | **Status de sync por produto×plataforma** | `last_projected_skus` (só um set) + Directives transientes | Sem `last_synced_at`, `external_id`, erro, pendência por item/plataforma. |
| G7 | **Gatilho estreito** | `_PROJECTABLE_FIELDS` ignora imagem/keywords/metadata | Editar mídia/marca/categoria **não re-sincroniza** até mudar nome/pub. |
| G8 | **Regras de publicação** | inexistente | Sem "publicar ao criar", "publicar com estoque", agendar. |
| G9 | **Adapters Google/Meta/TikTok** | só iFood + feed pull | Push near-real-time p/ social não existe (credential-gated). |
| G10 | **Hashtags / copy social** | inexistente | Redes sociais pedem hashtags/legenda ≠ description de e-commerce. |

---

## 5. Arquitetura — onde vive o micro PIM (análise de opções)

**Pergunta central (#3 da tarefa):** contrib no Offerman? pacote `socialman`? orquestrador?
superfície? Combinação?

**Recomendação: COMBINAÇÃO em 4 camadas, sem novo pacote Core.**

| Camada | Onde | Por quê |
|---|---|---|
| **Dados PIM** (marca, GTIN, categoria, mídia, hashtags) | **`packages/offerman/shopman/offerman/contrib/social/`** — dataclass `ProductSocialAttributes` em `Product.metadata` + aba no Product admin | Segue o padrão Fiscalman (contrib que estende o Product via metadata). **Zero migração no Core.** São atributos do PRODUTO (mesmos entre plataformas), logo pertencem perto do produto — mas em contrib, não no modelo cru. |
| **Projeção/sync por plataforma** | **`shopman/shop/adapters/catalog_projection_{google,meta,tiktok}.py`** (WhatsApp reusa Meta) + comandos `sync_catalog_{plataforma}` | Orquestração cross-app (Offerman→externo) é do orquestrador. Reusa `CatalogProjectionBackend` + auto-trigger + registry. Mesmo lugar do iFood. |
| **Estado de sync** | **`shopman/shop/models/catalog_sync.py`** — modelo novo `CatalogSyncState` (product×plataforma) | Estado operacional de sincronização, não catálogo Core. Fino, migração no shop (não em package). |
| **UI do operador** | **`orders-nuxt` "Catálogo"** (matriz produto×plataforma — estende a Frente 3 já decidida) + **Admin/Unfold** (config: regras, mapa de categorias, `Showcase`, `ProductSocialAttributes` editor) | Matriz operacional em Nuxt (decisão do hub); config em Unfold (decisão do hub). |

**Por que NÃO `packages/socialman/`:** fragmentaria o catálogo (que é do Offerman) e a projeção
(que é do orquestrador). A memória "Offerman should anticipate PIM/Offer split" se satisfaz com o
**contrib `social`** (o "PIM") + `ListingItem` (o "Offer" por canal) — o split já é conceitual via
ListingItem, sem precisar de pacote. Um `socialman` só se justificaria se houvesse lógica de rede
social **não-catálogo** (agendamento de posts, DMs, insights) — fora do escopo deste micro PIM.

**Por que NÃO campo de canal no Product:** viola a invariante `ListingItem`=projeção-por-canal.
"Está no Instagram?" = existe num `Listing`/`Showcase` cujo destino é Meta **e** o `CatalogSyncState`
diz `synced`.

```
┌─ Offerman (Core, sagrado) ──────────────────────────────┐
│ Product ─ metadata["social"] (ProductSocialAttributes)  │  ← contrib/social (dados PIM)
│ Product ─ ListingItem (preço/pub por canal)             │  ← "Offer" por canal (já existe)
│ Collection (rule/smart) → categoria/product-set          │
│ CatalogProjectionBackend (protocolo)                     │
└──────────────────────────────────────────────────────────┘
                  │ ProjectedItem (enriquecido c/ social)
                  ▼
┌─ shopman/shop (orquestrador) ───────────────────────────┐
│ adapters/catalog_projection_{meta,google,tiktok}.py     │  ← push por plataforma
│ models/catalog_sync.py: CatalogSyncState                │  ← status por produto×plataforma
│ Showcase(kind=meta/google/whatsapp/tiktok) (recortes)   │  ← feed/curadoria (500 do WhatsApp)
│ handlers/catalog_projection.py (auto-trigger, ampliado) │
└──────────────────────────────────────────────────────────┘
                  │ projections + APIs
                  ▼
┌─ Superfícies ───────────────────────────────────────────┐
│ orders-nuxt "Catálogo": matriz produto×plataforma       │  ← "ultra fácil" (operação)
│ Admin/Unfold: ProductSocial editor + config/regras      │  ← config
└──────────────────────────────────────────────────────────┘
```

---

## 6. Specs por capability

### 6.1 Campos PIM sociais — `ProductSocialAttributes` (dataclass em `metadata["social"]`)

**Model/schema** (padrão `NutritionFacts`; validado em um `clean()` de contrib, sem migração):

```python
# packages/offerman/shopman/offerman/contrib/social/schema.py
@dataclass(frozen=True)
class ProductSocialAttributes:
    brand: str = ""                       # G2 — default = nome da loja (Shop.brand_name) se vazio
    gtin: str = ""                        # G1 — EAN/UPC; vazio ⇒ identifier_exists=no
    mpn: str = ""                         # opcional (obrig. no Google só sem GTIN)
    google_product_category: str = ""     # G3 — id numérico ou path da taxonomia Google
    condition: str = "new"                # new|refurbished|used (bakery = new)
    tiktok_category_id: str = ""          # G3 — categoria própria do TikTok (quando aplicável)
    hashtags: list[str] = field(default_factory=list)   # G10 — sem "#", normalizado
    social_caption: str = ""              # G10 — legenda social (≠ long_description)
    # Overrides opcionais por plataforma (raro; default = campos canônicos):
    platform_overrides: dict = field(default_factory=dict)  # {"meta": {"title": "..."}}
```

- **Armazenamento:** `Product.metadata["social"]`. `from_metadata()` / `to_metadata()` (como fiscal).
- **Validação:** GTIN (8/12/13/14 dígitos, checksum), `condition` no enum, `google_product_category`
  contra a taxonomia (lista embarcada/CSV). Erros no admin, não no `Product.clean()` (Core intocado).
- **Herança de default:** `brand` vazio ⇒ resolve `Shop.brand_name` na projeção (não persiste).

**API/endpoint:** exposto no payload de projeção via enriquecimento do `ProjectedItem.metadata`
(ver 6.6). Sem endpoint REST próprio no MVP (editado via admin + matriz).

**Admin UI:** aba **"Redes sociais"** no `ProductAdmin` (via contrib, `get_fieldsets` insere um
fieldset `classes=("tab",)` — idêntico ao Fiscalman): brand, gtin, google_product_category (select2
com busca na taxonomia), hashtags (ArrayWidget), social_caption (textarea). Help-texts orientadores.

**Projeção:** cada adapter lê `social.*` do `ProjectedItem.metadata` e mapeia (brand→`brand`,
gtin→`gtin`|`identifier_exists`, google_product_category→`google_product_category`, hashtags→
legenda quando a plataforma suporta).

**UX ("ultra fácil"):** 80% dos campos têm default inteligente (brand=loja, condition=new,
gtin=vazio→identifier_exists=no, categoria sugerida pela coleção primária). O operador só toca no
que quer refinar. **Nunca** um formulário de 30 campos vazios.

### 6.2 Gestão de mídia (G4)

**MVP (antes do S3):** tipar a galeria em `metadata["social"]["media"]`:

```python
@dataclass(frozen=True)
class ProductMedia:
    url: str
    role: str = "gallery"      # main|gallery|social|video
    alt: str = ""
    sort: int = 0
```

- `main` → `image_link`; `gallery`/`social` → `additional_image_link` (Meta/WhatsApp até 10);
  `video` → campos de vídeo quando a plataforma aceitar (Meta/TikTok).
- Requisitos por plataforma: Meta ≥500×500, quadrada preferida; WhatsApp ≤10 imagens; Google
  imagem pública/estável; TikTok múltiplas + vídeo.

**Dependência dura:** URLs **públicas e estáveis**. Hoje o filesystem é efêmero (perde imagem em
redeploy). **Bloqueado por "media persistente (Spaces/S3)"** — agendado pré-go-live
(PRODUCT-V1-SCOPE-BACKLOG). Até lá, mídia rica social não é confiável; MVP usa `image_url` +
`gallery` com URLs já hospedadas.

**Full (pós-S3):** modelo `ProductImage` de verdade (FK Product, arquivo em Spaces, role, alt,
ordem, dimensões) — migra a galeria do metadata. Vídeo/story como assets com transcode.

### 6.3 Disponibilidade granular por plataforma (G5) — REUSO, não reinvenção

**Modelo:** "plataforma" = um **destino de projeção** (um `Listing`/`Channel` transacional OU um
`Showcase` de feed). Publicar/pausar por plataforma:

- **Transacional** (iFood, TikTok Shop, WhatsApp com carrinho): `ListingItem.is_published`/`is_sellable`
  no listing daquela plataforma. Já existe.
- **Feed/vitrine** (Google, Meta IG/FB, WhatsApp catálogo): membership do produto numa `Collection`
  que compõe o `Showcase(kind=...)` + `Showcase.paused_skus()`. Já existe.
- **Estado canônico** manda: um produto `is_published=false` some de tudo (retract em cascata pelo
  auto-trigger).

**O que falta:** um **mapa "plataforma → destino"** legível e uma matriz que mostre, por produto,
o estado em cada plataforma (derivado dos acima). Não é campo novo no produto — é uma **projeção de
leitura** (`backstage/projections/catalog.py`, ampliada) que resolve, por (produto, plataforma):
`{available, paused_here, synced, last_synced, error}`.

**Curadoria WhatsApp (limite 500):** `Showcase(kind=whatsapp)` com coleções que somem ≤500 SKUs;
validação que alerta ao passar de 500 (a API rejeita). Smart collection resolve o recorte sozinha.

### 6.4 Status de sync por plataforma (G6) — modelo novo `CatalogSyncState`

```python
# shopman/shop/models/catalog_sync.py
class CatalogSyncState(models.Model):
    sku = models.CharField(max_length=100, db_index=True)     # ou FK Product por uuid
    platform = models.CharField(max_length=32)               # meta|google|tiktok|whatsapp|ifood
    external_id = models.CharField(max_length=200, blank=True) # id do item na plataforma
    status = models.CharField(max_length=16)                  # synced|pending|error|retracted|skipped
    last_synced_at = models.DateTimeField(null=True)
    last_error = models.TextField(blank=True)
    last_payload_hash = models.CharField(max_length=64, blank=True)  # evita re-push idêntico
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ("sku", "platform")
```

- **Escrito pelos adapters/handler** ao final de cada `project`/`retract` (sucesso→`synced`+timestamp;
  falha→`error`+mensagem; 429→`pending`). Substitui/complementa o `last_projected_skus` cru.
- **Lido pela matriz** para o selo de status por célula (produto×plataforma).
- Migração vive em `shopman/shop/migrations` (orquestrador), não em package. Fino e queryable.

**API:** `GET /api/v1/backstage/catalog/sync-status?platform=&sku=` (projeção) para a matriz;
`POST …/catalog/resync` (dispara `project_listing`/directive) para "sincronizar agora".

### 6.5 Regras de publicação (G8)

Config por plataforma (em `Shop.defaults["social_publish"]` ou no `Channel`/`Showcase` config):

```json
{
  "meta":   {"publish_on_create": true,  "require_stock": false, "require_image": true},
  "google": {"publish_on_create": true,  "require_stock": false, "require_image": true},
  "tiktok": {"publish_on_create": false, "require_stock": true,  "require_image": true}
}
```

- `publish_on_create` — produto novo entra no destino automaticamente.
- `require_stock` — só publica com estoque > 0 (senão fica `pending` até ter).
- `require_image` — não publica sem imagem (Google/Meta rejeitam; hoje o feed já omite).
- `schedule` (futuro) — publicar a partir de uma data (lançamento). Um Directive com `available_at`.

Regras são **guardas no handler de auto-trigger**, não lógica nova de negócio.

### 6.6 Adapters de projeção (G9) — um por plataforma, contrato iFood

Cada um implementa `CatalogProjectionBackend`, registrado em `OFFERMAN["PROJECTION_BACKENDS"]`,
`off by default` atrás de env (`SHOPMAN_META`, `SHOPMAN_GOOGLE`, `SHOPMAN_TIKTOK`).

- **`catalog_projection_meta.py`** (cobre IG + FB + WhatsApp):
  - `project` → `items_batch` (CREATE/UPDATE, `retailer_id`=sku, `data`={title, description,
    availability(`in stock`/`out of stock`), condition, price, link, image_link,
    additional_image_link, brand, google_product_category, custom_label_0=coleção}).
  - `retract` → `items_batch` method DELETE (ou UPDATE availability=`out of stock`).
  - Batching ≤5000/call; respeitar ≤100 calls/h.
  - **WhatsApp** = mesmo adapter, `channel="whatsapp"`, alimentado por `Showcase(kind=whatsapp)`
    (recorte ≤500). Confirmar em homologação se é o mesmo catalog_id ou um dedicado.
  - ⚠️ resolver `data.price` (inteiro+moeda vs string) por versão da Graph API.
- **`catalog_projection_google.py`**:
  - `project` → Google Merchant API `products.insert/update` (ou supplemental feed).
  - `retract` → `products.delete` ou availability=`out_of_stock`.
  - `identifier_exists:false` quando sem GTIN. Fixar versão da API.
  - *O feed RSS pull continua como fallback/bootstrap sem credencial.*
- **`catalog_projection_tiktok.py`** (avaliar escopo):
  - Products API (create/update/delete) via Global Partner Portal; inventory sync; variants.
  - Peso ≈ iFood; provavelmente **onda posterior** (não MVP).

**Reuso obrigatório:** `catalog_exports.build_catalog_export()` como fonte do payload neutro;
`ProjectedItem` enriquecido com `metadata["social"]` (ver abaixo).

**Enriquecer o `ProjectedItem` (corrige a lacuna do 2.2):** `CatalogService.get_projection_items`
deve injetar `product.metadata["social"]` (+ imagens da galeria) no `ProjectedItem.metadata` para
os adapters sociais lerem brand/gtin/categoria/mídia. Hoje só injeta metadata do listing.

### 6.7 Auto-trigger — ampliar `_PROJECTABLE_FIELDS` (G7)

Incluir os campos que uma edição de PIM social muda: `image_url`, `keywords` (M2M — via signal
próprio), e mudanças em `metadata["social"]`/`metadata["gallery"]`. Sem isso, editar marca/foto/
categoria/hashtag **não re-sincroniza**. Como `metadata` é JSON, comparar um hash das chaves
relevantes no `save()` do produto (ou emitir `product_media_changed`/`product_pim_changed`).

### 6.8 UI do operador — matriz produto × plataforma (o "ultra fácil")

**orders-nuxt, aba "Catálogo"** (estende a Frente 3 já entregue — 51 produtos × 5 superfícies):

- **Matriz:** linhas = produtos (ou coleções, eixo alternável); colunas = plataformas
  (iFood, Instagram/FB, WhatsApp, Google, TikTok). Célula = selo de estado:
  🟢 publicado+synced · 🟡 pendente · ⏸️ pausado aqui · 🔴 erro de sync · ⚪ fora desta plataforma.
- **Um clique** na célula: publicar/pausar naquela plataforma (toggle no ListingItem/Showcase +
  dispara sync). Tooltip com `last_synced_at`/erro.
- **Bulk pelo eixo coleção:** "publicar coleção 'Pães' no Instagram" = uma ação.
- **Painel lateral** (ao abrir um produto): campos PIM sociais (brand/gtin/categoria/hashtags/mídia)
  editáveis inline, com defaults preenchidos — "ultra fácil" = raramente precisa digitar.
- **"Sincronizar agora"** e **"Ver erro"** por célula.

**Admin/Unfold** (config, não operação): editor de `Collection.rule`, `Showcase` (quais coleções
em cada plataforma), mapa de categorias por plataforma, regras de publicação, credenciais (env).

---

## 7. Faseamento

| Fase | Entrega | Depende de |
|---|---|---|
| **F0 — Fundação PIM (sem credencial)** | `contrib/social` + `ProductSocialAttributes` (brand/gtin/categoria/condition/hashtags) + aba admin + enriquecer `ProjectedItem` + ampliar auto-trigger (G7) + `CatalogSyncState` model. | nada (tudo local). |
| **F1 — Meta push (IG/FB)** | `catalog_projection_meta.py` (items_batch) + comando + config `SHOPMAN_META` + matriz mostra estado Meta. | credenciais Meta (System User token + Catalog ID). |
| **F2 — Google push** | `catalog_projection_google.py` (Merchant API). Feed pull já cobre o básico. | credenciais Google (service account + Merchant ID). |
| **F3 — WhatsApp Catalog** | reuso do adapter Meta + `Showcase(kind=whatsapp)` curado (≤500) + validação de limite. | WABA + Business Manager; homologar reuso. |
| **F4 — Mídia rica** | modelo `ProductImage` (S3/Spaces), múltiplas imagens/vídeo por plataforma. | **media persistente (Spaces/S3)** — pré-go-live. |
| **F5 — TikTok Shop** | `catalog_projection_tiktok.py` (Products API, variants, inventory, webhooks). | Global Partner Portal + credenciais; decidir escopo. |
| **F6 — Regras & agendamento** | publish rules avançadas, agendar publicação (Directive `available_at`). | F1-F2. |

**MVP recomendado = F0 + F1 + F2** (Meta cobre 3 plataformas; Google via push ou feed). WhatsApp
(F3) logo após, se as credenciais Meta já estiverem no ar. TikTok (F5) é onda própria.

---

## 8. Decisões abertas / riscos (para o Pablo)

1. **Escopo TikTok Shop:** entra no micro PIM (F5, peso ≈ iFood) ou fica fora (foco em Meta+Google)?
   BR está live, mas a integração é marketplace-completa, não só catálogo.
2. **Mídia antes ou depois:** a mídia rica social depende de S3 (pré-go-live). Ok começar F0-F2 com
   `image_url`+`gallery` (URLs já hospedadas) e adiar F4?
3. **`google_product_category`:** embarcar a taxonomia Google (CSV ~5k linhas) ou pedir só o path
   livre e validar leniente? Sugestão: select2 com a taxonomia embarcada.
4. **Conflito canônico × plataforma:** se um valor é editado na plataforma (ex.: alguém muda no
   Commerce Manager), a política é *internal-always-wins* (push sobrescreve)? — herdar a decisão do
   HUB (ainda aberta lá).
5. **WhatsApp = mesmo catálogo Meta?** confirmar em homologação (mesmo `catalog_id` + recorte, ou
   catálogo dedicado ao número). Afeta se F3 é "grátis" após F1.
6. **`data.price` do Meta batch** (inteiro+moeda vs string): validar por versão antes de F1.
7. **Split PIM/Offer formal:** este doc mantém o split *conceitual* (metadata social = PIM;
   ListingItem = Offer por canal). Formalizar em modelos separados (estilo Shopify Publication+PriceList)
   só "quando escalar" — **não** neste micro PIM. Confirmar que está de acordo.

---

## 9. Reuso — checklist (não reinventar)

- Modelo canônico: `Product` + **`ListingItem`** (pub/preço por canal) + `Collection` (`rule`/smart).
- Vitrine/feed: **`shop.Showcase`** (`kind`), **não** o `Channel.capability/content` (morto).
- Projeção: `CatalogProjectionBackend` (`project`/`retract`), registry `OFFERMAN["PROJECTION_BACKENDS"]`,
  delta por SKU (handler) + reconcile por listing (`project_listing`/`last_projected_skus`).
- Payload: `ProjectedItem` + `catalog_exports.build_catalog_export()` — **enriquecer com `metadata["social"]`**.
- Feed: specs `g:` verificadas em [CATALOG-FEEDS-GOOGLE-META](CATALOG-FEEDS-GOOGLE-META.md) (verbatim).
- Padrão de campo PIM: dataclass em `Product.metadata` (como `nutrition_facts` / `metadata["fiscal"]`).
- Auto-trigger: `handlers/catalog_projection.py` (ampliar campos projetáveis).
- Convenção de arquivo: `shopman/shop/adapters/catalog_projection_{plataforma}.py`; comando `sync_catalog_{plataforma}`.

---

## Fontes (pesquisa de plataforma, 2026)

- Meta Commerce Catalog — campos obrigatórios/opcionais, availability/condition enums, items_batch, Product Sets: [productfeedspec.com/platforms/meta-catalog](https://productfeedspec.com/platforms/meta-catalog), [Meta Business Help — Catalog eligibility](https://www.facebook.com/business/help/1205792533104321), [webappick — Meta feed specs 2026](https://webappick.com/facebook-product-feed-specifications-the-definitive-guide/)
- WhatsApp Catalog — limites (500/1 catálogo/10 imagens), retailer_id: [Meta for Developers — Catalogs overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/catalogs/catalogs-overview/), [WhatsApp Help — About catalog](https://faq.whatsapp.com/405903568419894), [Chatarmin — WhatsApp Catalog 2026](https://chatarmin.com/en/blog/whatsapp-business-catalog)
- Google Merchant — atributos obrigatórios, GTIN/brand/google_product_category: [Google — Product data specification](https://support.google.com/merchants/answer/7052112), [Google — GTIN](https://support.google.com/merchants/answer/6324461), [storegrowers — feed attributes](https://www.storegrowers.com/google-merchant-center-feed-attributes/)
- TikTok Shop — disponibilidade BR, Products API, Partner Center: [TikTok Shop Partner Center — Products API](https://partner.tiktokshop.com/docv2/page/products-api-overview), [bebolddigital — 2026 TikTok Shop requirements](https://www.bebolddigital.com/blog/tiktok-shop-requirements)
