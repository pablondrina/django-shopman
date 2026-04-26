# ROADMAP — Django Shopman

> Atualizado em 2026-04-25.

---

## Vocabulário (2026-04-15)

- **Shopman Suite** (ou "a suite") = o projeto inteiro: os 9 packages + camada orquestradora + instâncias.
- **Shopman** (sem qualificador) = a **camada orquestradora**, que hoje mora em `shopman/shop/` (Django app `shopman.shop`, label `shop`). Coloquialmente "orquestrador" ou "Maestro" também servem, mas o nome canônico informal é **Shopman**, fechando o padrão persona (Shopman rege; Offerman, Stockman, Craftsman, Orderman, Guestman, Doorman, Payman executam).
- **Core / packages** = os 9 packages pip-instaláveis em `packages/*`, cada um standalone.
- **Instância** = uma aplicação Django concreta em `instances/*` (ex.: Nelson Boulangerie), que consome a Suite.

*Nota:* há tensão de namespace — `shopman.*` como namespace Python contém todos os packages, não só o orquestrador. Na fala isso não atrapalha; se um dia fizer sentido formalizar, o Django app `shopman.shop` poderia ser promovido a `shopman` (label `shopman`). Não urgente.

---

## Pendências Ativas (sessão 2026-04-15)

Cinco frentes abertas. Ordem recomendada:

### 1. Commit da leva backend em trânsito (C1-C9)

Há ~58 arquivos modificados + untracked (handlers, services, ADR-007, novos iFood/PIX mock) resultantes de trabalho backend que ainda não fechou. Antes de tocar em qualquer outra coisa, fechar essa leva em commits semânticos agrupados por tema. Plano de 9 commits (C1-C9) aguardando execução — ver registro na sessão de trabalho ou gerar novamente com análise do `git status`.

### 2. ~~Consolidação semântica de nomes~~ — **Cancelado**

❌ Cancelado — nomenclatura atual (`shopman/shop/`, `instances/`) é definitiva. Ver memória de projeto `naming_consolidation_cancelled`.

### 3. ~~Extração de valor do `proto/` antes de descartar~~ — **concluído 2026-04-15**

Ver [`docs/plans/completed/PROTO-EXTRACTION-PLAN.md`](plans/completed/PROTO-EXTRACTION-PLAN.md).

Sete categorias portadas para `v2/`: design tokens `@theme` com pares light/dark, componentes `@layer components` (card, btn-*, badge-*, touch-target), 6 keyframes + `prefers-reduced-motion`, partial `availability_badge.html`, partial `timeline.html`, helper `haptic.js` com `triggerHaptic.{light,double,confirm,error}`. Diretório `proto/` deletado; `proto-scenarios.js` sobreviveu como ferramenta de dev em `tools/demo-scenarios/` com guia em [`docs/guides/demo-personas.md`](guides/demo-personas.md).

### 4. Projections + UI (Penguin) — WP grande

Ver [`docs/plans/PROJECTION-UI-PLAN.md`](plans/PROJECTION-UI-PLAN.md).

**Tese:** templates hoje consomem domain models + helpers diretos. A solução é uma camada de **projections** (dataclasses tipadas e imutáveis em `shopman/shop/projections/`, ou `shopman/hub/projections/` pós-NAMING) que traduzem estado do domínio para o que a UI precisa. A mesma projection alimenta storefront, API REST, POS, KDS — qualquer interface. Precedente já existe em [`packages/offerman/shopman/offerman/protocols/projection.py`](../packages/offerman/shopman/offerman/protocols/projection.py) (`CatalogProjectionBackend` para sync de canais externos), mas esse é um caso específico — o plano generaliza para consumo interno por persona.

Plano detalhado cobre: inventário de projections por tela (13 projections para storefront+operador), arquitetura, fases 1-5, integração com Penguin UI (Tailwind v4 + Alpine), regras (preços duais, disponibilidade como enum não bool, templates nunca importam models).

