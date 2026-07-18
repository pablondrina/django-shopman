# SOCIAL-PIM-IMPLEMENTATION-PLAN — Plano de execução

> **Status:** 🚧 Em execução. **Arcs A, B, C, D ✅ no main** (commits 76ad8c39, 09db84a6,
> 48c6db86, 3a84ed54) — MVP interno completo, sem credencial. Próximo: Arc E (Meta) ou H (matriz).
> Deriva de [SOCIAL-PIM-SPECS](SOCIAL-PIM-SPECS.md).
> **Data:** 2026-07-18
> **Regra de ouro:** cada Arc é **fechado, testável e implementável numa sessão**. **Backend e
> frontend nunca na mesma Arc.** Valor incremental: a primeira Arc já funciona sozinha.

**Cross-refs:** [SOCIAL-PIM-SPECS](SOCIAL-PIM-SPECS.md) ·
[CROSS-CHANNEL-CATALOG-HUB-PLAN](CROSS-CHANNEL-CATALOG-HUB-PLAN.md) ·
[CATALOG-FEEDS-GOOGLE-META](CATALOG-FEEDS-GOOGLE-META.md) ·
[CATALOG-SYNC-EXTERNO-PLAN](CATALOG-SYNC-EXTERNO-PLAN.md) ·
[PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md) · archive `redesign/PLAN.md` (WP10/WP11) ·
`redesign/07-spec-backoffice.md` (§2.1, §4.1).

---

## 0. Mapa das Arcs (visão de uma tela)

| Arc | Título | Camada | Complex. | Bloqueio externo | Depende de |
|---|---|---|---|---|---|
| **A** ✅ | Campos PIM sociais + admin | Backend (Offerman contrib) | **M** | ❌ nenhum | — |
| **B** ✅ | Enriquecer projeção + ampliar gatilho | Backend (Offerman) | **M** | ❌ nenhum | A |
| **C** ✅ | `CatalogSyncState` + status por plataforma | Backend (orquestrador) | **M** | ❌ nenhum | — (paralela a A/B) |
| **D** ✅ | Regras de publicação (form Unfold DEFERIDO p/ pós-adapters) | Backend (orquestrador) | **M** | ❌ nenhum | B, C |
| **E** | Adapter Meta (IG/FB) | Backend (adapter) | **G** | ⚠️ creds Meta p/ live | A, B, C |
| **F** | Adapter Google Merchant (push) | Backend (adapter) | **G** | ⚠️ creds Google p/ live | A, B, C |
| **G** | WhatsApp Catalog (recorte curado) | Backend (adapter+Showcase) | **M** | ⚠️ WABA+BM p/ live | E |
| **H** | Matriz produto×plataforma (extensão) | **Frontend** (orders-nuxt) | **G** | ❌ (mostra o que houver) | C (+ D/E úteis) |
| **I** | Mídia rica (`ProductImage`) | Backend | **G** | 🔴 media persistente (S3/Spaces) | A |
| **J** | Adapter TikTok Shop | Backend (adapter) | **G** | ⚠️ TikTok Partner + decisão de escopo | A, B, C |

**Sequência recomendada (valor incremental):**
`A → B → C → D → E → (H) → F → G → I → J`

- **MVP interno (sem credencial): A + B + C + D** — o operador já centraliza os dados PIM, o sistema
  sabe sincronizar e registrar status, e as regras de publicação funcionam. Nada externo bloqueia.
- **Primeira plataforma real: E (Meta)** — cobre IG + FB (+ WhatsApp na G). Depois **H** entrega a
  matriz "ultra fácil". **F** (Google) reforça o que o feed pull já faz. **I/J** são ondas próprias.

---

## 1. Decisões de arquitetura (já tomadas — não reabrir)

Fixadas pelas specs e pelos invariantes do hub. Cada Arc obedece:

