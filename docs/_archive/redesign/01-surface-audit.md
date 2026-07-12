# Auditoria das Superfícies Atuais — a hipótese do "frankenstein" testada (Etapa B, parte 1)

> Iniciativa [[project_excellence_refactor_initiative]]. Auditoria com evidência (leitura direta do
> código, 2026-06-05) de `storefront/`, `backstage/`, e da fronteira orquestrador↔superfície.
> Objetivo: testar a hipótese *"a dívida está em COMO as superfícies consomem o contrato, não no
> Core"* e separar **o que salvar** do que reorganizar. Alimenta o doc de confronto (02) e a
> arquitetura (D).

## Veredito: hipótese CONFIRMADA — e com causa-raiz identificada

A dívida **não está no Core nem na espinha do orquestrador** (ambos sólidos). Está na camada de
superfície — **mas a causa não é negligência, é uma decisão de fronteira que saiu pela culatra.**

### ⭐ A causa-raiz (a descoberta que reenquadra tudo)
`shopman/shop/tests/test_import_boundaries.py` **proíbe** `storefront/` e `backstage/` de importarem
qualquer package do Core (offerman/stockman/guestman…) diretamente. Intenção boa (superfícies
magras). **Consequência mecânica:** toda leitura de read-model é **forçada a descer pra
`shop/services/`** → o que **inflou `shop/services/` num BFF gigante (49 módulos, ~7.000+ linhas de
read-model+copy)** misturado com a espinha de orquestração legítima.

Provas de que são read-models de SUPERFÍCIE, não orquestração:
- `shop/services/order_tracking.py` (**1.652 linhas**) = projeção de tela 100% (timeline, ETA,
  progress steps, opening hours). `storefront/projections/order_tracking.py` só re-exporta, com
  docstring honesto: *"The canonical projection is built in shop.services… no separate Storefront
  DTO layer here."*
- `shop/services/storefront_context.py` = merchandising (fresh-from-oven, happy hour, upsell,
  barra de progresso de pedido mínimo).
- A espinha (`lifecycle.py`, `handlers/`, `rules/`) **nunca importa** os `*_context` — só
  superfícies consomem. (grep confirma.)

→ **A regra que mantém as superfícies magras é exatamente a que inchou o orquestrador.** O
orquestrador não foi mal-desenhado; ele foi **forçado a carregar lógica de superfície**. Isso é
exatamente o tipo de decisão de fronteira que o redesign precisa revisar conscientemente.

## O que é OURO e fica intocável
- **A espinha config-driven:** `lifecycle.py`/`production_lifecycle.py` (dispatch), `ChannelConfig`,
  `adapters/`, `rules/engine.py`, directive handlers, `projections/types.py`. (E a orquestração
  genuína em services: `availability.py`, `payment.py`, `sessions.py`, `cancellation.py`,
  `notification.py`, `fiscal.py`.)
- **O padrão Admin/Unfold canônico** (`backstage/admin_console/` + `backstage/projections/`) = o
  **gold standard do projeto**. Cada página: `UnfoldModelAdminViewMixin + TemplateView` + projection
  registrada + service. Zero query inline. Teste dedicado garante que views não dirigem lifecycle.
  **É a prova de que o time SABE fazer a fronteira certa** — o redesign deve replicar esse rigor pro
  storefront/POS.
- **`SurfaceActionProjection`** — contrato headless riquíssimo (ações, payload schema, idempotência,
  confirmação). Pronto. (Ironia: a tela POS o ignora — ver abaixo.)
- **A API REST headless** (`backstage/api/operations.py`) — já é a "superfície limpa" que queremos.
- **Camada de projections** (frozen dataclasses, dual price `_q`+`_display`, zero import de Core
  model, zero aritmética em template). Sólida.
- **Proxy Nuxt** (`surfaces/pos-nuxt/server/utils/djangoProxy.ts`) — transporte impecável
  (CSRF bootstrap, cookie merge, catch-all único).

## Os bolsões de frankenstein (localizados, contáveis — NÃO sistêmico)

### Storefront
- **`storefront/cart.py::CartService.get_cart()` (210 linhas)** — o pior offender. Importa Core
  direto (Session/Product/availability), faz **matemática de disponibilidade própria**, agrega
  descontos, calcula totais — tudo regra de negócio que pertence a `shop.services.cart_context`
  (que já tem o esqueleto e é ignorado).
- **`storefront/services/product_cards.py`** — pricing de promoção **paralelo** chamando **métodos
  PRIVADOS** do Core (`DiscountModifier._matches`/`_calc_discount`). É a fonte da **divergência
  preço-vitrine vs preço-carrinho**. + dois shapes de "card" (`CatalogItemProjection` vs dict) com
  dois templates (`_catalog_item_grid.html` vs `availability_preview.html` — que admite no header:
  *"Consumes annotate_products() dicts (not CatalogItemProjection)"* = frankenstein declarado).
- **CEP lookup / toasts** montando HTML/SVG dentro de view (`tracking.py::CepLookupView`).
- A mesma chamada `availability_for_skus` **triplicada** (cart.py / cart_context.py / product_cards).