**Status:**
- **Fase 1 — Fundação:** ✅ concluída 2026-04-15. `CatalogProjection`, `CartProjection`, `ProductDetailProjection` + builders em `shopman/shop/projections/`. Todas com `qty_in_cart` anotado a partir do `CartService`. Templates `menu.html`, `cart.html`, `product_detail.html` em v2 consumindo as projections. Stepper inline iFood/Rappi-style nos cards (`− N +`) via `CartSetQtyBySkuView` (POST absoluto idempotente). 35 testes verdes.
- **Fase 2 — Checkout/Payment/Tracking:** ⏳ próximo
- **Fases 3-5:** pendentes

**Nota sobre storefront bagunçado:** hoje há 3 versões coexistindo — `storefront/` (v1 produção, ~55 templates, todas as rotas usam), `storefront/v2/` (Penguin, só home+partials, ativada com `?v2`), e `web/templates/storefront/proto/` (sandbox com 21 duplicados, não roteado). O destino dessa bagunça é resolvido em 2 passos: **PROTO-EXTRACTION** (item 3) extrai valor do proto e deleta; **PROJECTION-UI-PLAN Fase 1** (este item) migra v1 → v2 tela por tela junto com criação de projections. Não limpar antes, senão refatora-se duas vezes.

### 5. ~~Fix UX rápido: stepper no cardápio~~ — **concluído 2026-04-15**

Ver [`docs/plans/STOREFRONT-ADDTOCART-UX-PLAN.md`](plans/STOREFRONT-ADDTOCART-UX-PLAN.md).

Entregue como parte da Fase 1 do PROJECTION-UI-PLAN (item 4). Stepper inline `− N +` no card v2 dirigido por `CatalogItemProjection.qty_in_cart`, posta absoluto via `CartSetQtyBySkuView` (idempotente: 2 no carrinho + qty=3 no card → carrinho vira 3, não 5). PDP v2 segue o mesmo padrão: inicializa `qty: qty_in_cart || 1, inCart: qty_in_cart` e o botão alterna entre "Adicionar" e "Atualizar para N".

---

### Ordem recomendada de execução

```
1. C1-C9 (commits em trânsito)                                       ✓ feito
   ↓
2. NAMING-CONSOLIDATION                                              — ❌ Cancelado — nomenclatura mantida
   ↓
3. PROTO-EXTRACTION (cria tokens/componentes em v2 já no lugar final) ✓ feito 2026-04-15
   ↓
4. PROJECTION-UI-PLAN Fase 1 (migra v1 → v2 tela por tela, consumindo o que proto deixou)
   ↓
5. (paralelo, a qualquer momento) STOREFRONT-ADDTOCART-UX — pequeno, isolado
```

### 6. Backoffice UI — Penguin UI Refactor (Omotenashi-First)

Ver [`docs/plans/BACKOFFICE-UI-PLAN.md`](plans/BACKOFFICE-UI-PLAN.md).

Unificar telas operador (Pedidos, KDS, POS, Produção, Fechamento) sob Penguin UI com tema Industrial. Dark-first, sidebar compartilhado, navegação entre áreas.

**Status:** WP-1 (Shell + CSS Foundation) pronto para iniciar. Plano completo com 6 Work Packages (WP-1 a WP-6).

---

## Estado Atual

Todos os planos históricos de execução foram concluídos (arquivados em `docs/plans/completed/`):
- **REFACTOR-PLAN** (WP-0 a WP-R5) — Reestruturação de 8 core apps
- **CONSOLIDATION-PLAN** (WP-C1 a WP-C6) — Consolidação pós-refatoração
- **HARDENING-PLAN** (WP-H0 a WP-H5) — Hardening arquitetural
- **BRIDGE-PLAN** (WP-B1 a WP-B7) — Alinhamento Core ↔ App
- **P0-NAMING-PLAN** — Refactor de nomenclatura persona (concluído 2026-04-14)

A Suite está funcional como MVP: storefront completo (menu → cart → checkout → PIX → tracking),
3 presets de canal, pipeline de pedidos flexível, ~2.448 testes.

---

## Já Implementado

