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
   - Checkout autenticado por telefone na storefront web, agora expresso pela
     projection `checkout.requires_authentication` e pela action
     `checkout.auth_action`.
   - Auth OTP via `/api/v1/auth/request-code/`, incluindo o metodo real de
     entrega retornado pelo servico Doorman quando ha fallback.

2. Deve ser canonizado:
   - Capability/health operacional de entrega OTP por ambiente. Evidencia:
     staging retornou 400 em `/thing/api/auth/request-code/` para telefone de
     teste porque ManyChat/SMS/email nao conseguiram entregar codigo para esse
     alvo. A superficie nao deve inventar login alternativo; ela mostra erro do
     backend e acao de WhatsApp da loja.

3. Detalhe efemero de superficie:
   - Organizacao visual do hero em momentos `Agora`, `Pedir` e `Forno`.
   - Lista lateral de sugestoes rapidas no cardapio usando `UiCommand` sem
     segundo campo de busca.

4. Legado/descartavel:
   - Expor `omotenashi.is_open`, `omotenashi.opens_at` e
     `omotenashi.closes_at` na home projection.
   - Qualquer derivacao de status operacional na superficie.
   - Auth gate local no checkout sem contrato de projection.
   - Campo numerico em `0` usado como CTA primario de compra em Home/PDP.

## UI Thing

A superficie Thing usa componentes scaffoldados locais em
`surfaces/storefront-nuxt/app/components/Ui`, configurados em
`ui-thing.config.ts`. Os componentes de aplicacao (`HomeHeroThing`,
`ProductTile`, `CartDrawer`, `ProductDetailSheet`, `CartQuantityAction`,
`QuantityControl`) sao composicoes da superficie sobre esses primitives, nao
componentes de dominio.

Revisao 2026-05-18: o MCP oficial do UI Thing foi usado para listar os
componentes disponiveis e cruzar necessidade de UX com componente scaffoldado.
A matriz aplicada agora e:

- OTP/login: `Pin Input`, `Field`, `Button Group`, `Alert`, `Badge` discreto
  dentro do alert de debug.
- Carrinho vazio e busca sem resultado: `Empty`.
- Drawer de carrinho: `Sheet` + `Scroll Area`.
- Informacao nutricional de PDP: `Accordion` + `Description List`.
- Busca e sugestao de cardapio: `Command`, mantendo um unico campo de busca.
- Filtros de secoes: `Tabs`.
- Compra: `Button`, `Number Field`, `Tooltip`, `Hover Card`, `Toast/Sonner`,
  `Progress`, `Radio Group`, `Calendar/Datepicker` conforme telas existentes.

Correcao visual: a superficie agora usa `theme: "stone"` no `ui-thing.config.ts`,
fonte `ui-sans-serif/system-ui`, primary taupe
`oklch(0.535 0.028 64.5)` e raio base `0.25rem`. A projection da loja nao
sobrescreve mais `--primary`, `--background` ou outros tokens do UI Thing; ela
expoe apenas `--shop-brand-color` e `--shop-brand-background` como pistas de
marca. Isso removeu a segunda fonte de verdade visual entre projection e
superficie.

Badges: `success` nao e mais usado para disponibilidade, contadores ou labels
genericas. Disponivel usa `secondary`, planejado usa `outline`, indisponivel
usa `destructive`, promocao usa primary/taupe quando precisa destaque. Verde
fica reservado para alertas/estados de sucesso evidentes.

Guardrails ativos:

- `tests/surfaceGuardrails.test.ts` impede controles nativos fora de
  `app/components/Ui`, busca duplicada por `UiCommandInput` no cardapio e uso de
  `home.omotenashi.is_open` como status.
- `tests/surfaceGuardrails.test.ts` tambem exige `PinInput`, `Field`,
  `ButtonGroup`, `Empty`, `ScrollArea` e `DescriptionList` nos pontos de UX
  acima, e falha se `UiBadge variant="success"` reaparecer nas telas de
  superficie.
- O cardapio nao pode renderizar grids de produto dentro de `UiTabsContent`
  repetidos. Essa regressao montava centenas de `ProductTile`/`NumberField`
  escondidos e deixava o browser lento.
- `scripts/ux-smoke.mjs` executa smoke real via Chrome headless contra a app
  rodando e falha em status contraditorio, hero colapsado, busca duplicada,
  DOM inicial grande demais, muitos steppers no primeiro render, endpoint de
  carrinho nao canonico, 409 indevido em item projetado como disponivel, PDP
  sem `h1`, PDP sem botao de adicionar e checkout anonimo fora da action de
  auth projetada.