| Decisão | Valor | Onde |
|---|---|---|
| **Campos PIM = metadata tipada, não coluna** | `Product.metadata["social"]` via dataclass `ProductSocialAttributes` (padrão `NutritionFacts`/`metadata["fiscal"]`). **Zero migração no Core.** | Arc A |
| **PIM vive em contrib do Offerman** | `packages/offerman/shopman/offerman/contrib/social/` (padrão Fiscalman: estende Product admin via metadata). **Não** pacote `socialman`. | Arc A |
| **Sem campo de canal no `Product`** | Disponibilidade por plataforma = `ListingItem` (transacional) + `Showcase` (feed). Reuso. | A, C, G, H |
| **Projeção = `CatalogProjectionBackend`** | Cada plataforma = adapter em `shopman/shop/adapters/catalog_projection_<plat>.py`, registrado em `OFFERMAN["PROJECTION_BACKENDS"]`, `off by default` atrás de env. | E, F, G, J |
| **Enriquecer `ProjectedItem`, não trocar o contrato** | `get_projection_items` (Offerman `service.py`) injeta `metadata["social"]`+galeria no `ProjectedItem.metadata` (additivo). | Arc B |
| **Status de sync = modelo novo fino no orquestrador** | `shopman/shop/models/catalog_sync.py` → `CatalogSyncState(sku, platform, external_id, status, last_synced_at, last_error, last_payload_hash)`. Migração no shop, não em package. | Arc C |
| **Regras de publicação = config + guards no handler** | `Shop.defaults["social_publish"]`; guards no auto-trigger existente. Sem lógica de negócio nova no Core. | Arc D |
| **Matriz = EXTENSÃO do que já existe** | Frente 3 já entregou `backstage/{api,projections,services}/catalog.py` + `orders-nuxt/app/pages/catalog.vue`/`useCatalogMatrix.ts`. Arc H adiciona colunas de plataforma + painel PIM. | Arc H |
| **Feed/vitrine = `shop.Showcase`** | `kind` = google/meta (existe); adicionar `whatsapp` (Arc G). **Não** o `Channel.capability/content` (morto). | G, H |
| **Ads/automação (WP11) fora de escopo** | "Anúncios sensíveis a contexto" (fornada saiu, só X croissants) é subsistema de marketing separado. Este plano é **catálogo/PIM** (WP10-estendido), não broadcast. | — |

---

## 2. Estado herdado — o que já está PRONTO (não refazer)

Do hub cross-channel e feeds (verificado em código):

- ✅ **Protocolo `CatalogProjectionBackend`** (`packages/offerman/.../protocols/projection.py`): `project`/`retract` + `ProjectedItem` + `ProjectionResult`.
- ✅ **Registry** `OFFERMAN["PROJECTION_BACKENDS"]` + `get_projection_backend()` por `listing_ref` (`offerman/service.py`, `offerman/conf.py`).
- ✅ **Adapter iFood** (`shopman/shop/adapters/catalog_projection_ifood.py`) — padrão-ouro (uuid5 determinístico, status inline, retract dedicado, categoria por config).
- ✅ **Auto-trigger** (`shopman/shop/handlers/catalog_projection.py`): signals → Directive `CATALOG_PROJECT_SKU` (dedupe SHA-256) → re-lê estado → project/retract; 429 requeue.
- ✅ **Reconciliação por listing** (`get_projection_items`/`project_listing` em `offerman/service.py`; `last_projected_skus` em `Listing.projection_metadata`).
- ✅ **Smart collections** (`Collection.rule`, `is_smart`, `product_queryset()`, `smart_collection.py`).
- ✅ **`Showcase`** (`shop.Showcase`, `kind` google/meta/menuboard, `collections`, `paused_skus()`).
- ✅ **Feed pull RSS** (`shopman/shop/views/product_feed.py`, `?platform=meta`) — Google/Meta pull sem credencial.
- ✅ **Export neutro** (`shopman/shop/services/catalog_exports.py`) — imagens em tupla, metadata completo.
- ✅ **Matriz produto×superfície (Frente 3)** — `backstage/{api,projections,services}/catalog.py` + `orders-nuxt` (`pages/catalog.vue`, `composables/useCatalogMatrix.ts`, `presentation/catalog.ts`, `types/catalog.ts`).
- ✅ **Import/export** de produto por SKU (`offerman/contrib/import_export/`).

**PENDENTE (o que este plano entrega):** campos PIM sociais estruturados · adapters Meta/Google/TikTok
push · status de sync por produto×plataforma · regras de publicação · matriz com eixo de plataforma
social + painel PIM · mídia rica (bloqueada em S3).

---

## 3. Arcs em detalhe

### Arc A — Campos PIM sociais + admin (Backend · Offerman contrib · **M**)