### Backstage
- **3 transportes de mutação redundantes:** HTMX-HTML (`views/pos.py`), Admin-custom
  (`admin_console/`), REST (`api/operations.py`). Admin e REST respeitam o contrato; **a tela POS
  HTMX o IGNORA** — monta HTML em **40 f-strings** dentro da view (`pos.py:130-251`), enquanto a
  própria `projections/pos.py:560-1135` publica 20 ações `SurfaceActionProjection` com `href` pra
  `/api/v1/...` que ninguém consome. **O contrato limpo existe e a tela não usa.**
- **Lifecycle duplicado:** `backstage/projections/order_queue.py` redefine `NEXT_STATUS_MAP`/
  `_next_status` (READY→dispatched, gating de pagamento) que já é canônico em
  `shop/services/operator_orders.py::next_status_for`. **Duas fontes da verdade** pra "próxima etapa".
- **Helpers de permissão copiados 5×** (`_can_operate_kds`/`_can_manage_orders`/… em navigation.py +
  4 módulos). Não há `backstage/permissions.py` canônico.
- **KDS em duas casas** (admin_console/kds.py tabular + views/kds_station.py runtime). O KDS-no-Admin
  é vestígio.
- Registro das admin_console via **reflexão lazy** (`admin.site._registry[Order]` + `admin_view` em
  config/urls) — "Unfold-shaped" mais que "Unfold-canonical".

### Fronteira / vertical
- **Vertical food/BR hardcoded na camada de serviços** (deveria ser config): copy de cliente
  (`f"{name} está esgotado…"`, `f"O preço mudou para R$…"` em checkout_context), thresholds
  (repricing `> 0.05`, happy-hour, freshness 15/60min em storefront_context — o código admite a
  dívida: *"Settings-driven for now; a future iteration can move to ChannelConfig"*). Primitivas pra
  isso **já existem** (`OmotenashiCopy`/`ChannelConfig`/`RuleConfig`) e o padrão certo já é usado em
  `order_tracking._tracking_copy()` — só não uniformemente.
- **`shop/services/pos.py` (2.179 linhas, 80+ fn)** mistura commit/orquestração legítima com
  gestão de comanda + montagem de payload de UI + persistência de cliente — surface logic no
  orquestrador.
- **Contrato POS duplicado client+server:** `posIntent.ts::buildPosSaleIntent` reconstrói à mão o
  mesmo payload que `shop/services/pos.py::build_session_ops` desmonta (`intent_version v1`). Sync
  manual, frágil — devia ser schema/tipos compartilhados gerados.

## ⭐ A bifurcação arquitetural central (decisão pra etapa D — precisa do Pablo)
A causa-raiz expõe O fork que define a nova arquitetura:

- **Hoje:** "superfícies NUNCA tocam o Core; tudo roteia pelo orquestrador" → inflou o orquestrador
  com read-models de tela.
- **Proposta (a confrontar/decidir):** introduzir uma **camada de read-model/BFF de superfície
  explícita**, *permitida a ler o Core* (ou uma **fachada read-only do Core**), drenando os
  read-models de tela (`order_tracking`, `*_context`, `customer_orders`…) pra FORA da espinha. O
  orquestrador fica enxuto: mutação + orquestração + config. As superfícies (storefront/POS/admin
  custom/agentic) consomem **um contrato projection+comando uniforme** — exatamente o que o
  `admin_console` já faz certo e o POS-HTMX faz errado.

Isso implica **revisar a política do `test_import_boundaries`** (convenção de arquitetura, não
kernel). É a peça que destrava o "des-frankensteinizar".

## Direção de conserto (sem reescrever o Core; alvos concretos)
1. **Camada de projeção de superfície explícita** (BFF) com leitura do Core permitida → drena
   `order_tracking`/`*_context`/`customer_orders`/`payment_status` da espinha. Replica o rigor do
   `admin_console` pro storefront/POS.
2. **Um transporte/contrato de comando** (a REST + `SurfaceActionProjection` que já existem) consumido
   por TODAS as superfícies. POS-HTMX para de montar HTML; vira casca sobre o contrato. Schema POS
   compartilhado (gerar tipos), matando a dupla manutenção client/server.
3. **Externalizar vertical food/BR** pra `OmotenashiCopy`/`ChannelConfig`/`RuleConfig` (já existem).
4. **Aposentar duplicações:** `cart.py::get_cart` → `cart_context`; `product_cards` promo → caminho
   canônico `contextual_price`; lifecycle de `order_queue` → `operator_orders.next_status_for`;
   `backstage/permissions.py` único; decidir destino do KDS-no-Admin.

**Custo:** moderado e localizado (não é reescrita). O contrato e as projections **não precisam
mudar** — precisam ser USADOS onde hoje são contornados, + a fronteira de import revista.

## Conexão com os princípios (insumo do confronto 02)
- Valida **projection-driven** (a camada de projections é boa; o problema é não usá-la em todo lugar).
- Valida **config-driven** (as primitivas existem; o vertical hardcoded é dívida de não-uso).
- Valida [[feedback_no_standalone_admin]] + Unfold Canonical Gate (o `admin_console` é o gold
  standard; a regra Unfold×dedicada já está quase certa, só com incoerências pontuais: KDS em 2
  casas, registro por reflexão).
- O **contrato uniforme projection+comando** (a tese do redesign) é confirmado empiricamente: onde
  é seguido (admin_console, REST), é limpo; onde é contornado (POS-HTMX, cart.py), é frankenstein.
</content>
