# Storefront UI Thing Canonical Audit

Data: 2026-05-16
Branch: `codex/pos-uithing-surface`
Alvo: `surfaces/storefront-nuxt`

## Escopo

Auditoria feita antes da implementacao da Storefront UI Thing:

- Django/Penguin storefront atual como superficie mais madura de descoberta.
- Nuxt UI existente em `surfaces/storefront-nuxt`.
- APIs/projections/actions do storefront: home, menu, produto, cart, checkout,
  auth, account, tracking, payment, reorder, cancel/rate e geocode.
- Pipeline DigitalOcean App Platform em `.do/app.yaml`.
- Documentacao oficial UI Thing via MCP/docs: introduction, setup, CLI,
  components, shortcuts e MCP.

## Resultado Arquitetural

Nao foi necessario criar projection/action/service novo para esta entrega. A
auditoria mostrou que os comportamentos reais exigidos para a nova superficie
ja estao sustentados por contratos canonicos existentes. A implementacao UI
Thing ficou como adaptador visual sobre esses contratos.

## Classificacao Django/Penguin

### 1. Ja Canonico

- Home: `build_home`, `HomeProjection`, status da loja, horarios,
  omotenashi, destaques, public config, WhatsApp e actions.
- Menu: `CatalogProjection` com secoes, categorias, busca auxiliada por
  `search_terms`, favorite category, happy hour, disponibilidade e itens
  destacados.
- Produto: `ProductDetailProjection` com galeria, combo/componentes,
  alergenos, dietary, conservacao, ingredientes, trace notice, nutricional,
  disponibilidade, `qty_in_cart`, `max_qty` e `can_add_to_cart`.
- Carrinho: `CartProjection` e mutations `/api/v1/cart/*`, incluindo totals,
  cupom, descontos, pedido minimo, upsell, indisponibilidade e holds.
- Checkout: `CheckoutProjection` e serializer de `/api/v1/checkout/` com
  `idempotency_key`, fulfillment, endereco salvo/estruturado, complemento,
  instrucoes, data, slot, payment method e fidelidade.
- Auth: `/api/v1/auth/session/`, `request-code`, `verify-code`,
  `device-check`, `trust-device` e `logout`.
- Conta: profile, summary, addresses, orders, active badge, preferences,
  devices, export/delete.
- Tracking: `/api/v1/tracking/{ref}/` com `OrderTrackingProjection`,
  promise/actions/progress/timeline/fulfillments/payment gate flags.
- Pagamento: `/api/v1/payment/{ref}/` e `/status/` com `PaymentProjection` e
  recovery para PIX/cartao/status terminal.
- Reorder/cancel/rating: actions resolvidas e mutations idempotentes em
  `/api/v1/orders/{ref}/*`.
- Geocode: `/api/v1/geocode/reverse/` server-side para endereco estruturado sem
  expor chave privada.

### 2. Deve Ser Canonizado

Nenhum gap P0/P1 bloqueante foi encontrado para criar a nova superficie. Dois
pontos ficaram como observacao para evolucao futura, sem bloquear `/thing/`:

- `next_url` e `payment_gate_url` ainda podem vir em formato de rota historica
  Django (`/pedido/{ref}/pagamento`). A nova superficie trata isso como
  adaptacao de navegacao local, nao regra de negocio. Uma evolucao limpa seria
  backend expor route intents multi-superficie ou action hrefs neutralizados por
  surface context.
- Autocomplete Google Places da superficie Nuxt existente ainda depende de
  loader client-side. O contrato canonico novo para server-side e
  `/api/v1/geocode/reverse/`; CEP/ViaCEP antigo de Django/Penguin nao foi
  copiado.

### 3. Detalhe Efemero De Superficie

- Layout, rails, microcopy visual, hero, cards, drawer/sheet, stepper,
  accordion, tabs e agrupamentos sao escolhas de superficie.
- Scroll-spy, comandos de busca, ordem visual das secoes e densidade de cards
  podem variar por superficie desde que nao mudem disponibilidade, preco,
  status ou promessa operacional.
- Rota local `/pedido/{ref}/pagamento` em Nuxt UI Thing e compatibilidade de
  navegacao para o contrato atual de payment gate; nao e status canonico.

### 4. Legado/Descartavel

- HTMX partials e views Django/Penguin especificas nao devem ganhar novos
  consumidores.
- `CepLookupView`/ViaCEP de superficie e legado diante do contrato server-side
  de geocode e address APIs.
- Views de mock/debug de pagamento e iFood sao ferramenta operacional/dev, nao
  contrato publico de superficie.
- Qualquer regra derivada de template Django para estoque, pagamento, prazo ou
  lifecycle deve ser descartada se nao estiver expressa em projection/action.

## Auditoria Nuxt UI Existente

`surfaces/storefront-nuxt` ja consome os contratos principais e serviu como
fonte de tipos/proxy/composables reaproveitados na nova superficie. O reuso foi
limitado a contrato, proxy e utilitarios de mutation; componentes Nuxt UI,
layout e UX visual nao foram copiados como canon.

## UI Thing

MCP/UI Thing confirmou o workflow canonico:

1. `npx nuxi@latest init`
2. `npm install`
3. `npx ui-thing@latest init`
4. `npx ui-thing@latest add ...`

Os componentes foram scaffoldados para `app/components/Ui` e agora sao codigo
editavel da superficie.

## Matriz UX -> UI Thing

| Momento de UX | Componentes UI Thing usados |
| --- | --- |
| Home/status/proxima acao | Alert, Badge, Card, HoverCard, Progress, Skeleton |
| Menu/busca/filtros | Command, Tabs, Badge, Tooltip, Skeleton |
| Produto/PDP | Sheet, Dialog route, Accordion, NumberField, Badge, Toast/Sonner |
| Carrinho | Sheet, Item, Progress, Alert, Badge, AlertDialog-ready recovery |
| Checkout | Stepper, Tabs, RadioGroup, Datepicker/Calendar, Select, Switch, Checkbox, AlertDialog, Sonner |
| Tracking | Timeline, Progress, Tabs, Alert, Badge, Dialog, Tooltip |
| Pagamento | Alert, Card, Progress, Button, Sonner |
| Conta/historico/reorder | Tabs, List/Item, AlertDialog, Switch, Select |

`Combobox` nao apareceu como alvo scaffoldavel separado no MCP; `Command` foi
usado como equivalente documentado e composto sobre primitives de combobox/list.

## Guardrails Implementados

- Testes front cobrem payload canonico de checkout, idempotencia e adaptacao de
  rotas de backend.
- Teste estatico bloqueia endpoints nao-canonicos diretos e verifica que login
  usa o telefone normalizado retornado por `/api/auth/request-code/`.
- UI nao calcula preco, estoque, status de pedido ou promessa de pagamento; usa
  campos display/progress/status/actions vindos do backend.

## Deploy

`.do/app.yaml` agora declara:

- `/` -> `web`
- `/nuxt` -> `nuxt-storefront`
- `/thing` -> `thing-storefront`

O novo servico usa `source_dir: /surfaces/storefront-nuxt`,
`build_command: npm ci && npm run build`, `run_command:
node .output/server/index.mjs`, `NUXT_APP_BASE_URL=/thing/` e
`NUXT_DJANGO_BASE_URL=${APP_URL}`.
