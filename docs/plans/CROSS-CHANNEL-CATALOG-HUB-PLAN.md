# Plano — Gestor de Pedidos como HUB cross-channel (pedidos + cardápio)

> Visão do Pablo (2026-07-01): enriquecer o nosso **Gestor de Pedidos** para ser, no espírito do
> iFood, um hub único que além de **gerir pedidos** (aceitar/recusar/cancelar com motivo, KDS) também
> **gerencia o cardápio cross-channel** — CRUD, sincronização, pausa, publicação, preços, descrições
> curta/longa, keywords, fotos, info nutricional/dietética, "TUDO". E é o lugar natural para
> sincronizar com catálogos externos: **iFood, Google, Meta/Instagram, WhatsApp**.
>
> ⚠️ Continuar em **nova sessão**. Este doc preserva o contexto.

## Estado atual verificado (2026-07-01)

### O que já existe no nosso Core
- **Disponibilidade por canal**: `ListingItem.is_published` / `is_sellable` (por listing = por canal).
  UI no Admin/Unfold: `ListingItemInline` (checkboxes por canal) + ações de produto (pause/resume,
  mas **globais**, via `queryset.update()`).
- **Motor de retract JÁ PRONTO**: `CatalogService.project_listing()` faz diff de `last_projected_skus`
  e chama `backend.project()` (upsert dos publicados+vendáveis) + `backend.retract()` (dos
  despublicados/removidos). **Mas está dormente** — só os testes chamam `project_catalogs()`.
- **Projeção iFood v2.0** (`catalog_projection_ifood`): `project()` (PUT item) + `retract()`
  (PATCH status UNAVAILABLE) — **verificados AO VIVO**. Sem imagem inline (iFood 500).
- **Nutrição/dietético**: Craftsman deriva alergênicos/dieta/nutrição das receitas (recipe derivation).