| Feature | Status | Localização |
|---------|--------|-------------|
| Catálogo + preços + listings | Estável | `packages/offerman/` |
| Estoque: holds, moves, alertas | Estável | `packages/stockman/` |
| Produção: receitas, work orders, BOM | Estável | `packages/craftsman/` |
| Pedidos: session → order, directives | Estável | `packages/orderman/` |
| CRM: customers, contatos, grupos | Estável | `packages/guestman/` |
| Auth OTP: WhatsApp-first, device trust | Estável | `packages/doorman/` |
| Pagamentos: PIX (EFI) | Estável | `packages/payman/` + adapters |
| Loyalty: earn, redeem, tiers, stamps | Implementado | `guestman/contrib/loyalty/`, checkout |
| Disponibilidade na UI | Parcial | catalog views + `_helpers.py` |
| Storefront HTMX | Beta | `shopman/storefront/` |
| KDS (kitchen display) | Implementado | `shopman/backstage/views/kds.py` |
| POS (point of sale) | Implementado | `shopman/backstage/views/pos.py` |
| Admin (Unfold) + dashboard | Implementado | `shopman/shop/admin/` |
| Rules engine (promotions, coupons) | Implementado | `shopman/shop/rules/` |
| Fechamento do dia | Implementado | `shopman/shop/models/closing.py` |

---

## Parcialmente Implementado

### Disponibilidade + Alternativas no Storefront

Backend completo. UI parcial — falta PDP inline e seção de alternativas colapsável.

**Já existe:**
- `StockingBackend.check_availability()` + `get_alternatives()`
- `find_alternatives()` em `offerman/contrib/suggestions/`
- Availability badges no catalog view (home page + cardápio)
- Políticas: `stock_only`, `planned_ok`, `demand_ok`

**Falta:**
- PDP: feedback inline antes de adicionar ao carrinho
- PDP: seção de alternativas quando indisponível
- Carrinho: warnings inline por item com ações (Ajustar qty, Ver Alternativas, Remover)

---

### Cartão de Crédito no Storefront

Backend completo. Seletor de método de pagamento no checkout não implementado.

**Já existe:**
- `StripeBackend` (`adapters/payment_stripe.py`) funcional
- `StripeWebhookView` implementado
- `ChannelConfig.Payment` aceita `method="card"`

**Falta:**
- Seletor de método de pagamento no checkout (PIX vs Cartão)
- Template com Stripe Elements

---

### API REST Completa

Endpoints de catálogo e tracking prontos. Account e histórico incompletos.

---

## Gaps Técnicos Conhecidos

| Item | Descrição | Plano |
|------|-----------|-------|
| C2 | Thread safety adapter EFI + cobertura base | CONSOLIDATION-PLAN |
| C4 | Security headers (CSP, HSTS) | CONSOLIDATION-PLAN |
| C5 | Queries N+1 no storefront (catalog, cart, tracking) | CONSOLIDATION-PLAN |
| C6 | Testes de concorrência (stock, payment, work orders) | CONSOLIDATION-PLAN |
| C7 | Payman: cobertura de testes insuficiente | CONSOLIDATION-PLAN |
| ~~B3~~ | ~~Doorman depende de Guestman (viola standalone)~~ | **CONCLUÍDO** — `shopman-doorman` não depende de `shopman-guestman` por default: o resolver padrão é `NoopCustomerResolver` e o suporte a Guestman é opt-in via `DOORMAN["CUSTOMER_RESOLVER_CLASS"]` e extra opcional (`shopman-doorman[guestman]`). | ✅ |
| R3-R8 | Storefront: empty states, erros, responsividade mobile | READINESS-PLAN |
| HTMX swap errors antigos | `htmx:swapError` "Cannot read properties of null (reading 'querySelector')" no console — vinha de respostas de `/meus-pedidos/?badge_only=1` ou de drawer reload com target ausente. Identificado durante a Fase 1 do PROJECTION-UI-PLAN; não tem relação com o stepper novo. Investigar quando alguém estiver na área de header/badge polling. | _ad-hoc_ |
| `_cart_qty_by_sku` carrega cart inteiro a cada render | `shopman/shop/projections/catalog.py` — o helper chama `CartService.get_cart(request)` em cada `build_catalog`, o que itera todas as linhas só pra montar um dict sku→qty. Fine pra catálogos pequenos (Nelson tem ~50 SKUs, cart tem 1-10 linhas). Se virar gargalo, expor `CartService.qty_by_sku(request)` que pula o resto do projection do carrinho. Documentado em 2026-04-15 durante Fase 1. | Baixa |

