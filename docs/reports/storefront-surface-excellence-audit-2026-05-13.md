# Storefront Nuxt v4 - Surface Excellence Audit

Data: 2026-05-13
Escopo: home, menu, catalogo, PDP, carrinho, checkout, auth, pagamento, tracking, reorder, mobile-first, contrato Django/Shopman, omotenashi, confiabilidade transacional e ciclo de vida do cliente.
Framework aplicado: `docs/reference/surface-excellence-review-framework.md`.

## Decisao executiva

Status: nao aprovada para primeira linha.

Nenhum P0 foi confirmado nesta auditoria, mas ha P1s abertos que bloqueiam evolucao para implementacao de refinamentos. A superficie Nuxt v4 ainda esta em estado transicional: boas projecoes backend existem, mas parte do contrato critico fica fora do Nuxt, alguns endpoints runtime nao estao registrados, checkout/pagamento perdem campos canonicos, e a experiencia mobile mostrou quebra visual real no Browser.

Pontuacao:

| Eixo | Nota | Leitura |
| --- | ---: | --- |
| A. Funcionalidade / contrato | 22/40 | Backend tem fontes fortes, mas Nuxt falha em pagamento, SSE/logout, payload de fulfillment e retry transacional. |
| B. Omotenashi | 21/35 | Boa linguagem e memoria inicial; lacunas em confianca, recovery, fidelidade, tracking e ciclo de vida pos-pedido. |
| C. Design / interacao | 13/25 | Base visual boa, mas mobile drawer quebrou no Browser, hidratacao diverge, rotas quebradas e acessibilidade incompleta. |
| Total | 56/100 | Bloqueada. Eixos A e C ficam abaixo de 60%. |

Regra do framework aplicada: qualquer eixo abaixo de 60% bloqueia primeira linha; P1s abertos tambem impedem classificacao acima de 84.

## Como rodar a superficie

Backend Django/Shopman:

```bash
make up
make migrate
make seed
make run
```

O `Makefile` define `run` como `manage.py runserver 0.0.0.0:8000` com refresh, worker e tunnel auxiliares (`Makefile:257-266`). Nesta auditoria ja havia backend em `127.0.0.1:8000`; `GET /api/v1/storefront/home/` retornou payload valido.

Frontend Nuxt v4:

```bash
cd surfaces/storefront-nuxt
npm run dev
```

O script real e `nuxt dev --host 127.0.0.1 --port 3000` (`surfaces/storefront-nuxt/package.json:9-12`). A config aponta `djangoBaseUrl` para `http://127.0.0.1:8000` por padrao (`surfaces/storefront-nuxt/nuxt.config.ts:6-13`).

Verificacao executada:

- `npm run build` em `surfaces/storefront-nuxt`: passou.
- Warnings de build: sourcemaps Tailwind/Vite/VueUse. O bundle gerado registrou apenas rotas Nitro `api/auth` e `api/v1`; os proxies top-level `server/auth`, `server/pedido`, `server/storefront` e `server/checkout` nao aparecem nos chunks de rotas.

## Rotas reais Nuxt v4

Arquivos em `surfaces/storefront-nuxt/app/pages`:

| Rota | Arquivo | Observacao |
| --- | --- | --- |
| `/` | `index.vue` | Home com projecao `/api/v1/storefront/home/`. |
| `/menu` | `menu.vue` | Catalogo completo; filtro local. |
| `/produto/:sku` | `produto/[sku].vue` | PDP; breadcrumb pode apontar para rota inexistente de colecao. |
| `/cart` | `cart.vue` | Carrinho. |
| `/checkout` | `checkout.vue` | Checkout Nuxt, mas pagamento pode sair para Django legado. |
| `/login` | `login.vue` | OTP via `/api/auth/request-code/` e `/api/auth/verify-code/`. |
| `/conta` | `conta.vue` | Perfil, pedidos, enderecos, fidelidade placeholder. |
| `/sair` | `sair.vue` | Logout best-effort, mas chama proxy nao registrado. |
| `/tracking/:ref` | `tracking/[ref].vue` | Tracking Nuxt via API, SSE nao registrado. |