- `tests/surfaceGuardrails.test.ts` falha se o checkout Thing voltar a impor
  decisao de auth fora de `checkout.requires_authentication` e
  `checkout.auth_action`.

## Checkout 2026-05-18

Achado: Django/Penguin exige cliente autenticado com telefone antes do
checkout (`CheckoutView.get` redireciona para `/login/?next=/checkout/` quando
`request.customer` ou `customer.phone` nao existe), mas a projection API nao
declarava essa regra. Isso criou duas leituras: superficies maduras exigiam
login; a action API ainda parecia habilitavel para carrinho anonimo.

Correcao: `CheckoutProjection` agora expoe `requires_authentication` e
`auth_action`. Quando o visitante esta anonimo, a action `checkout` vem
desabilitada com o motivo projetado "Entre por telefone para continuar." e a
superficie Thing apenas segue essa action para `/login?next=/checkout`.

Evidencia local via proxy Nuxt em `/thing/`:

- carrinho: 1 item
- `checkout.is_authenticated`: `false`
- `checkout.requires_authentication`: `true`
- `checkout.auth_action.href`: `/login?next=/checkout`
- `checkout.actions[checkout].enabled`: `false`
- required payload: `name`, `phone`, `fulfillment_type`, `payment_method`

## Auth Delivery 2026-05-18

Achado: o staging publico retornou:

- endpoint: `POST https://shopman-staging-cdjpy.ondigitalocean.app/thing/api/auth/request-code/`
- status: `400`
- detalhe: `Nao foi possivel enviar o codigo. Verifique o numero e tente novamente.`

Isso prova que o fluxo remoto de login depende da configuracao real de entrega
OTP/ManyChat para o telefone alvo. A superficie nao pode fabricar login local
ou bypass; ela agora:

- consome `home.auth_copy` para copy de login;
- usa `home.public_config.whatsapp_url` como acao de recuperacao;
- mostra `dev_console_hint` quando o backend local declara sender de
  desenvolvimento;
- exibe o metodo real de entrega retornado por Doorman, nao apenas o metodo
  solicitado.

Gap canonico remanescente: expor uma capability operacional de auth delivery
para ambientes/staging, em vez de descobrir falha apenas na tentativa de envio.

## PDP/Home Add CTA 2026-05-18

Achado: Home e PDP exibiam `NumberField` em `0` como primeira acao de compra.
Na PDP isso deixava o produto sem CTA primario legivel; em mobile o usuario via
apenas `- 0 +`.

Correcao: `CartQuantityAction` centraliza a regra de superficie: quando
`qty == 0`, mostra `UiButton` "Adicionar" chamando a mutation canonica de
carrinho; quando `qty > 0`, mostra `QuantityControl` com `UiNumberField`
scaffoldado pelo UI Thing.

Evidencia local:

- Home initial `quantityControls`: 0
- PDP `/product/BAGUETE`: `h1 = Baguete Francesa`
- PDP initial `quantityControls`: 0
- PDP botoes incluem `Adicionar`

## Prefixo Local 2026-05-18

Achado: o staging publico e canonico em `/thing/`, mas o dev server da nova
superficie abria em `/`. Abrir `http://127.0.0.1:3003/thing/` retornava 404 e
criava uma segunda verdade operacional para a propria superficie.

Correcao: `npm run dev` agora sobe Nuxt com `NUXT_APP_BASE_URL=/thing/`, e o
smoke usa `http://127.0.0.1:3003/thing` por padrao.

## Performance 2026-05-18

Achado: o menu renderizava o grid em um `UiTabsContent value="all"` e novamente
em um `UiTabsContent v-for="section in sections"`. Como `activeSections` era
compartilhado, a tela podia montar centenas de cards e steppers escondidos.

Correcao: `UiTabs` ficou apenas como controle de filtro; o grid de
`activeSections` e renderizado uma unica vez. O wrapper `CartQuantityAction`
impede `NumberField` em zero e chama a mesma mutation canonica de carrinho.

Evidencia local em `/menu`, viewport mobile:

- `tabContents`: 0
- `quantityControls`: 0 no primeiro render
- `domNodes`: 2026
- `loadEventEnd`: 916 ms em dev server local

## Evidencia Executada

- `pytest shopman/storefront/tests/api/test_storefront_surface.py shopman/storefront/tests/web/test_projections_checkout.py shopman/storefront/tests/api/test_auth_session.py -q`
- `pytest packages/doorman/shopman/doorman/tests/test_delivery_chain.py -q`
- `npm run test`
- `npm run test:ux`
- `npm run build`