---

## Próximos Passos (não iniciado)

### Notificações Transacionais Reais

Email/WhatsApp funcionais existem via adapters, mas instâncias de produção precisam de:
- Email transacional configurado (confirmação, tracking, PIX expirado)
- ManyChat template ativo para notificações de pedido

### Fiscal / Contábil

Extension points prontos (FiscalBackend, AccountingBackend em `orderman/protocols.py`).
Implementações de referência: FocusNFCeBackend (NFC-e), ContaAzulBackend.
Ativação é configuração de instância — o framework suporta sem mudanças de código.

### Deploy de Produção

Configurações de instância (Nelson Boulangerie) em `instances/nelson/`.
Pendente: PostgreSQL, static files (Whitenoise/S3), worker Celery (se async), reverse proxy.

---

## Refactor Constitucional — Pendências Registradas

Itens identificados durante a execução da Matriz Executiva de Delta Constitucional
que estão fora do escopo atual mas não devem ser esquecidos.

| Item | Onde | Descrição | Prioridade |
|------|------|-----------|------------|
| KDS como contrib formal | `shopman/shop/models/kds.py`, `services/kds.py`, `web/views/kds.py` | KDS models e views estão no framework como built-in. Lifecycle agora é opt-in (lazy import), mas modelos e views ainda são parte do framework. Considerar extrair para `shopman/shop/contrib/kds/` como app contrib registrável. | Média |
| ~~_is_happy_hour_active no storefront~~ | `shopman/shop/web/views/_helpers.py:790` | **CONCLUÍDO** — Badge agora condicional: só aparece se um modifier com `code="shop.happy_hour"` estiver registrado no registry. Teste adicionado. | ✅ |
| ~~Stockman testes importam offerman~~ | `packages/stockman/shopman/stockman/tests/` | **CONCLUÍDO** — 4 arquivos migrados para SimpleNamespace + NoopSkuValidator. Zero imports de offerman. | ✅ |
| ~~10 settings ausentes~~ | `config/settings.py` | **CONCLUÍDO** — Todos os 10 settings declarados com defaults neutros: GUESTMAN, ORDERMAN, GUESTMAN_INSIGHTS, GUESTMAN_LOYALTY, SHOPMAN_OPERATOR_EMAIL, SHOPMAN_PIX_EXPIRY_SECONDS, SHOPMAN_POS_CHANNEL_REF, SHOPMAN_FISCAL_BACKENDS, SHOPMAN_SMS_ADAPTER, STOCKMAN_ALERT_COOLDOWN_MINUTES. Dicts vazios delegam a defaults internos dos conf.py. | ✅ |
| Doorman multi-handle formal | `packages/doorman/` | Multi-handle existe no orderman (handle_type/handle_ref) mas não é protocolo formal no doorman. | Média |
| Doorman provider linking | `packages/doorman/` | OAuth/SSO provider linking não existe. Extension point a criar. | Baixa |
| ~~Listing sem contrato de canal~~ | `packages/offerman/` | **CONCLUÍDO** — Docstring do Listing formaliza contrato de canal (ref match por convenção, estado comercial em 2 níveis). | ✅ |
| ~~Sync/projeção de catálogo externo~~ | `packages/offerman/protocols/projection.py` | **CONCLUÍDO** — CatalogProjectionBackend protocol criado (project/retract). Implementações concretas ficam no framework ou instância. | ✅ |
| D1Rule e HappyHourRule no framework | `shopman/shop/rules/pricing.py` | Rule wrappers para admin (D1Rule, HappyHourRule) ainda estão no framework. Os modifiers correspondentes foram movidos para instância. Considerar mecanismo de rule discovery para que instâncias registrem suas próprias rules. | Média |
| CatalogProjectionBackend implementation | `shopman/shop/adapters/` | Protocolo criado em offerman. Falta implementação concreta para pelo menos um canal externo (iFood, Rappi, etc). | Alta estratégica |
| Craftsman UI de chão | `shopman/shop/web/views/production.py` | A Matriz pede "desenhar UI/fluxos de chão como parte do domínio". A view atual de produção existe mas não cobre apontamento operacional completo (start, finish com quantidades, waste report). | Média |
| ~~Utils: JS estático faltante~~ | `packages/utils/shopman/utils/static/shopman_utils/js/autocomplete_autofill.js` | **CONCLUÍDO** — Arquivo JS criado. Escuta `select2:select` em widgets com `data-autofill`, copia valores do resultado Select2 para campos target no mesmo inline. | ✅ |