Rotas ausentes no Nuxt v4:

- `/menu/:collection`: o PDP usa `breadcrumb_category.url` e mostrou `/menu/paes-artesanais/`, mas a pagina Nuxt nao existe (`produto/[sku].vue:68-75`). Browser/dev log confirmou `No match found for location with path "/menu/paes-artesanais/"`.
- `/pedido/:ref/pagamento`: checkout Django retorna essa rota para `pix` e `card` (`shopman/storefront/api/views.py:274-278`), mas nao ha pagina Nuxt.
- `/pedido/:ref/cancelar`: existe no Django legado (`shopman/storefront/urls.py:81-84`), nao no Nuxt.
- `/conta/pedidos` e `/conta/enderecos`: aparecem no dropdown autenticado (`AppHeader.vue:31-33`), mas nao existem como paginas Nuxt.

## Evidencia Browser

Browser local usado obrigatoriamente em `http://127.0.0.1:3000`.

Percurso validado:

- `/`: home renderizou com hero, destaques, CTA WhatsApp e copy de omotenashi.
- `/menu`: catalogo real carregou categorias e itens seedados.
- `/produto/BAGUETE`: PDP carregou produto, badge, preco, ingredientes e breadcrumb.
- `/cart`: carrinho vazio carregou.
- `/checkout`: com carrinho vazio renderizou estado vazio, sem commit.
- `/login?next=/checkout`: fluxo inicial de telefone visivel.
- `/conta`: client guard redirecionou para `/login?next=/conta` apos loading.
- `/tracking/SHOPMAN-UNKNOWN`: estado de pedido nao encontrado visivel.
- Viewport mobile `390x844`: menu do header abriu com conteudo duplicado/repetido e area principal em branco na captura. O DOM tambem passou a expor botoes genericos sem nomes claros.

Logs Browser/dev relevantes:

- Hydration mismatch repetido: SSR renderiza `Shopman`, cliente espera `Test Shop` no header (`AppHeader.vue:56` usa `shop?.brand_name` apos bootstrap cliente).
- `Hydration completed but contains mismatches`.
- `No match found for location with path "/menu/paes-artesanais/"`.
- `No match found for location with path "/storefront/stock/events/storefront/"`.
- `No match found for location with path "/pedido/SHOPMAN-UNKNOWN/events"`.
- `Icon failed to load icon lucide:bread`.

Endpoints runtime confirmados por curl contra Nuxt dev:

- `GET /storefront/stock/events/storefront/` em `127.0.0.1:3000`: 404.
- `GET /pedido/SHOPMAN-UNKNOWN/events`: 404.
- `POST /auth/logout/`: rota top-level tambem nao registrada; `GET /auth/session/` retornou 404.
- `PUT /api/v1/cart/skus/BAGUETE/`: 200, via proxy `/api/v1`, confirmando que o proxy principal funciona.

## Fontes de verdade e contrato

### Home / menu / catalogo / PDP

Fonte de verdade: projecoes Django em `/api/v1/storefront/home/`, `/api/v1/storefront/menu/`, `/api/v1/storefront/products/<sku>/` (`shopman/storefront/api/urls.py`).

Pontos fortes:

- Nuxt consome projecoes server-side via proxy `/api/v1`.
- PDP usa JSON-LD Product/Breadcrumb (`produto/[sku].vue:92-149`).
- Carrinho vem junto nas projecoes, evitando cache local puro.

Lacunas:

- Breadcrumb de categoria usa URL vinda do backend legado sem rota Nuxt equivalente.
- Stock SSE do PDP aponta para `/storefront/stock/events/storefront/` (`produto/[sku].vue:32-41`), mas o proxy esta em `server/storefront/...`, nao registrado em Nitro.
- Tipos Nuxt de endereco e tracking descartam campos canonicos ricos do backend (`types/shopman.ts:273-340`).