**Objetivo (o que fica pronto):** o operador edita marca, GTIN, categoria taxonômica, condição,
hashtags e legenda social de um produto no Admin, numa aba "Redes sociais"; tudo persiste em
`Product.metadata["social"]`, validado, com defaults inteligentes. **Funciona sozinho** (é a base do PIM).

**Arquivos a criar:**
- `packages/offerman/shopman/offerman/contrib/social/__init__.py`
- `packages/offerman/shopman/offerman/contrib/social/schema.py` — dataclass `ProductSocialAttributes` (`brand, gtin, mpn, google_product_category, condition, tiktok_category_id, hashtags, social_caption, platform_overrides`) + `from_metadata()`/`to_metadata()` + `errors()` (validação GTIN checksum, `condition` enum, categoria).
- `packages/offerman/shopman/offerman/contrib/social/taxonomy.py` — helper de `google_product_category` (CSV embarcado ou validação leniente — ver decisão aberta #3 das specs).
- `packages/offerman/shopman/offerman/contrib/offerman/…` **admin form** que insere o fieldset `("Redes sociais", {classes:("tab",)})` no `ProductAdmin` via `get_fieldsets` — **espelhar** `packages/fiscalman/shopman/fiscalman/contrib/offerman/admin.py`.
- `packages/offerman/shopman/offerman/contrib/social/tests/test_social_schema.py`

**Arquivos a modificar:** registrar o admin do contrib (settings `INSTALLED_APPS`/import onde o Fiscalman registra). **Nenhum modelo/migração.**

**Dependências:** nenhuma.

**Critério de done:**
- `ProductSocialAttributes.from_metadata(to_metadata(x)) == x` (round-trip).
- GTIN inválido/`condition` fora do enum ⇒ erro no form (não no `Product.clean()`).
- Salvar no admin grava `metadata["social"]`; abrir mostra os valores + defaults (`brand` vazio resolve `Shop.brand_name` na leitura).
- Testes verdes; `make admin` (gate Unfold) verde.

**Cross-ref:** realiza o `ProductFeedAttributes` proposto (mas não construído) em CATALOG-SYNC-EXTERNO §gaps.

---

### Arc B — Enriquecer projeção + ampliar gatilho (Backend · Offerman · **M**)

**Objetivo:** os campos PIM chegam aos adapters, e **editar um campo PIM re-sincroniza** (hoje não).

**Arquivos a modificar:**
- `packages/offerman/shopman/offerman/service.py` — `get_projection_items`: injetar `product.metadata["social"]` (+ galeria) em `ProjectedItem.metadata` (additivo; hoje só metadata do listing).
- `packages/offerman/shopman/offerman/models/product.py` — ampliar o gatilho: mudança em `image_url`, `keywords` e chaves relevantes de `metadata` (social/gallery) passa a emitir re-projeção. Opções: (a) incluir `image_url` em `_PROJECTABLE_FIELDS` + hash das chaves sociais no `save()`; (b) novo signal `product_pim_changed`. **Additivo, sem migração.**
- `packages/offerman/shopman/offerman/tests/…` — testes do enriquecimento + gatilho.

**Dependências:** Arc A (schema existe).

**Critério de done:**
- `get_projection_items` retorna `ProjectedItem.metadata["social"]` populado (ou default) por SKU.
- Editar `brand`/`image_url`/hashtag dispara `product_updated`/`product_pim_changed` → Directive de projeção.
- Testes cobrem: enriquecimento presente; edição de mídia/marca gera evento; edição irrelevante não gera.
- Suíte Offerman verde.

**Cross-ref:** corrige o gap "ProjectedItem ignora metadata/keywords" e "gatilho estreito" (SPECS G7).
Reusa o motor do HUB PR #25.

---

### Arc C — `CatalogSyncState` + status por plataforma (Backend · orquestrador · **M**)

**Objetivo:** o sistema registra, por (SKU, plataforma), o último sync, id externo, status e erro;
uma projeção/endpoint expõe isso. Fundação da matriz e dos adapters. **Sem credencial** (o iFood já
alimenta).

**Arquivos a criar:**
- `shopman/shop/models/catalog_sync.py` — `CatalogSyncState(sku, platform, external_id, status[synced|pending|error|retracted|skipped], last_synced_at, last_error, last_payload_hash, updated_at)`, `unique_together=(sku, platform)`.
- migração em `shopman/shop/migrations/` (orquestrador).
- `shopman/shop/services/catalog_sync.py` — `record_sync(sku, platform, result, external_id=…, payload_hash=…)` / `record_retract(...)` chamado pelos adapters/handler.
- testes: `shopman/shop/tests/test_catalog_sync_state.py`.

**Arquivos a modificar:**
- `shopman/shop/handlers/catalog_projection.py` — ao final de `project`/`retract`, chamar `record_sync`/`record_retract` (sucesso→synced+timestamp; erro→error+msg; 429→pending).
- `shopman/shop/adapters/catalog_projection_ifood.py` — devolver `external_id` (o item uuid) no `ProjectionResult` **ou** o handler deriva; gravar estado do iFood como primeiro cidadão.
- `shopman/backstage/projections/catalog.py` — adicionar, por produto, o mapa `{platform: {status, last_synced_at, error, available}}`.
- `shopman/backstage/api/catalog.py` — `GET …/catalog/sync-status?platform=&sku=` e `POST …/catalog/resync` (dispara `project_listing`/directive).

**Dependências:** nenhuma dura (roda com o iFood existente). Sinergia com B.

**Critério de done:**
- Após um sync iFood (dry-run/mock ok), existe uma linha `CatalogSyncState(sku, "ifood", status="synced", last_synced_at)`.
- `GET sync-status` retorna o estado por plataforma; `POST resync` reprojeta.
- Erro simulado ⇒ `status="error"` + `last_error`. 429 ⇒ `pending`.
- Testes verdes; `make admin` verde.

**Cross-ref:** realiza a "projeção de status de sync por canal" do backoffice spec §4.1 (substitui o
`last_projected_skus` cru como fonte de UI).

---

### Arc D — Regras de publicação (Backend · orquestrador · **M**)

**Objetivo:** produto novo entra (ou não) automaticamente por plataforma; só publica com estoque/imagem
quando exigido; base para agendar. **Sem credencial.**

**Arquivos a criar:**
- `shopman/shop/services/social_publish_rules.py` — lê `Shop.defaults["social_publish"]` (`{plataforma: {publish_on_create, require_stock, require_image, schedule?}}`); função `should_publish(sku, platform) -> bool|deferred`.
- testes: `shopman/shop/tests/test_social_publish_rules.py`.

**Arquivos a modificar:**
- `shopman/shop/handlers/catalog_projection.py` — aplicar as guardas antes de projetar (skip → `CatalogSyncState.status="skipped"` com razão; `require_stock` sem estoque → `pending` até `availability_changed`; `schedule` → Directive `available_at`).
- Admin/Unfold: expor `social_publish` na página de config (ShopIntegrations/ShopOrdering proxy) — form tipado (padrão `feedback_dataclass_driven_admin`).

**Dependências:** Arc B (gatilho) + Arc C (registrar skipped/pending).

**Critério de done:**
- `publish_on_create=false` ⇒ produto novo fica `skipped` naquela plataforma até publicação manual.
- `require_stock=true` sem estoque ⇒ `pending`; ao chegar estoque, projeta.
- `require_image=true` sem imagem ⇒ `skipped` (não manda payload que a plataforma rejeitaria).
- Testes cobrem as 3 guardas; suíte verde.

**Cross-ref:** SPECS §6.5 (G8). Guarda no motor existente, não lógica nova.

---

### Arc E — Adapter Meta (Instagram + Facebook) (Backend · adapter · **G**)

**Objetivo:** projetar/retratar o catálogo no Meta Commerce Catalog via `items_batch`; código+testes
completos com API **mockada**; live quando o Pablo prover credenciais.

**Arquivos a criar:**
- `shopman/shop/adapters/catalog_projection_meta.py` — `MetaCatalogProjection(CatalogProjectionBackend)`: `project` → `POST /v{N}/{catalog_id}/items_batch` (CREATE/UPDATE, `retailer_id`=sku, `data`={title, description, availability `in stock`/`out of stock`, condition, price, link, image_link, additional_image_link, brand, google_product_category, custom_label_0=coleção primária}); `retract` → batch DELETE/UPDATE availability. Batching ≤5000/call; respeitar ≤100 calls/h. Lê `ProjectedItem.metadata["social"]`.
- `shopman/shop/services/meta_auth.py` — System User token (env), header helper (espelha `ifood_auth`).
- `shopman/shop/management/commands/sync_catalog_meta.py` — `--full`/`--dry-run` (espelha `sync_catalog_ifood`).
- testes: `shopman/shop/tests/test_catalog_projection_meta.py` (payload correto, batching, retract, 429, dry-run) com `requests` mockado.

**Arquivos a modificar:**
- `config/settings.py` — `SHOPMAN_META` (catalog_id, api_version, token via env) + `IFOOD_CATALOG_PROJECTION`-style env-gate; registrar em `OFFERMAN["PROJECTION_BACKENDS"]` no `Listing`/Showcase Meta.
- `shopman/shop/services/catalog_sync.py` — gravar `external_id`=retailer_id, `platform="meta"`.

**Dependências:** A, B, C.

**Bloqueio externo:** ⚠️ **Meta Business** (System User access token + Catalog ID). Sem isso, roda em
`--dry-run`/mock; não vai live. (Não bloqueia o código nem os testes.)

**Critério de done:**
- `--dry-run` emite o batch JSON esperado para um catálogo Nelson (verificável em teste).
- `retract` gera DELETE/UPDATE correto; 429 respeita `Retry-After`.
- Enum de availability = **`in stock`/`out of stock`** (espaço), condition `new`.
- ⚠️ resolver `data.price` (inteiro+moeda vs string) por versão — documentar a escolha no adapter.
- Testes verdes; adapter `off by default`.

**Cross-ref:** realiza o adapter proposto em CATALOG-SYNC-EXTERNO (`catalog_projection_meta.py`) e o
push pendente em CATALOG-FEEDS (items_batch, Product Sets). Cobre IG + FB; WhatsApp na Arc G.

---

### Arc F — Adapter Google Merchant (push) (Backend · adapter · **G**)

**Objetivo:** push near-real-time ao Google via Merchant API (o feed pull continua como bootstrap/fallback).

**Arquivos a criar:**
- `shopman/shop/adapters/catalog_projection_google.py` — `GoogleCatalogProjection`: `project` → `products.insert/update`; `retract` → `products.delete` ou availability `out_of_stock`. `identifier_exists:false` sem GTIN. **Fixar a versão da API** (Content API depreciando → Merchant API).
- `shopman/shop/services/google_auth.py` — OAuth2 service account (env).
- `shopman/shop/management/commands/sync_catalog_google.py` (`--full`/`--dry-run`).
- testes: `shopman/shop/tests/test_catalog_projection_google.py` (mock).

**Arquivos a modificar:** `config/settings.py` (`SHOPMAN_GOOGLE`: merchant_id, service account, api_version); registry; `catalog_sync` (`platform="google"`).

**Dependências:** A, B, C.

**Bloqueio externo:** ⚠️ **Google Merchant Center** (service account + Merchant ID + projeto GCP).
Mock/dry-run sem isso.

**Critério de done:** `--dry-run` emite o corpo `products.insert` correto (enum `in_stock`/`out_of_stock`
com underscore; preço `12.00 BRL`); retract correto; `identifier_exists:false` sem GTIN; testes verdes.

**Cross-ref:** CATALOG-FEEDS "push pendente (Merchant API)"; complementa o feed RSS já vivo.

---

### Arc G — WhatsApp Catalog (recorte curado) (Backend · adapter+Showcase · **M**)

**Objetivo:** publicar um **recorte ≤500** do catálogo no WhatsApp Catalog, reusando o adapter Meta.

**Arquivos a criar/modificar:**
- `shopman/shop/models/…` (ou migração de `Showcase`) — adicionar `kind="whatsapp"` a `Showcase`.
- reuso de `catalog_projection_meta.py` com `channel="whatsapp"` alimentado por `Showcase(kind=whatsapp)` (coleções que somem ≤500 SKUs).
- validação de limite (500) na config do Showcase whatsapp (alerta no admin ao passar).
- testes: recorte respeita 500; sync usa o mesmo caminho Meta.

**Dependências:** Arc E (adapter Meta pronto).

**Bloqueio externo:** ⚠️ **WABA + Business Manager**; **homologar** se é o mesmo `catalog_id` do Meta ou
um dedicado ao número (decisão aberta #5 das specs).

**Critério de done:** `Showcase(kind=whatsapp)` resolve ≤500 SKUs; sync projeta só esse recorte;
validação bloqueia >500; testes verdes.

**Cross-ref:** SPECS §3.3/§6.3; único doc que trata WhatsApp como sync-target (CATALOG-SYNC-EXTERNO).

---

### Arc H — Matriz produto×plataforma (Frontend · orders-nuxt · **G**)

> **Frontend puro.** Estende a matriz da Frente 3 já entregue; consome as projeções/APIs das Arcs C/D.

**Objetivo ("ultra fácil"):** o operador vê, numa matriz produto × plataforma, o estado por célula
(publicado/pendente/pausado/erro/fora), publica/pausa com um clique, faz bulk pelo eixo coleção, e edita
os campos PIM num painel lateral.

**Arquivos a modificar/criar (todos em `surfaces/orders-nuxt/app/`):**
- `pages/catalog.vue` — adicionar colunas de plataforma social (IG/FB, WhatsApp, Google, TikTok) além dos canais atuais.
- `composables/useCatalogMatrix.ts` — consumir `catalog/sync-status`; ação de publicar/pausar por plataforma; "sincronizar agora"; ver erro.
- `presentation/catalog.ts` — derivar o selo por célula (🟢/🟡/⏸️/🔴/⚪) a partir do status; puro/testável (vitest).
- `types/catalog.ts` — tipos do sync-status.
- novo `components/CatalogPimPanel.vue` — painel lateral de campos PIM (brand/gtin/categoria/hashtags/mídia) com defaults preenchidos.
- BFF Nitro (`server/…`) proxy dos endpoints novos.
- testes vitest da presentation + guardrails da superfície.

**Dependências:** Arc C (status + APIs). Úteis: D (regras refletidas), E/F/G (plataformas reais para exibir).

**Bloqueio externo:** ❌ — mostra o que existir (iFood desde já; social conforme os adapters entram).

**Critério de done:**
- Matriz renderiza estado por (produto, plataforma); clique publica/pausa e o selo atualiza.
- Bulk "publicar coleção X no Instagram" funciona pelo eixo coleção.
- Painel PIM edita e salva (via API); defaults visíveis.
- vitest verde; `make admin`/guardrails de superfície verdes; QA visual no browser.

**Cross-ref:** EXTENSÃO da Frente 3 (HUB) — não recria. Backoffice spec §2.1/§4.1 (gestão por canal).

---

### Arc I — Mídia rica (`ProductImage`) (Backend · **G** · 🔴 bloqueada)

**Objetivo:** múltiplas imagens/vídeo por produto com papel/ordem/alt, URLs públicas estáveis;
migra a `metadata["gallery"]` para um modelo real.

**Arquivos:** `packages/offerman/shopman/offerman/models/…` (`ProductImage`: FK Product, arquivo em
Spaces, `role[main|gallery|social|video]`, `alt`, `sort`, dimensões) + migração + admin inline +
migração de dados da galeria + adapters passam a mandar `additional_image_link`/vídeo.

**Dependências:** Arc A.

**Bloqueio externo:** 🔴 **media persistente (Spaces/S3)** — filesystem efêmero perde imagem em
redeploy; agendado **pré-go-live** (PRODUCT-V1-SCOPE-BACKLOG). **Não desenvolver antes do S3.**

**Critério de done:** upload persistente; N imagens/roles; galeria migrada; adapters mandam mídia
adicional; testes verdes.

**Cross-ref:** SPECS §6.2 (G4); dependência de infra do backlog v1.

---

### Arc J — Adapter TikTok Shop (Backend · adapter · **G** · decisão de escopo)

**Objetivo:** projetar catálogo + variantes + inventário no TikTok Shop (BR live), com webhooks.

**Arquivos:** `shopman/shop/adapters/catalog_projection_tiktok.py` (Products API create/update/delete),
`services/tiktok_auth.py`, `management/commands/sync_catalog_tiktok.py`, webhook receiver em
`shopman/shop/webhooks/tiktok.py`, testes mock.

**Dependências:** A, B, C.

**Bloqueio externo:** ⚠️ **TikTok Global Partner Portal** + credenciais; **decisão de escopo** (peso ≈
iFood, marketplace completo). Decisão aberta #1 das specs.

**Critério de done:** dry-run emite payload TikTok correto; inventário/variantes mapeados; retract ok;
webhooks tratados; testes verdes.

**Cross-ref:** WP10 (archive) lista TikTok Shop; SPECS §3.3. Provável **onda própria**, não MVP.

---

## 4. Bloqueios externos (o que depende do Pablo)

| Recurso | Bloqueia | Necessário para |
|---|---|---|
| **Nada** | — | **Arcs A, B, C, D, H** (H mostra o que houver). Todo o MVP interno roda sem credencial. |
| **Meta Business** (System User token + Catalog ID) | ir live | **Arc E** (código/testes rodam em mock/dry-run sem isso). |
| **Google Merchant Center** (service account + Merchant ID + GCP) | ir live | **Arc F** (feed pull já cobre o básico sem credencial). |
| **WABA + Business Manager** (+ homologar catalog_id) | ir live | **Arc G**. |
| **TikTok Global Partner Portal** + decisão de escopo | começar | **Arc J**. |
| **Media persistente (Spaces/S3)** — infra | começar | **Arc I** (agendado pré-go-live). |

> **Padrão:** adapters entram `off by default` atrás de env (como `IFOOD_CATALOG_PROJECTION`). Código e
> testes não dependem de credencial (mock/dry-run). Só o "ligar em produção" depende do Pablo.

---

## 5. O que dos planos existentes já está feito vs entra aqui

| Plano | Feito (não refazer) | Entra neste plano |
|---|---|---|
| **CROSS-CHANNEL-CATALOG-HUB** | Auto-trigger (PR#25), registry, smart collections, Showcase, matriz Frente 3 (iFood/superfícies) | Arc H **estende** a matriz; Arcs B/C/D reusam auto-trigger+registry |
| **CATALOG-FEEDS-GOOGLE-META** | Feed pull RSS (Google/Meta, `?platform`) | Arc E/F = **push** por cima do pull; specs `g:` reusadas |
| **CATALOG-SYNC-EXTERNO** | Protocolo, adapter iFood, export neutro, `ProjectedItem` | Arcs A (realiza `ProductFeedAttributes`), E/F/G (adapters propostos) |
| **PRODUCT-V1-SCOPE-BACKLOG** | "sync externo" = frente v1 (fundação pronta) | Este plano é a execução da frente; Arc I depende de "media persistente" (backlog) |
| **archive redesign WP10** (sync catálogo) | contrato Core, iFood | Arcs C–G, J = os adapters + gestão que o WP10 pedia |
| **archive redesign WP11** (ads/automação) | — | **FORA de escopo** (subsistema de marketing/broadcast; não é catálogo/PIM) |

---

## 6. Riscos & notas de execução

- **Core sagrado:** Arcs A/B/I tocam Offerman. A = só contrib (zero Core). B = additivo no `service.py`/`product.py` (sem migração). I = modelo novo (migração em Offerman) — só pós-S3. Tudo o mais é orquestrador/superfície.
- **`data.price` do Meta batch** e **versão da Google API**: validar em homologação antes de E/F (specs §8.6/#8).
- **WhatsApp = mesmo catálogo Meta?** confirmar antes de G (specs §8.5) — muda se G é "quase grátis" após E.
- **`google_product_category`:** decidir taxonomia embarcada vs leniente (specs §8.3) — afeta Arc A.
- **Conflito canônico × plataforma** (internal-always-wins?) — herdar do HUB; afeta E/F/G (política de sobrescrita).
- **Ampliar o gatilho (Arc B)** com cuidado: não disparar re-sync em massa por edições irrelevantes (usar hash das chaves sociais, não `metadata` inteiro).
- **Testes:** cada Arc backend fecha com sua suíte + `make admin` (gate Unfold quando toca admin) + `make test`. Arc H fecha com vitest + guardrails de superfície + QA no browser. Nunca misturar as duas.

---

## 7. Ordem sugerida de sessões (uma Arc por sessão)

1. **Arc A** — PIM fields + admin (valor imediato, zero externo).
2. **Arc B** — enriquecer projeção + gatilho.
3. **Arc C** — CatalogSyncState + status/API.
4. **Arc D** — regras de publicação.
5. **Arc E** — adapter Meta (code+mock; live quando houver creds).
6. **Arc H** — matriz (frontend) — já mostra iFood+Meta.
7. **Arc F** — adapter Google (push).
8. **Arc G** — WhatsApp (recorte).
9. **Arc I** — mídia rica (após S3).
10. **Arc J** — TikTok (onda própria, se aprovado).