---

## Débitos Conhecidos

Itens que aparecem como `pytest.mark.skip` na suíte e precisam voltar à tela do radar
quando a área correspondente for retomada.

| Item | Onde | Descrição | Prioridade |
|------|------|-----------|------------|
| Manychat webhook | `shopman/shop/tests/web/test_webhook.py` (10 skips) | Testes marcados como skip após a primeira rodada de reestruturação de canais. O endpoint atual não cobre o fluxo completo Manychat → session → confirmação. Retomar junto com a reimplementação do app de canal externo. | Alta |
| Perishable shelflife wiring | `shopman/shop/tests/integration/test_production_stock.py::TestPerishableProducts` (4 skips) | `stockman.services.queries._resolve_stock_profile` lê `.shelflife` do produto, mas `offerman.Product` expõe `.shelf_life_days`. Além disso, o framework usa `NoopSkuValidator` por default, que não retorna `shelflife_days`. Correção exige registrar `OffermanSkuValidator` em settings **ou** alias de atributo em Offerman. Padaria real precisa disso (croissant same-day, bolo 3 dias). | Média |
| Concorrência Postgres-only | vários `tests/.../test_*_concurrency.py` (9 skips) | `SELECT ... FOR UPDATE SKIP LOCKED` não é suportado no SQLite. Os testes rodam em CI com Postgres — reativar quando a pipeline de deploy for plugada. | Baixa (cobertura existe, só requer ambiente) |
| Playwright E2E | `shopman/shop/tests/e2e/` (1 skip) | Suite E2E opcional, roda quando `playwright` está instalado. | Baixa |

---

## Nice-to-Have (futuro distante)

| Item | Descrição |
|------|-----------|
| Variantes de produto | Tamanho, sabor, etc. |
| Assinaturas/recorrência | Pedido semanal automático |
| Gift cards | Crédito pré-pago |
| Reviews/ratings | Avaliação de produtos |
| Busca facetada | Filtros por preço, tags, atributos |
| Endereços salvos | Quick-select no checkout |
| Reordenar pedido | 1-click para repetir |
| Devoluções (UI) | Handler existe, UI não |
| Push notifications | PWA stubs prontos, falta backend |
| Passkeys / WebAuthn | Auth device-bound (quando perfil de risco justificar) |
| Promotions → core app | Promotion/Coupon hoje em `shop/models.py` (funciona bem no app layer) |
| Favoritos como coleção dinâmica | `FavoritesResolver` + M2M `Customer.favorites_skus`. Pill "Favoritos" visível só se `request.customer` + tem favoritos. (Anotado durante WP-MENU-V2 em 2026-04-17 por Pablo). |
| Busca server-side do cardápio (WP-SEO-5) | Substituir filter client-side por endpoint `/api/menu/search?q=` usando `_score_candidates` (keywords + coleção + fuzzy via `difflib.SequenceMatcher`). HTMX com debounce 200ms. Entregue como client-side provisional em 2026-04-17. |
| Admin UX pra coleções dinâmicas | `Shop.defaults.menu.dynamic_collections` hoje é JSON manual no admin. Criar form dedicado com checkbox por resolver registrado (auto-discovery via `dynamic_collections.all_refs()`) + reordenação drag-and-drop. |
| Cards/itens do menu — revisão visual | Pablo sinalizou que "os itens do menu merecem atenção" ao aprovar o layout sticky pills + busca. Revisar grid + card (proporção, typography, badge de availability, unit_weight_label próximo ao preço) como polish pass. |