### Carrinho

Fonte de verdade: Orderman session via `CartService`, API `/api/v1/cart/skus/<sku>/`, `/api/v1/cart/coupon/`, projecao `build_cart`.

Pontos fortes:

- API de qty por SKU aceita `qty=0..99` e retorna carrinho autoritativo.
- Erros 409 de estoque trazem payload rico.
- Remocao e troca de quantidade reconciliam holds no caminho normal.

Lacunas:

- `useCartState` recalcula subtotal/grand total otimisticamente no cliente e ignora descontos, entrega e minimo durante o estado pendente (`useCartState.ts:74-87`, `132-145`).
- `clearCart()` no cliente apaga estado local sem consultar fonte canonica (`useCartState.ts:100-102`), usado apos checkout e logout.

### Checkout

Fonte de verdade: Orderman commit via `checkout_service.process` e `CommitService`; API Nuxt chama `/api/v1/checkout/`.

Pontos fortes:

- Orderman tem commit com idempotencia e retorna pedido existente quando a sessao ja foi commitada.
- API ratelimitada em 3/min (`shopman/storefront/api/views.py:197-224`).

Lacunas criticas:

- A API gera uma idempotency key nova a cada POST (`shopman/storefront/api/views.py:264-269`). O cliente nao manda chave estavel de retry.
- `validateAll()` nao exige `delivery_date`, apesar de `commitWhen()` exigir (`checkout.vue:162-172`, `195-205`). A sticky bar mobile chama `submit()` diretamente (`checkout.vue:596-610`).
- Payload final nao envia `saved_address_id`, `place_id`, coordenadas, rua, numero, bairro, CEP ou endereco estruturado (`checkout.vue:219-234`), embora o backend e a projection suportem dados ricos (`account.py:37-70`, `checkout.py:172-189`).
- `use_loyalty` e enviado (`checkout.vue:233`) e a UI mostra "Aplicando ..." (`checkout.vue:476-488`, `528-530`), mas `CheckoutSerializer` nao define fidelidade (`serializers.py:36-49`) e a view nao mapeia esse campo para `checkout_data`.
- Excecoes de dominio do commit nao sao normalizadas no `CheckoutView.post`; nao ha uso do mapper de erro, entao alguns bloqueios podem escapar como 500 ou mensagem generica.

### Pagamento

Fonte de verdade backend: Payman/service `payment`; rotas Django legado em `pedido/<ref>/pagamento/` e status/mock-confirm (`shopman/storefront/urls.py:77-80`).

Lacuna principal: pagamento nao esta implementado no Nuxt v4. Para `pix`/`card`, a API retorna `next_url` legado (`shopman/storefront/api/views.py:274-278`) e o Nuxt navega externamente se comeca com `/pedido/` (`checkout.vue:237-239`). Isso quebra continuidade mobile, instrumentacao Nuxt, recovery e consistencia visual.

### Delivery / pickup

Fonte de verdade: `CheckoutProjection`, saved addresses, pickup slots, Shop config.

Pontos fortes:

- Projection expõe `pickup_slots`, `earliest_slot_ref`, `closed_dates_json`, `max_preorder_days`, payment methods e saved addresses.

Lacunas:

- `has_pickup` e `has_delivery` sao sempre `True` na projection (`checkout.py:134-154`), sem refletir fechamento, zona ou politica.
- Endereco salvo e copiado para string; a identidade do endereco e sua verificacao geocodificada nao chegam ao checkout.
- `AddressAutocomplete` le `formatted_address`, `address_components`, `geometry`, mas persiste somente string (`AddressAutocomplete.vue:21-34`; `AddressFormModal.vue:59-67`).
- Entrega/taxa/zona parecem ser validadas tarde, no commit, nao como preflight de checkout.

### Auth / cliente

