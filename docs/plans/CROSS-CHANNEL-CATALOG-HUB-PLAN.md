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

### O gap de wiring (por que pausar não chega ao iFood hoje)
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
1. **Duas registries divergentes para projeção**: `SHOPMAN_CATALOG_PROJECTION_ADAPTERS` (usada pelo
   handler/signals, shop) vs `OFFERMAN["PROJECTION_BACKENDS"]` (usada por `project_listing`/
   `project_catalogs`/`get_projection_backend`, offerman). Unificar numa só (canônica) é pré-requisito
   pra rotear tudo pelo `project_listing`.
2. **`sync_catalog_ifood` não é retract-aware** — instancia `IFoodCatalogProjection` e chama
   `project()` cru (não retrata). Depois de unificar (1), roteá-lo por `project_listing`.
3. **Imagem**: projeção não sincroniza foto (iFood exige upload separado/`imagePath`). Fluxo à parte.

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