### O gap de wiring (histórico — estado ANTES do auto-trigger + Frente 1)
> Registro do gap original. **1-2 resolvidos pelo auto-trigger (PR #25)**; **4-5 resolvidos pela
> Frente 1** (ver follow-ups abaixo). **3 permanece parcial**: `project_listing` já tem caller de
> produção (o comando `sync_catalog_ifood`), mas ainda não há gatilho de reconciliação para bulk/
> deleção — é a ponte para a Frente 3.
1. Toggle de `is_sellable`/`is_published` **não dispara signal** (`ListingItem.save()` só emite
   `price_changed`, e só em mudança de preço). Ações de produto usam `queryset.update()` (nem `save()`).
2. O handler de projeção só escuta `product_created` + `price_changed`.
3. `project_listing()` (com retract) **não tem caller de produção** (só testes).
4. O comando `sync_catalog_ifood` usa `backend.project()` cru — **não retrata**.
5. Adapter iFood **desligado** em settings (`SHOPMAN_CATALOG_PROJECTION_ADAPTERS` comentado).

### Auto-trigger — ✅ FEITO (2026-07-01, verificado ao vivo)
Fatia entregue (commit no PR #25), reaproveitando a infra existente:
- Signals novos no Offerman: `product_updated` (nome/desc/publish) + `availability_changed`
  (pausa por canal), emitidos de `save()` como os já existentes.
- `CatalogProjectHandler` agora **retract-aware**: lê estado atual → `project()` (publicado+vendável)
  ou `retract()` (pausado/removido). Directive idempotente ao estado final.
- Receivers `on_product_updated`/`on_availability_changed` → mesmo directive `catalog.project_sku`.
- Adapter habilitável por env `IFOOD_CATALOG_PROJECTION` (off por padrão; no-op sem adapter).
- **Verificado ao vivo**: pausar `is_sellable=False` → iFood UNAVAILABLE; reativar → AVAILABLE.

### ⚠️ Follow-ups descobertos (para o hub, decisão deliberada — NÃO ramar às cegas)
1. ✅ **FEITO (Frente 1, 2026-07-01)** — **Registry de projeção unificada.** A canônica é a do
   **Offerman** (`OFFERMAN["PROJECTION_BACKENDS"]` + `get_projection_backend()`); o kernel é dono do
   contrato, o adapter concreto fica no shop, alcançado por dotted-path (sem import cruzado). O
   `SHOPMAN_CATALOG_PROJECTION_ADAPTERS` foi **aposentado**: o handler/signals do shop
   (`_register_catalog_projection_handler`, `_projection_listing_refs`) agora resolvem via offerman.
   O env-gate `IFOOD_CATALOG_PROJECTION` passou a popular a registry canônica (default-off preservado).
   Achado que mudou o desenho: **não havia adapter iFood duplicado no offerman** (era só exemplo de
   docstring). Os dois retracts são **complementares, não redundantes**: per-SKU (handler, delta
   event-driven) vs per-listing (`project_listing`, reconciliação por diff de `last_projected_skus`).
2. ✅ **FEITO (Frente 1, 2026-07-01)** — **`sync_catalog_ifood` retract-aware.** Roteado por
   `CatalogService.project_listing("ifood", full_sync=…)`: incremental reconcilia (upsert dos
   publicáveis + retract dos despublicados/removidos + persiste `last_projected_skus`); `--full` faz
   upsert-all sem retract. Sem backend configurado → `CommandError` claro. Testes novos cobrindo
   full/incremental-retract/not-configured. `make test` verde.
3. **Imagem**: projeção não sincroniza foto (iFood exige upload separado/`imagePath`). Fluxo à parte.

> **Ponte para a Frente 3 (deixada de propósito):** bulk actions do admin e deleções de
> `ListingItem`/`Product` usam `queryset.update()`/`delete()` → **não chamam `save()` → não emitem
> signal** → o delta per-SKU (handler) não os vê. Quem os pega é a reconciliação per-listing
> (`project_listing`, via diff). Portanto as **ações em lote da matriz (Frente 3)** devem rotear por
> `project_listing` (reconciliação), não emitir N signals. O resolver unificado já é o seam pronto.

## Referência — Cardápio do iFood (Portal do Parceiro, verificado ao vivo 2026-07-01)

Estrutura em abas: **Cardápio | Produtos | Complementos | PDV**.

- **Cardápio** ("Defina quais os itens seus clientes podem pedir"): categorias → itens.
  - Por **categoria**: editar nome, **Criar combo**, **Criar oferta**, **⏸ pausar categoria**, ⋮, colapsar.
  - Por **item**: foto, nome + tag ("Oferta Simples"), descrição curta, **Complementos [n]**,
    **Estoque**, **preço** (com "preço inteligente"), tag/promoção, **▶/⏸ pausar item**, ⋮.
- **Produtos** (CRUD): filtros **Todos/Pausados/Ativos** + busca + **Criar produto**. Colunas:
  Produto (foto+nome+descrição), Classificação ("Item principal"), **Disponível em** (categoria),
  **▶/🗑** por linha.
- **Edição de produto** — abas **Sobre o produto / Grupo de complementos / Disponível em**:
  - *Sobre*: **Nome** (80), **Descrição** (1000), **Imagem**, **Estoque** (ativar), e
    **"Destaque seu produto"** → **Restrições alimentares** (Vegano/Vegetariano/Orgânico/Sem açúcar/
    Sem lactose/Sem glúten), **Bebidas** (gelada/alcoólica/natural), **Tamanho** (serve até / peso+unidade).
  - **Preview ao vivo** do card no app iFood (foto, nome, descrição, badges dietéticos).
- **Gestor de Pedidos** (app externo `gestordepedidos.ifood.com.br`) — ⚠️ **não inspecionado**
  (navegar no domínio pelado desloga; abrir pelo link interno do Portal na próxima). Sabemos que faz
  fila de pedidos + confirmar/despachar/pronto + cancelar com **motivo coded** (já replicamos os
  callbacks + o seletor de motivo).

## Dois eixos de gestão: CANAL × COLEÇÃO (requisito do Pablo, 2026-07-01)

O gerenciamento do cardápio deve ser natural pelos **dois eixos**, não só por canal:

- **Por CANAL** (onde vende): iFood, web, PDV, WhatsApp, delivery próprio… — disponibilidade/preço/
  publicação por canal (o que já temos em `ListingItem`).
- **Por COLEÇÃO** (como agrupa): Pães rústicos, Folhados, Veganos, Promoções, Natal… — operar a
  **coleção inteira**: pausar/publicar/reprecificar/sincronizar todos os itens de uma coleção (num
  canal, ou em todos). Base já existe: `Collection` + `collection_items` (`is_primary`) no Offerman.

**Omotenashi para o operador**: a UI deve deixar trivial alternar entre "estou olhando o canal X" e
"estou olhando a coleção Y", e agir em lote em qualquer um dos recortes — sem fricção, sem duplicar
trabalho. Pense numa **matriz produto × canal** filtrável/agrupável por coleção, com ações em lote
scoped ao recorte ativo (coleção, canal, ou seleção).

Pontos a resolver no design:
- Ação em lote por coleção → itera os `ListingItem` dos produtos da coleção no(s) canal(is) alvo →
  dispara os signals já existentes (`availability_changed` etc.) → projeção por canal. Reusa o motor.
- Coleção pode ser **transversal a canais** (uma coleção "Veganos" existe conceitualmente; a projeção
  respeita quais itens estão em quais listings/canais).
- Evitar explosão combinatória na UI: agrupar, colapsar, e usar seleção + ação em lote.

## Benchmarks da indústria — síntese de pesquisa (2026-07-01)

> Deep-research verificado (24 claims confirmadas por voto adversarial, fontes primárias/vendor
> docs). Cobertura forte: **Shopify, Toast, Square, Uber Eats**. NÃO verificado (tratar como aberto):
> Google Merchant Center, Meta Commerce Manager, TikTok/IG, Odoo, Rappi, Deliveroo.

### O princípio convergente (o padrão-ouro a seguir — Shopify)
- **Produto canônico único + objeto de junção por contexto.** No Shopify, um `Catalog` = `Publication`
  (o que é visível) + `PriceList` (a que preço), atrelado a um contexto (Market/Location/App-canal).
  **Desacopla "o quê é visível" de "a que preço"**, ambos scoped ao canal.
  → **Nós já temos isso**: `ListingItem` (produto × listing) É esse objeto de junção — carrega
  `is_published`/`is_sellable`/`price_q` por canal. Confirma nossa arquitetura; não inventar campos de
  canal no `Product`.
- **Visibilidade NUNCA é flag global** — é registro de publicação por contexto. Estar no catálogo não
  basta; o produto precisa ser **explicitamente publicado no canal**. → disponibilidade = par
  (item × canal), nunca um booleano "ativo" único. A projeção p/ iFood/Google/Meta é um ato de
  publicação por canal (é o que o auto-trigger já faz).
- **Anti-explosão combinatória**: decompor em catálogos **só-preço** (1 por lista de preço) + catálogos
  **só-publicação** (1 por sortimento) e **compô-los**, em vez de 1 por combinação (Shopify: ~97% menos
  config). → **Separar PREÇO de SORTIMENTO/DISPONIBILIDADE** como dimensões independentes componíveis
  por canal. (Hoje ambos vivem juntos no `ListingItem`; avaliar separar preço-por-canal de
  disponibilidade-por-canal quando escalar.)

### O eixo COLEÇÃO (o que o Pablo pediu) — como os líderes resolvem
- **Smart collections por CONDIÇÕES** (Shopify): até 60 condições (tag, tipo, preço, estoque,
  metafield…) com lógica **all/any (AND/OR)**, auto-populadas, sem atribuição manual. Servem de **alça
  natural para bulk ops e saved views**: "todos os pães", "em promoção", "esgotáveis do dia" viram
  escopos VIVOS que se atualizam sozinhos. → nossas `Collection` são manuais; **coleções por regra**
  são um upgrade forte para o eixo coleção.
- **Disponibilidade da coleção é ela mesma per-canal** (Shopify: checkbox por sales channel no editor
  da coleção). **Esse é o cruzamento direto CANAL × COLEÇÃO**: a coleção existe canonicamente e
  projeta-se por canal. → materializar como **matriz operável**: escopo = (coleção), alvo = (canal);
  a ação em lote itera os `ListingItem` dos produtos da coleção no(s) canal(is) alvo e dispara os
  signals que já temos (`availability_changed`) → projeção. **Reusa 100% o motor.**

### Fricções a EVITAR (aprendendo com food/delivery — e superando)
- **Toast**: visibilidade por parceiro só no nível do **MENU inteiro** (não item/grupo/modifier) →
  força multiplicar menus por parceiro. **Nós devemos ter targeting de canal por ITEM e por COLEÇÃO**
  — já supera todos os POS de restaurante.
- **Parceiro tem a palavra final** (Uber/DoorDash): visibilidade/86/timed-pricing frequentemente NÃO
  honrados; capacidades assimétricas por canal. → a UI deve mostrar **o que cada canal SUPORTA** e o
  **último estado sincronizado**, nunca prometer paridade cega (vale p/ a integração DIRETA iFood).
- **Pausa operacional ≠ disponibilidade de catálogo.** Uber Eats "pause new orders" = loja inteira,
  time-boxed, com motivo e retomada. É um **kill-switch operacional**, distinto do "esgotado" por item.
  → tratar como **primitivas diferentes** (nossa `feedback_transparent_timeouts` já pede TTL+UI+notif).
- **Cascata de disponibilidade explícita, não silenciosa** (Uber: horário do menu envelopa o item).
  Se um envelope (canal/coleção) corta o item, mostrar **por quê** — evita "por que meu item sumiu".

### Sync cross-channel (o padrão canônico)
- **Full sync (bootstrap) + incremental/delta (deltas)**, com **publicação por canal como filtro de
  projeção** (Shopify Product Feeds API: `PRODUCT_FEEDS_FULL_SYNC` + `incremental_sync`). Square:
  **um único estado canônico** de disponibilidade propaga a todos os canais integrados (fonte da
  verdade interna; canais são projeções). → alinha com a lei do projeto: **signal** anuncia mudança,
  **directive** faz o comando async confiável (retry/idempotência). É exatamente o que temos; falta o
  **full-sync idempotente** por canal (reconciliação) além do delta por-SKU já entregue.

### Recomendações concretas p/ Offerman (destilado)
1. **Manter o `ListingItem` como o "channel projection"** (já é o padrão Shopify) — validar.
2. **Coleções por regra** (condições AND/OR sobre atributos) como alça de bulk + saved views vivas.
3. **Matriz produto × canal** filtrável/agrupável por coleção; ações em lote scoped a (coleção|canal|
   seleção); estado de sync por célula (último estado + o que o canal suporta).
4. **Separar pausa operacional (loja/canal, time-boxed, c/ motivo) de disponibilidade de catálogo.**
5. **Full-sync idempotente por canal** (reconciliar via `project_listing`) + delta por evento (feito).
6. **Consolidar as duas registries** (pré-requisito já registrado) antes de escalar canais.

### Perguntas em aberto (resolver no design)
- **Conflito canal↔canônico**: quando o iFood muda um item por fora — last-write-wins, fonte interna
  sempre vence, ou merge por campo? (nenhum benchmark verificado deu política além de "parceiro manda").
- **Google Merchant (supplemental feeds + `custom_label_0..4`) e Meta (catalog sets)**: análogos das
  smart collections p/ ads — **mapear antes** de desenhar as projeções Offerman→Google/Meta.
- **Multi-coleção com disponibilidades conflitantes** projetadas em canais diferentes: precedência,
  união ou interseção?
- **Ergonomia da matriz** item×canal (grid editável, filtros, saved views): benchmarks confirmam
  checkbox-por-canal + coleções-por-regra, mas não a UX de alternar eixos sem fricção — é onde vamos
  inovar (omotenashi).

**Fontes primárias**: Shopify Catalogs/Markets/Collections/Product-Sync docs; Toast partner-visibility
+ integration-limitations; Square item-availability; Uber Eats menu-hours + pause-orders.

## ⭐ Refinamento decisivo: SUPERFÍCIE, não só "canal" (Pablo 2026-07-01)

Insight do Pablo: nem todo alvo de projeção é "canal de vendas". Google Merchant, Meta/IG e um
**menuboard** (TV) mostram um recorte de produtos, mas **não é ali que a venda transaciona**. O
primitivo certo é mais geral e unifica tudo:

**SUPERFÍCIE** (generaliza "canal") = qualquer alvo onde um recorte do catálogo é projetado/renderizado.
Três atributos:
- **tipo/adapter**: iFood API · web storefront · PDV · WhatsApp · Google feed · Meta catalog · **menuboard** · KDS…
- **capacidade**: `transacional` (aceita pedido) | `display/feed` (só mostra/anuncia).
- **fonte de conteúdo = uma COLEÇÃO** (ou regra/conjunto de coleções) define **o QUE aparece**; +
  overrides por superfície (preço/disponibilidade/layout).

Classificação das superfícies:
- **Transacionais**: iFood, web próprio, PDV, WhatsApp/delivery próprio.
- **Feed/anúncio**: Google Merchant (feed = coleção "vendáveis online"; `custom_label` = sub-recortes),
  Meta/IG catalog (catalog = coleção; **sets** = sub-coleções p/ targeting), TikTok.
- **Display in-loco**: **menuboard** (TV) — cada tela é uma superfície display alimentada por uma
  coleção ("Café da manhã", "Pães & padaria"), renderizada **em tempo real**.

**Por que é a abordagem mais simples/robusta/elegante:**
- **Um só primitivo de projeção** (Superfície) + **um `CatalogProjectionBackend` por tipo** — iFood/
  Google/Meta/menuboard viram adapters. O protocolo já existe em offerman.
- A **coleção como fonte de conteúdo universal** resolve o eixo CANAL×COLEÇÃO naturalmente: "esta
  superfície mostra esta coleção". Bulk ops = por coleção; disponibilidade/preço = por (item×superfície).
- Os **signals + motor de projeção (auto-trigger) que já entregamos servem TODAS as superfícies** —
  inclusive o menuboard, via o **SSE que já existe** (django-eventstream + daphne;
  ver [[project_sse_push_active]]).
- Distingue honestamente `transacional` de `display/feed` — a UI mostra **capacidades reais** por
  superfície (aprendizado do Toast: nunca prometer paridade cega).
- Alinha com a pesquisa: Shopify separa *Publication* (o que é visível) de *transacionar*; Google/Meta
  são publication surfaces alimentadas por um recorte. Nossa "Superfície" é essa generalização honesta.

### 📺 Menuboard dinâmico (PROJETO NOVO — anotado)
Hoje: **2 TVs** estilo "quadro-negro pintado à mão", **estáticas**. Meta: **menuboard dinâmico ligado
ao Django Shopman** — uma **superfície display** alimentada por coleção, atualizada **em tempo real**
(pausar item / mudar preço / esgotar reflete na TV na hora). Reusa 100% o motor de projeção + push
(SSE) que já existe. Provável **nova superfície Nuxt** (`surfaces/menuboard-*`) assinando o stream da
coleção, com layout "chalkboard" fiel à marca Nelson. Adapter `menuboard` = mais um
`CatalogProjectionBackend`/consumidor de eventos.

## Frente 2 — ✅ FEITO (2026-07-01): primitivo Superfície + coleções por regra

Decisões (aprovadas): **Shape 1** (formalizar sobre o modelo atual, zero migração no Core para a
Superfície) + **`rule` JSONField em Collection**. Verificado no código antes: Channel não tem campo
de tipo/capacidade (classifica por convenção de `ref`); Listing/Channel ligam por convenção
`ref==ref`; a registry canônica (Frente 1) já é keyed por `listing_ref` → o **Listing já é a espinha
da superfície**. O que faltava era só a **capacidade** e a **fonte-coleção**.

- **WP-2a (shop, zero migração Core)** — `capability` (`transactional|display|feed`, default
  `transactional`) + aspecto `content` (`source: listing|collection` + `collection` ref) no
  `ChannelConfig`. Vivem em `Channel.config` (JSON), como os outros 8 aspectos; cascata + validação.
  Os 5 canais seedados permanecem `transactional`/`content=listing` por default. 12 testes.
- **WP-2b (offerman Core, migração `0006_collection_rule`)** — `rule` JSONField em `Collection` +
  resolver `offerman/smart_collection.py`. Schema `{match: all|any, conditions:[{field,op,value}]}`;
  campos keyword/sku/name/unit/base_price_q/is_published/is_sellable/collection; ops
  eq/ne/lt/lte/gt/gte/in/contains. `Collection.is_smart` + `Collection.product_queryset()` (regra se
  smart, senão CollectionItems). Smart vs manual é **exclusivo** (Shopify-style). `clean()` valida a
  regra. 18 testes.
- **WP-2c (não-dormente)** — smart collections resolvem de verdade nos dois consumidores canônicos de
  "produtos numa coleção": `CatalogService.search(collection=…)` e a API de catálogo do storefront
  (página de coleção do cliente). Ambos via `Collection.product_queryset()`.

**Fora do escopo da Frente 2 (deliberado):** UI de admin para editar `rule`/`capability` (Admin/Unfold
Canonical Gate) e o **materializador coleção→ListingItems** vão para a **Frente 3** (matriz + bulk).
Nesta frente o motor está pronto e consumido; a criação de smart collection é via seed/shell/API até a
UI da Frente 3.

## Direção de arquitetura (rascunho — validar na próxima sessão)

- **Um catálogo canônico interno** (Offerman) → **projeções por canal** (adapters), com o
  `project_listing` (retract-aware) como motor único. Nosso `ProjectedItem` já carrega
  name/description/price/keywords/dietary/metadata.
- **Superfície no Gestor** (`orders-uithing-nuxt` ou superfície nova): CRUD de produto (nome, desc
  curta/longa, foto, keywords, nutricional/dietético), disponibilidade **por canal** (matriz
  produto×canal), pausa 1-clique, publicação, preço por canal, sync status por canal.
- **Cross-channel**: iFood (pronto), e seams para Google Merchant / Meta&IG / WhatsApp Catalog —
  cada um um `CatalogProjectionBackend` (o protocolo já existe em offerman).
- **Respeitar o Core**: Offerman é sagrado; disponibilidade já mora em `ListingItem`. O que falta é
  gatilho (signal) + orquestração + UI, não campos novos no Core.

## Princípios a honrar (do projeto)
Simples, robusto, elegante. Sem gambiarra. Sem reinventar (o retract já existe). Sem lib externa de
componentes (Alpine/HTMX/Tailwind no Django; Nuxt nas superfícies). Admin/Unfold canônico onde couber.

## Pendências fora do código
- iFood WP-6 homologação (Pablo).
- Inspecionar o app **Gestor de Pedidos** do iFood (abrir pelo link interno do Portal).