Fonte de verdade: Doorman/Guestman via `/api/auth/*` e `/api/v1/account/*`.

Pontos fortes:

- APIs de conta checam customer autenticado e ownership no backend (`account.py:96-117`, `183-196`, `244-260`).
- Conta redireciona anonimo para login depois do mount (`conta.vue:124-130`).

Lacunas:

- `finalizeName()` ignora falha do PATCH e mesmo assim grava identidade no cliente (`login.vue:116-124`).
- Logout chama `/auth/logout/` (`sair.vue:12-21`), mas o proxy top-level `server/auth/[...path].ts` nao foi registrado em Nitro; falha e limpa estado local mesmo assim (`sair.vue:22-28`).
- Dropdown autenticado aponta para subrotas inexistentes (`AppHeader.vue:31-33`).

### Tracking

Fonte de verdade backend: `build_tracking` em `shopman.shop.services.order_tracking`, com promise, progress, `can_cancel`, pagamento, deadlines, stale time e WhatsApp (`order_tracking.py:107-143`, `198-245`).

Lacunas:

- API `/api/v1/tracking/<ref>/` reduz a projection e perde `promise`, `can_cancel`, deadlines, ETA, payment flags e `stale_after_seconds` (`shopman/storefront/api/tracking.py:47-86`).
- Nuxt considera terminal `fulfilled`, `delivered`, `cancelled` (`tracking/[ref].vue:14-24`), mas o backend canonico usa `completed`, `cancelled`, `returned` (`order_tracking.py:37`).
- Nuxt usa `in_production`, mas Orderman usa `preparing` (`tracking/[ref].vue:14-24`, `packages/orderman/.../order.py`).
- SSE `/pedido/<ref>/events` esta em `server/pedido/...`, nao registrado em Nitro; polling continua, mas "Atualizando ao vivo" fica enganoso.
- Nao ha cancelamento Nuxt, embora backend legado tenha `pedido/<ref>/cancelar/`.

### SEO / performance / a11y

Pontos positivos:

- `lang=pt-BR`, viewport e theme-color configurados (`nuxt.config.ts:12-21`).
- PDP define SEO meta e JSON-LD.
- Build production passou.

Lacunas:

- Home/menu nao tem JSON-LD local business/breadcrumb e a home depende de titulo generico/hydration posterior.
- Hydration mismatch no header afeta confiabilidade e performance percebida.
- Mobile drawer quebrou visualmente no Browser.
- Icone `lucide:bread` falha; `@iconify-json/lucide` nao tem esse icone.
- Botoes do drawer mobile ficaram sem nome claro no snapshot pos-abertura.
- Nuxt v4 nao expoe manifest/offline/SW; essas rotas existem no Django legado (`shopman/storefront/urls.py:19-22`), nao na superficie Nuxt.

## Inventario de acoes destrutivas ou sensiveis

