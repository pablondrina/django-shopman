# Storefront UI Thing Canonical Audit

Data: 2026-05-18

## Achado Critico

Havia duas leituras operacionais para a home:

- `home.shop_status`, resolvida por `business_calendar.current_business_state`.
- `home.omotenashi.is_open`, derivada de `OmotenashiContext` por horario direto.

Isso permitia a mesma tela mostrar "Loja aberta" e "Loja em pausa". A correcao
canonica foi manter `home.shop_status` como a unica projection de status
operacional e remover `is_open`, `opens_at` e `closes_at` de
`OmotenashiProjection` na API de home. `OmotenashiContext` agora usa
`business_calendar.current_business_state` para momento/copy temporal, evitando
divergencia interna.

## Classificacao

1. Ja canonico:
   - `home.shop_status` para status operacional.
   - `home.hero_copy`, `home.sections_copy`, `home.actions` e projections de
     catalogo/carrinho.
   - Mutacao de quantidade via `/api/v1/cart/skus/{sku}/`.

2. Deve ser canonizado:
   - Nenhum novo contrato foi necessario nesta rodada. O gap real era uso
     incorreto/duplicado da projection existente.

3. Detalhe efemero de superficie:
   - Organizacao visual do hero em momentos `Agora`, `Pedir` e `Forno`.
   - Lista lateral de sugestoes rapidas no cardapio usando `UiCommand` sem
     segundo campo de busca.

4. Legado/descartavel:
   - Expor `omotenashi.is_open`, `omotenashi.opens_at` e
     `omotenashi.closes_at` na home projection.
   - Qualquer derivacao de status operacional na superficie.

## UI Thing

A superficie Thing usa componentes scaffoldados locais em
`surfaces/storefront-uithing-nuxt/app/components/Ui`, configurados em
`ui-thing.config.ts`. Os componentes de aplicacao (`HomeHeroThing`,
`ProductTile`, `CartDrawer`, `ProductDetailSheet`, `QuantityControl`) sao
composicoes da superficie sobre esses primitives, nao componentes de dominio.

Guardrails ativos:

- `tests/surfaceGuardrails.test.ts` impede controles nativos fora de
  `app/components/Ui`, busca duplicada por `UiCommandInput` no cardapio e uso de
  `home.omotenashi.is_open` como status.
- O cardapio nao pode renderizar grids de produto dentro de `UiTabsContent`
  repetidos. Essa regressao montava centenas de `ProductTile`/`NumberField`
  escondidos e deixava o browser lento.
- `scripts/ux-smoke.mjs` executa smoke real via Chrome headless contra a app
  rodando e falha em status contraditorio, hero colapsado, busca duplicada,
  DOM inicial grande demais, muitos steppers no primeiro render, endpoint de
  carrinho nao canonico ou 409 indevido em item projetado como disponivel.

## Performance 2026-05-18

Achado: o menu renderizava o grid em um `UiTabsContent value="all"` e novamente
em um `UiTabsContent v-for="section in sections"`. Como `activeSections` era
compartilhado, a tela podia montar centenas de cards e steppers escondidos.

Correcao: `UiTabs` ficou apenas como controle de filtro; o grid de
`activeSections` e renderizado uma unica vez. `ProductTile` agora monta
`QuantityControl` somente quando `qty > 0`; no primeiro render exibe um
`UiButton` de adicionar que chama a mesma mutation canonica de carrinho.

Evidencia local em `/menu`, viewport mobile:

- `tabContents`: 0
- `quantityControls`: 0 no primeiro render
- `domNodes`: 2026
- `loadEventEnd`: 916 ms em dev server local

## Evidencia Executada

- `pytest shopman/storefront/tests/test_home_projection_contract.py shopman/storefront/tests/test_omotenashi.py shopman/storefront/tests/test_shop_status.py shopman/storefront/tests/api/test_storefront_surface.py shopman/storefront/tests/api/test_cart_hardening.py shopman/storefront/tests/test_rate_limiting.py::test_api_cart_sku_qty_rate_limited_payload_has_recovery -q`
- `npm run test`
- `npm run test:ux`
- `npm run build`