| Acao | UI Nuxt | Endpoint / efeito | Confirmacao atual | Risco |
| --- | --- | --- | --- | --- |
| Adicionar item ao carrinho | ProductStepper em home/menu/PDP | `PUT /api/v1/cart/skus/<sku>/` cria/ajusta sessao e hold | Nao precisa; acao explicita | Sensivel operacional: reserva estoque. Browser nao refletiu add no carrinho durante teste, embora proxy direto responda 200. |
| Incrementar/decrementar item | ProductStepper | Mesmo endpoint, reconcilia holds | Sem confirmacao | OK para carrinho, mas total otimista pode ficar incorreto ate resposta. |
| Remover item | `CartLineItem` botao Remover (`CartLineItem.vue:70-78`) | `qty=0`, libera item/hold | Sem confirmacao | P2: reversivel, mas pode perder reserva se estoque acabar. |
| Aceitar quantidade disponivel | `CartLineItem` alerta (`CartLineItem.vue:99-107`) | Reduz qty para disponivel | Sem confirmacao | P3: copia clara, ajuste esperado. |
| Aplicar cupom | `CartCouponSection` | `POST /api/v1/cart/coupon/` | Sem confirmacao | Baixo; reversivel. |
| Remover cupom | `CartCouponSection` | `DELETE /api/v1/cart/coupon/` | Sem confirmacao | P3: pode alterar total; reversivel se cliente lembra codigo. |
| Enviar pedido | Checkout desktop/sticky mobile (`checkout.vue:578-587`, `596-610`) | `POST /api/v1/checkout/`, cria pedido e pode iniciar pagamento | Sem confirmacao final alem do resumo | P1: sem idempotency key cliente, data pode faltar, payload endereco/pagamento/fidelidade incompleto. |
| Navegar para pagamento pix/card | `navigateTo(next_url)` externo (`checkout.vue:237-239`) | Sai para `/pedido/<ref>/pagamento/` Django | Implicita apos pedido | P1: pagamento fora da superficie Nuxt e sem recovery Nuxt. |
| Repetir pedido com carrinho vazio | `conta.vue:80-82` + `useReorder.ts:23-50` | `POST /api/v1/orders/<ref>/reorder/` adiciona itens | Sem confirmacao | P2: muta carrinho e holds; aceitavel se copy clara. |
| Repetir pedido - append | Modal conflito (`ReorderConflictModal.vue:34-44`) | `mode=append` | Modal unica | P2: aumenta carrinho, pode reservar estoque. |
| Repetir pedido - replace | Modal conflito (`ReorderConflictModal.vue:45-53`) | `mode=replace`; `CartService.clear()` abandona sessao (`surface.py:236-239`, `cart.py:465-473`) | Modal unica, sem listar carrinho atual/perda | P1: acao destrutiva abandona carrinho e potencialmente holds sem release imediata clara. |
| Excluir endereco | Conta (`conta.vue:35-43`) | `DELETE /api/v1/account/addresses/<id>/` | `window.confirm` nativo | P2: apaga dado de cliente; confirmacao existe, mas sem contexto/undo. |
| Definir endereco padrao | Conta (`conta.vue:54-62`) | `POST action=default` | Sem confirmacao | P3: reversivel. |
| Salvar endereco | Modal (`AddressFormModal.vue:46-77`) | POST/PATCH endereco | Submit normal | P2: perde campos estruturados/verificacao. |
| Salvar nome no login | Login (`login.vue:108-131`) | PATCH profile; falha engolida | Sem confirmacao | P2: pode divergir cliente/backend. |
| Sair | `/sair` (`sair.vue:8-28`) | Tentativa POST `/auth/logout/`, depois limpa local | Sem confirmacao | P1/P2: proxy 404; usuario pode achar que saiu do Django quando so limpou cliente. |
| Cancelar pedido | Ausente no Nuxt | Django legado `pedido/<ref>/cancelar/` | N/A | P1: ciclo de vida cliente incompleto. |
| Confirmar/mock pagamento | Ausente no Nuxt | Django legado `mock-confirm` | N/A | Fora de escopo Nuxt atual; precisa WP de pagamento. |

## Achados

### P1 - Pagamento nao pertence ao Nuxt v4

Evidencia: checkout API retorna rota Django `/pedido/<ref>/pagamento/` para pix/card (`shopman/storefront/api/views.py:274-278`) e Nuxt marca navegacao externa (`checkout.vue:237-239`). Nao existe pagina Nuxt de pagamento.

Impacto: quebra mobile-first, tracking de conversao, recovery de pagamento, consistencia de copy, acessibilidade e contrato visual. O usuario sai do fluxo Nuxt no momento mais sensivel.

### P1 - Proxies SSE/logout top-level nao estao registrados

Evidencia: arquivos existem em `server/pedido/...`, `server/storefront/...`, `server/auth/...` (`server/pedido/[ref]/events.get.ts`, `server/storefront/stock/events/[channel].ts`, `server/auth/[...path].ts`), mas `npm run build` gerou apenas rotas Nitro `routes/api/auth` e `routes/api/v1`. Curl contra Nuxt retornou 404 para stock SSE, order SSE e `/auth/session/`.

Impacto: disponibilidade ao vivo e tracking usam fallback/polling enquanto a UI diz "Atualizando ao vivo"; logout Django falha silenciosamente e limpa so o cliente.

### P1 - Checkout pode enviar pedido sem data de cumprimento

Evidencia: `commitWhen()` exige `delivery_date`, mas `validateAll()` nao exige (`checkout.vue:162-172`, `195-205`). O submit mobile sticky chama `submit()` direto (`checkout.vue:596-610`). Backend aceita `delivery_date` em branco (`serializers.py:45-48`) e so inclui no `checkout_data` quando presente (`views.py:257-260`).

Impacto: pedido pode ser commitado sem promessa de data, prejudicando producao, pickup/delivery e expectativa do cliente.

### P1 - Idempotencia/retry do checkout nao e estavel no cliente

Evidencia: API gera nova idempotency key a cada POST (`views.py:264-269`). Cliente nao envia chave de tentativa e nao guarda `order_ref` local antes de navegar.

Impacto: Orderman mitiga duplicidade por sessao ja commitada, mas timeout/reload no limite do commit continua ambiguo para o cliente. Falhas de dominio tambem nao sao normalizadas no endpoint.

### P1 - Endereco/fulfillment perde contrato canonico

Evidencia: projection backend carrega saved address rico (`checkout.py:172-189`) e account API aceita rota, numero, bairro, CEP, place_id, coordinates (`account.py:37-70`). Nuxt tipa saved address sem esses campos (`types/shopman.ts:273-280`), copia so `formatted_address`/complemento/instrucoes (`checkout.vue:102-109`) e envia so strings (`checkout.vue:219-234`).

Impacto: delivery fee, zona, verificacao e memoria de cliente ficam frágeis; erro de entrega tende a aparecer tarde.

### P1 - Fidelidade apresentada na UI nao e aplicada no contrato

Evidencia: UI mostra saldo e checkbox (`checkout.vue:476-488`) e resumo "Aplicando ..." (`checkout.vue:528-530`), envia `use_loyalty` (`checkout.vue:233`), mas `CheckoutSerializer` nao define esse campo (`serializers.py:36-49`) e a view nao adiciona `loyalty` ao `checkout_data`.

Impacto: promessa financeira/relacional falsa. Cliente pode confirmar pedido achando que saldo sera usado.

### P1 - Reorder replace abandona carrinho sem contrato destrutivo suficiente

Evidencia: modal oferece "Substituir o carrinho" sem mostrar carrinho atual ou consequencias (`ReorderConflictModal.vue:45-53`). Backend limpa via `CartService.clear()` antes de re-adicionar itens (`surface.py:236-239`), e clear abandona a sessao (`cart.py:465-473`, `cart.py:243-245`). `abandon_session()` so marca `state="abandoned"` (`sessions.py:133-140`); a liberacao imediata de holds dessa sessao nao ficou evidente.

Impacto: perda de carrinho e reservas atuais; reorder e best-effort e pode pular itens depois da limpeza.

### P1 - Mobile drawer/header quebrou no Browser

Evidencia: em viewport `390x844`, ao abrir "Open menu", screenshot mostrou repeticao de header/menu em colunas/linhas e area principal em branco. Snapshot pos-abertura expôs botoes sem nomes claros.

Impacto: principal navegacao mobile fica nao confiavel.

### P2 - Tracking Nuxt subusa a projection canonica e tem status drift

Evidencia: backend canonical `OrderTrackingProjection` inclui `promise`, `can_cancel`, payment flags, deadlines, ETA e stale metadata (`order_tracking.py:107-143`, `198-245`). API Nuxt reduz isso para status/timeline/items/fulfillments/payment label (`tracking.py:47-86`). Frontend trata terminal como `fulfilled/delivered/cancelled` (`tracking/[ref].vue:14-24`), enquanto backend usa `completed/cancelled/returned` (`order_tracking.py:37`).

Impacto: polling pode continuar em pedidos completados, copy fica generica, cancelamento e payment recovery somem.

### P2 - Hydration mismatch no header

Evidencia: Browser logs repetidos: SSR `Shopman`, cliente `Test Shop`. Header usa `shop?.brand_name || 'Shopman'` (`AppHeader.vue:56`) e shop e populado no plugin cliente (`session.client.ts:1-13`).

Impacto: flicker, erro console e risco de DOM divergente no mobile.

### P2 - Rotas internas quebradas

Evidencia: `/menu/paes-artesanais/` no breadcrumb do PDP nao tem pagina Nuxt; dropdown autenticado aponta `/conta/pedidos` e `/conta/enderecos` sem paginas.

Impacto: navegacao de catalogo e conta tem dead ends.

### P2 - Logout e client/backend podem divergir

Evidencia: `sair.vue` ignora erro do fetch e sempre limpa cliente (`sair.vue:22-28`), mas a rota proxy `/auth/logout/` nao existe no Nuxt runtime.

Impacto: usuario pode permanecer autenticado no Django enquanto Nuxt aparenta logout local.

### P2 - Conta/memoria ainda superficial

Evidencia: profile so exibe dados; nome no login ignora falha do PATCH; fidelidade e tab visual sem contrato de uso real; preferencias/notificacoes do Django legado nao aparecem no Nuxt.

Impacto: ciclo de vida do cliente nao fecha omotenashi de retorno, preferencia, consentimento e suporte.

### P3 - SEO/PWA incompleto no Nuxt

Evidencia: Django legado tem manifest, SW, offline, robots, sitemap (`storefront/urls.py:19-29`); Nuxt so define meta basica global e PDP SEO.

Impacto: instalabilidade/offline e SEO de home/menu dependem do legado ou ficam incompletos.

## Plano de WPs autocontidos

Nao implementar antes de alinhar estes WPs. Cada WP deve terminar com testes automatizados e nova passada Browser mobile.

### WP-SF-01 - Registrar e validar rotas/proxies runtime Nuxt

Escopo:

- Mover/registrar proxies SSE e auth logout para paths Nitro reais (`server/routes` ou alternativa Nuxt correta).
- Cobrir `/storefront/stock/events/:channel`, `/pedido/:ref/events`, `/auth/logout/` e remover arquivos top-level mortos.
- Ajustar UI para nao dizer "ao vivo" quando SSE nao esta conectado.

Aceite:

- Curl contra Nuxt retorna SSE/proxy ou erro upstream controlado, nao 404 Nuxt.
- Browser logs sem `No match found` para SSE/logout.
- Teste Nitro/endpoint para cada rota.

### WP-SF-02 - Checkout transacional e idempotente

Escopo:

- Chave idempotente cliente por tentativa de checkout, enviada ao backend.
- Guard contra double submit em `submit()`.
- `validateAll()` exige data/slot conforme politica; sticky mobile respeita steps incompletos.
- Backend normaliza erros de dominio com payloads acionaveis.
- Persistir/reconciliar `order_ref` apos commit antes de navegacao.

Aceite:

- Teste de double click/retry retorna mesmo pedido ou recovery claro.
- Pedido sem data exigida falha antes do POST.
- Erros de estoque/zona/horario voltam JSON 4xx com campo e mensagem.

### WP-SF-03 - Contrato de fulfillment, endereco e taxa

Escopo:

- Enviar `saved_address_id` e/ou endereco estruturado com `place_id`, coordinates, route, number, neighborhood, postal_code.
- Fazer preflight de delivery zone/taxa antes do commit.
- `has_delivery`/`has_pickup` refletirem config e calendario reais.
- `AddressAutocomplete` armazenar estrutura do Place, nao somente string.

Aceite:

- Checkout mostra taxa/indisponibilidade antes de "Enviar pedido".
- Pedido delivery sempre carrega endereco verificavel ou erro de campo.
- Testes de saved address, novo endereco, fora de zona, pickup only e delivery only.

### WP-SF-04 - Pagamento Nuxt v4

Escopo:

- Criar rota Nuxt de pagamento para pix/card.
- Consumir Payman/status canonico, QR/deep link, expiracao, retry, cancelamento quando permitido.
- Remover redirect externo para Django legado para pagamentos web.
- Integrar tracking com status de pagamento e recovery.

Aceite:

- Checkout pix/card nunca sai para `/pedido/<ref>/pagamento/` legado.
- Browser mobile cobre pedido criado -> pagamento pendente -> status/timeout/retry.
- A11y de QR/codigo copia-cola e foco apos navegacao.

### WP-SF-05 - Reorder e acoes destrutivas

Escopo:

- Reorder replace com confirmacao destrutiva explicita, listando carrinho atual e pedido antigo.
- Tornar replace atomico ou executar preflight de disponibilidade antes de limpar carrinho.
- Garantir liberacao imediata de holds ao abandonar carrinho ou documentar TTL/cleanup operacional.
- Inventariar/remediar remocao de item/cupom/endereco com undo ou copy adequada.

Aceite:

- Replace nao perde carrinho se reorder nao puder recriar itens.
- Teste de hold release/abandon.
- Browser mobile confirma modal compreensivel e sem overflow.

### WP-SF-06 - Tracking/ciclo de vida do cliente

Escopo:

- Expandir API tracking para expor `promise`, `can_cancel`, payment flags, deadlines, ETA, stale metadata, pickup info e support context.
- Alinhar status Nuxt aos status canonicos `new/confirmed/preparing/ready/dispatched/delivered/completed/cancelled/returned`.
- Implementar cancelamento permitido no Nuxt.
- Mostrar fiscal/suporte quando disponivel.

Aceite:

- Pedido `completed` para polling.
- Pedido cancelavel mostra acao com confirmacao adequada.
- Tracking degrade sem SSE com copy honesta.

### WP-SF-07 - Mobile/a11y/design/hydration

Escopo:

- Corrigir mobile drawer/header e bottom navigation.
- Eliminar hydration mismatch de brand.
- Trocar icones inexistentes (`lucide:bread`) por icones reais.
- Testar labels acessiveis dos botoes do header/drawer/ProductStepper.
- Revisar rotas internas quebradas e breadcrumbs.

Aceite:

- Browser viewport 390x844 e desktop sem duplicacao visual.
- Console sem hydration mismatch e sem icon missing.
- Rotas internas nao geram `No match found`.

### WP-SF-08 - SEO/PWA/performance

Escopo:

- Decidir se Nuxt assume manifest/SW/offline/robots/sitemap ou se Django continua fonte unica com links canonicos.
- JSON-LD LocalBusiness/Breadcrumb para home/menu.
- Metricas de bundle e lazy loading de checkout/account.
- Pre-bundling de dependencias vistas no dev (`@internationalized/date`).

Aceite:

- Build sem warnings acionaveis novos.
- Lighthouse/axe mobile baseline documentado.
- Canonical URLs consistentes com `baseURL` `/nuxt/` em producao.

## Gate antes de implementar

Implementacao funcional deve esperar pelo menos WP-SF-01, WP-SF-02, WP-SF-03 e WP-SF-07. Pagamento (WP-SF-04) e obrigatorio antes de declarar o storefront Nuxt v4 completo para escopo checkout/payment/tracking.

Proxima auditoria deve repetir:

- Browser desktop e mobile.
- `npm run build`.
- Curl de endpoints Nuxt runtime.
- Testes de checkout idempotente, delivery address, reorder replace, SSE/tracking e logout.
