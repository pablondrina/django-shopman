# Storefront Surface Spec

> **ARQUIVADA (2026-07-11).** Esta spec descrevia o contrato de experiência do
> storefront na era pré-headless (Django/Penguin, UI Thing — nomes mortos). A spec
> canônica e atual, escrita a partir do código, é
> [`docs/reference/storefront-spec.md`](../../reference/storefront-spec.md); o contrato
> de paridade é [`docs/reference/storefront-surface-parity-contract.md`](../../reference/storefront-surface-parity-contract.md).

**Status:** especificacao canonica de superficie  
**Data:** 2026-05-18  
**Escopo:** qualquer storefront publico ou app cliente Shopman, incluindo Django/Penguin, Nuxt, UI Thing, Ionic e futuras superficies.

## Proposito

Esta spec define o contrato de experiencia do Storefront. Uma nova superficie deve nascer de tres fontes, nesta ordem:

1. projections/actions canonicas do Shopman;
2. esta spec de superficie;
3. documentacao oficial da tecnologia visual escolhida.

Django/Penguin e referencia madura de descoberta de UX, nao fonte de regra. Se uma capacidade util existir so nele, ela deve ser classificada e canonizada em projection, action, service, capability ou contrato antes de ser portada.

O principio de implementacao e core enxuto, flexivel e agnostico: KISS, DRY, YAGNI, Omotenashi-first, WhatsApp-first e Mobile-first. A superficie e uma casca ergonomica; Shopman core/orquestrador continua sendo o canon.

## Regras

- A superficie renderiza `Projection` e dispara `Action`/mutation canonica. Ela nao calcula preco, estoque, loja aberta, pagamento, prazo, permissao de cancelamento, auth gate, reorder, taxa, desconto ou status de pedido.
- O ciclo obrigatorio e `InteractionContext -> Projection -> node canonico(actions[]) -> Action -> Intent -> Mutation -> Projection`.
- Copy factual e operacional vem do backend. A superficie pode ajustar hierarquia visual, nao inventar promessa.
- Estado local permitido: rota, drawer/dialog aberto, tab, busca digitada, formulario em rascunho, foco, scroll, skeleton, haptic, cache reconciliavel, estado `pending` e chave de idempotencia.
- Estado local proibido: fonte alternativa de verdade operacional, fallback de pricing/stock/status, endpoint nao canonico, status/lifecycle/control plane novo, action fabricada quando a projection poderia entregar.
- Sem compatibilidade legada aberta. Ao tocar um fluxo, convergir para projections/actions atuais em vez de preservar ambiguidade.

## Contratos Canonicos

| Momento | Projection/action |
| --- | --- |
| Home | `GET /api/v1/storefront/home/` |
| Menu | `GET /api/v1/storefront/menu/`, `GET /api/v1/storefront/menu/{collection}/` |
| Produto | `GET /api/v1/storefront/products/{sku}/` |
| Carrinho | `GET /api/v1/storefront/cart/`, `/api/v1/cart/*` |
| Checkout | `GET /api/v1/storefront/checkout/`, `POST /api/v1/checkout/` |
| Auth | `/api/v1/auth/session/`, `device-check/`, `request-code/`, `verify-code/`, `trust-device/`, `logout/` |
| Conta | `/api/v1/account/summary/`, `profile/`, `addresses/`, `orders/`, `orders/active/`, `preferences/*`, `devices/`, `export/`, `delete/` |
| Tracking | `GET /api/v1/tracking/{ref}/`, `POST /api/v1/orders/{ref}/cancel/`, `rate/`, `conversation/` |
| Pagamento | `GET /api/v1/payment/{ref}/`, `GET /api/v1/payment/{ref}/status/`, debug `mock-confirm/` quando projetado |
| Recompra | `POST /api/v1/orders/{ref}/reorder/` |
| Geocode | `GET /api/v1/geocode/reverse` server-side |

Action minima: `ref`, `kind`, `label`, `priority`, `enabled`, `reason`, `href`, `method`, `payload_schema`, `idempotency`, `confirmation`. Mutations sensiveis usam `Idempotency-Key` ou `idempotency_key` quando a action declarar `required` ou `recommended`.

## Donos Canonicos

Cada pergunta da interface deve ter dono claro antes de virar tela:

| Pergunta | Dono canonico |
| --- | --- |
| O que vender, por quanto e com qual promocao? | Offerman/catalog projections |
| Posso prometer este SKU/quantidade/agora? | Stockman availability/promise via projection |
| Ha producao planejada, prevista ou finalizada que afete promessa? | Craftsman, consumido por Stockman/projection |
| Quem e o cliente, preferencias, enderecos, dispositivos e historico? | Guestman/Doorman/account projections |
| O cliente pode acessar/continuar este fluxo? | Doorman/auth actions |
| O pedido pode ser criado, cancelado, avaliado ou repetido? | Orderman/order actions |
| Como pagar, aguardar, recuperar ou confirmar pagamento? | Payman/payment projections |
| Como variar por canal/superficie? | ChannelConfig resolvido antes da projection |

Se a pergunta nao encaixar em um dono, a fronteira esta errada ou falta projection/capability.

## Traducao Entre Frameworks

Uma superficie nova deve preservar a mesma UX canonica e traduzir apenas a materializacao:

- `Sheet`, `Drawer`, `Modal`, `Dialog`, `IonModal` ou equivalente representam o mesmo bloco quando cumprem foco, dismiss, safe-area e recovery.
- `Tabs`, `Segmented Control`, `Pills`, `IonSegment` ou equivalente representam o mesmo rail/filtro quando mantem uma unica fonte de busca/filtro.
- `Card`, `List Item`, `IonItem`, `Polaris Card` ou equivalente representam o mesmo card quando preservam anatomia, CTA e estados.
- `Toast`, `Alert`, `Alert Dialog`, `IonToast` ou equivalente representam feedback/recovery conforme severidade.
- Rotas, gestos e animacoes podem variar; ordem de blocos, dados, actions, estados e hyper focus nao podem variar.

Regra para LLM/implementador: primeiro monte a arvore de blocos; depois escolha componentes do framework; por ultimo aplique tema e microinteracoes.

## Hyper Focus

Hyper focus e a regra de atencao por momento. Em qualquer viewport, o usuario deve entender em ate 3 segundos:

- onde estou;
- qual estado importa agora;
- qual e a proxima acao primaria;
- o que me impede de avancar, se houver bloqueio;
- como recuperar ou falar com a loja.

Cada tela/bloco deve declarar:

| Campo | Exigencia |
| --- | --- |
| Tarefa primaria | Uma frase operacional: "adicionar item", "escolher horario", "confirmar pedido". |
| Acao primaria | Um unico CTA dominante, visivel sem procurar. |
| Acao secundaria | No maximo duas acoes auxiliares no mesmo foco. |
| Estado critico | Aberto/fechado, indisponivel, minimo, auth, pagamento, prazo, erro ou stale. |
| Recovery | Caminho visivel: ajustar, remover, entrar, tentar de novo, WhatsApp. |
| Ruido proibido | CTA concorrente, badge decorativo, copy longa, controle duplicado, status redundante. |

## Lente iFood Brasil

iFood e a principal referencia brasileira de expectativa mental para cardapio, sacola e acompanhamento. A lente e de UX, nao de dominio:

- cardapio mostra itens e categorias ativas para aquele dia/horario; em Shopman isso vem de `CatalogProjection`, ChannelConfig e availability;
- a pessoa monta o pedido no cardapio e fecha na sacola/carrinho; em Shopman o checkout nasce do carrinho, nao da navbar;
- a sacola e ponto decisivo: precisa reunir itens, meios de pagamento, cupons, saldo/loyalty, avisos e bloqueios antes de finalizar;
- produto digital substitui atendente: nome curto, foto confiavel, descricao objetiva, preco claro, categoria correta, alergicos/dietas e observacoes reduzem duvida e abandono;
- categorias devem refletir comportamento de compra: mais vendidos/destaques no topo, combos quando existirem, itens principais, bebidas e sobremesas bem posicionados;
- tracking deve manter expectativa honesta: pedido recebido, preparo, pagamento, retirada/entrega, atraso/stale e proxima acao.

Esta lente deve ser combinada com Shopify/Polaris para simplicidade de cart/checkout, Odoo para densidade operacional e Ionic para experiencia app/mobile nativa.

## Blueprint De Paginas

Toda superficie deve seguir esta ordem de blocos. Pode mudar grid, breakpoint ou componente, mas nao deve mudar o fluxo sem justificar gap.

### Global Web Shell

1. Skip link/acessibilidade.
2. Status operacional, apenas se `home.shop_status.message`.
3. Navbar principal.
4. Conteudo da rota.
5. Cart drawer global.
6. Toast/alert host global.
7. Footer web.
8. Bottom nav mobile, exceto telas que exigem foco transacional e declaram isso.

### Home

Mobile:

1. Navbar compacta/status.
2. Hero de uma decisao: boas-vindas/aniversario, pedir agora, recompra ou valor de marca.
3. CTA principal para cardapio ou action projetada.
4. Quick reorder quando action existir.
5. Destaques/recem saindo do forno.
6. Categorias/atalhos.
7. Como funciona/retirada/entrega em formato curto.
8. WhatsApp/support.
9. Footer web quando aplicavel.

Desktop:

1. Navbar/status.
2. Hero visual com CTA.
3. Faixa de destaques.
4. Categorias + disponibilidade.
5. Como funciona + horarios.
6. WhatsApp/support.
7. Footer.

### Menu

Mobile:

1. Header `Cardapio`.
2. Sticky search trigger unico + rail de secoes.
3. Banner de happy hour/alerta quando existir.
4. Secoes em lista vertical; cada secao tem titulo, descricao e product cards horizontais.
5. Cart floating/drawer affordance com count/total quando houver itens.
6. Empty/error/recovery se necessario.

Desktop:

1. Breadcrumb.
2. Header `Cardapio`.
3. Toolbar sticky: busca unica, rail de secoes, grid/list toggle opcional.
4. Conteudo em grid/lista por secao.
5. Cart drawer acionavel pela navbar e por add-to-cart.

### PDP

Mobile:

1. Header/breadcrumb compacto.
2. Media.
3. Nome, descricao curta, preco, disponibilidade.
4. CTA sticky `Adicionar` ou quantity control.
5. Detalhes em accordions.
6. Recovery/WhatsApp se bloqueado.

Desktop:

1. Breadcrumb.
2. Layout duas colunas: media; info/CTA.
3. Detalhes abaixo ou coluna secundaria.
4. Cart drawer ao adicionar quando apropriado.

### Cart

Drawer:

1. Header `Carrinho` + fechar.
2. Minimum/progress ou warnings.
3. Linhas do carrinho.
4. Coupon.
5. Totals.
6. Upsell.
7. CTA sticky: `Ver carrinho`, `Finalizar pedido` ou bloqueio com reason.

Page:

1. Breadcrumb.
2. Header com count/subtotal.
3. Warnings/minimum.
4. Linhas detalhadas.
5. Coupon.
6. Summary sticky desktop.
7. CTA checkout + continuar comprando.

### Checkout

Anonimo quando auth exigida:

1. Breadcrumb/header.
2. Auth gate seguindo `checkout.auth_action`.
3. Resumo de carrinho visivel.
4. Recovery WhatsApp.

Autenticado:

1. Breadcrumb/header.
2. Resumo compacto de progresso.
3. Section contato.
4. Section fulfillment.
5. Section endereco, apenas delivery.
6. Section quando.
7. Section pagamento/notas/loyalty.
8. Section revisao.
9. Summary persistente.
10. Submit idempotente.

### Payment

1. Header pedido/total.
2. Payment promise.
3. Metodo: Pix QR/copia, card checkout ou recovery.
4. Deadline/status polling.
5. Actions projetadas.
6. Link tracking.

### Tracking

1. Header pedido/status.
2. Promise dominante.
3. Actions primarias: pagar, suporte, cancelar/avaliar/reorder quando projetadas.
4. Progress/timeline.
5. Itens e total.
6. Pickup/delivery info.
7. Freshness/stale/retry.
8. Yoin/reorder/menu quando finalizado.

### Account

1. Header saudacao/telefone.
2. Tabs/segments: perfil, pedidos, fidelidade, configuracoes.
3. Perfil: dados + enderecos.
4. Pedidos: historico/reorder/tracking.
5. Fidelidade: saldo/progresso/transacoes.
6. Config: notificacoes, preferencias, dispositivos, privacidade.

## Rotulos E Microcopy Padrao

Copy factual vem da projection. Quando a projection nao trouxer label especifico, usar estes rotulos padrao para manter consistencia entre superficies:

| Intencao | Rotulo padrao |
| --- | --- |
| Ir ao menu | `Ver cardapio` ou `Cardapio` em nav |
| Adicionar item | `Adicionar` |
| Atualizar quantidade | `Atualizar` apenas quando a acao muda qty existente |
| Abrir carrinho | `Carrinho` |
| Ver carrinho completo | `Ver carrinho` |
| Continuar compra | `Continuar comprando` |
| Entrar | `Entrar por telefone` quando em auth/checkout; `Entrar` na nav |
| Avancar etapa | `Continuar` |
| Editar etapa concluida | `Editar` |
| Finalizar checkout | `Finalizar pedido` |
| Pagar | `Pagar pedido` ou label projetado por PaymentProjection |
| Acompanhar pedido | `Acompanhar pedido` |
| Reorder | `Pedir de novo` |
| Suporte WhatsApp | `Falar no WhatsApp` ou label projetado |
| Remover linha | `Remover` |
| Aplicar cupom | `Aplicar` |

Evitar sinonimos concorrentes na mesma superficie. Se a marca escolher `Sacola`, aplicar de forma global e documentada; o contrato continua `CartProjection`.

## Building Blocks

Building block e uma unidade de UX reutilizavel. Ele consome projection/action, tem anatomia visual definida e pode variar por tecnologia. Ele nao possui regra de negocio propria.

### App Shell / Navbar Principal

Tarefa: orientar, mostrar estado operacional e manter compra/conta acessiveis.

Dados:

- `home.shop.brand_name`, `logo_url`, `tagline`;
- `home.shop_status`;
- `cart.items_count`;
- `auth/session` ou `account/summary`;
- `account/orders/active/` quando autenticado;
- `home.public_config.whatsapp_url` para suporte.

Anatomia:

- esquerda: marca clicavel para Home;
- centro/desktop: `Cardapio`, `Carrinho`, `Conta/Pedidos` e links institucionais essenciais;
- direita/desktop: botao de carrinho com badge, avatar/entrar, suporte quando necessario;
- mobile: header compacto + bottom nav; menu hamburguer so para itens secundarios;
- banner operacional acima ou abaixo do header quando `shop_status.message` existir.

Estados:

- loja aberta: status discreto, sem competir com CTA de compra;
- loja fechada/em pausa: banner claro com mensagem projetada e proxima acao;
- carrinho vazio/com itens;
- autenticado/anonimo;
- pedido ativo: badge discreto em Conta/Pedidos.

Falhas P1:

- checkout como item primario de navbar;
- status derivado de `omotenashi` ou relogio local;
- carrinho inacessivel no desktop;
- bottom nav como unica forma de encontrar checkout/carrinho.

### Bottom Nav Mobile

Tarefa: permitir retorno rapido aos quatro destinos de maior frequencia.

Itens padrao: `Inicio`, `Cardapio`, `Carrinho`, `Conta` ou `Entrar`. Nao incluir `Finalizar` como aba. Checkout e um estado do carrinho.

Requisitos:

- area segura com `env(safe-area-inset-bottom)`;
- icone + label;
- badge de carrinho;
- badge de pedido ativo quando sustentado por projection/API;
- estado ativo por rota, nao por clique local.

### Rodape Web

Tarefa: fechar a pagina com confianca, contato e contexto operacional.

Obrigatorio em storefront web responsivo, salvo app nativo/full-screen. Deve usar `ShopProjection` e copy projetada:

- marca, descricao curta, cidade;
- horarios de `opening_hours`;
- links: menu, como funciona/institucional quando existir, pedidos/conta ou entrar;
- contato: endereco, mapas, telefone, email, social links;
- WhatsApp quando configurado;
- copyright/copy institucional.

Nao usar rodape como deposito de CTA transacional. CTA de compra pertence ao fluxo principal.

### Breadcrumbs

Tarefa: orientar profundidade sem roubar foco.

Regras:

- aparecer em Menu, PDP, Cart, Checkout, Tracking, Payment e Conta quando web;
- truncar responsivamente com ellipsis clicavel;
- ultimo item e texto, nao link;
- em mobile pode virar linha compacta, mas nao sumir onde a rota tem profundidade.

Dados: rota local + `breadcrumb_category` na PDP + labels projetados quando existirem.

### Cabecalho De Pagina Ou Secao

Tarefa: dizer qual e o trabalho daquela tela.

Anatomia:

- titulo curto;
- uma linha de contexto;
- estado critico ou action secundaria quando realmente necessaria;
- nunca competir com CTA principal.

Exemplos:

- Menu: "Cardapio" + subtitulo de `sections_copy`/omotenashi;
- Carrinho: item count + subtotal;
- Checkout: "Finalizar pedido" + progresso/estado;
- Conta: saudacao + telefone;
- Tracking: pedido + status label.

### Busca, Colecoes E Filtros

Tarefa: encontrar produto rapido sem perder o contexto do cardapio.

Dados:

- `catalog.sections`, `categories`, `items`, `featured`, `favorite_category_ref`, `happy_hour`;
- `item.search_terms`, `tags`, `dietary_info`, `allergens`, availability projetada.

Anatomia:

- sticky search affordance unica;
- rail horizontal de pills de secoes/colecoes, com scroll inteligente e pill ativa;
- `Todos` ou retorno ao topo, sem duplicar grid;
- overlay/dialog de busca com categorias quando query vazia e resultados quando query ativa;
- filtros adicionais como dieta/alergeno/disponibilidade apenas se sustentados por projection e sem esconder produtos de forma ambigua;
- toggle grid/lista quando a tecnologia e viewport suportarem.

Grid/lista:

- mobile default: lista/card horizontal para leitura rapida, imagem pequena, preco e CTA visiveis;
- desktop default: grid denso, 2-3 colunas, cards alinhados;
- lista desktop opcional: rows densas para compra recorrente, com imagem menor, badges e CTA no fim;
- estado de visualizacao e local, mas itens/filtros continuam derivados da projection.

Scroll:

- rail sincroniza com a secao visivel;
- clique em pill faz scroll para secao e centraliza pill;
- busca aberta prende foco e fecha por escape/back;
- nada de renderizar todos os grids duplicados dentro de tabs escondidas.

Falhas P0/P1:

- dois campos de busca primarios;
- scroll-spy quebrando layout;
- busca que ignora termos projetados;
- filtros que recalculam disponibilidade ou promocao localmente;
- DOM massivo por render duplicado.

### Product Card

Tarefa: decidir rapidamente se o item entra no carrinho ou merece PDP.

Dados:

- `sku`, `name`, `short_description`, `image_url`, `category`, `tags`, `search_terms`;
- `price_display`, `original_price_display`, `promotion_label`, `has_promotion`;
- `availability`, `availability_label`, `can_add_to_cart`, `available_qty`, `qty_in_cart`;
- `dietary_info`, `allergens`, `is_new`, `is_featured`.

Anatomia mobile:

- thumb fixa esquerda;
- nome com ate duas linhas;
- descricao curta opcional, normalmente escondida se faltar espaco;
- preco e promocao;
- disponibilidade discreta;
- CTA primario a direita/rodape: `Adicionar` quando `qty_in_cart == 0`; stepper quando `qty_in_cart > 0`.

Anatomia desktop:

- imagem superior ou lateral conforme grid/lista;
- nome, descricao, badges, preco;
- action alinhada e estavel, sem deslocar card vizinho;
- hover/focus mostram affordance de PDP, nao escondem CTA.

Estados:

- disponivel: sem badge verde chamativo; CTA primary;
- low/planned: badge discreto + reason/tooltip se projetado;
- indisponivel: CTA disabled com `availability_label`;
- promocao: preco anterior riscado + label pequena;
- busy: desabilitar CTA localmente e preservar largura;
- erro mutation: toast/dialog de recovery e refresh de cart projection.

Falhas:

- `NumberField` em zero como primeira acao;
- dois controles de quantidade no mesmo card;
- card sem preco visivel;
- imagem/copy deslocando CTA;
- badge decorativo competindo com preco/CTA.

### Product Detail Block

Tarefa: confirmar uma decisao de compra com informacao suficiente.

Blocos obrigatorios:

- media/gallery;
- nome, descricao curta, preco/promocao, disponibilidade;
- CTA sticky no mobile e inline no desktop;
- quantity/add block;
- detalhes em accordions: ingredientes, alergenos/dietas, nutricao, conservacao, peso/medidas, bundle/components;
- breadcrumb e SEO quando web.

Hyper focus:

- acima da dobra: produto, preco, disponibilidade e adicionar;
- detalhes longos ficam colapsados, mas com padding e hierarquia consistente;
- add button precede stepper quando ainda nao ha item no carrinho.

### Quantity Control

Tarefa: alterar quantidade com minimo erro.

Regras:

- absolute set qty via mutation canonica;
- menos, valor, mais; alvos de toque >= 44px;
- valor em texto ou number field canonico da lib, mas sem permitir layout shift;
- `effectiveMax` visual pode orientar, mas backend valida;
- ao chegar no maximo, mostrar hint discreto, nao alerta bloqueante;
- remover item e acao explicita em carrinho, nao decremento invisivel abaixo de 1, salvo UX especifica com undo.

### Cart Line / Cart Card

Tarefa: revisar e corrigir uma linha do pedido.

Dados:

- `CartItemProjection`: sku, name, qty, price, total, image, original price, discount, availability, available qty, hold/deadline;
- actions/recovery vindas da mutation/projection.

Anatomia:

- thumb;
- nome;
- unit price e desconto;
- warnings/holds;
- stepper;
- total da linha;
- remover;
- recovery inline quando indisponivel: aceitar disponivel, remover, alternativas se projetadas.

Estados:

- awaiting confirmation: badge + mensagem + polling;
- ready for confirmation: deadline, countdown reconciliavel e CTA;
- unavailable: warning com qty pedida e disponivel;
- busy: linha preserva espaco e bloqueia duplo submit;
- removed: undo por toast/action quando suportado.

### Cart Drawer

Tarefa: permitir revisao rapida sem sair do fluxo.

Anatomia:

- sheet/drawer com titulo e fechar;
- progresso de minimo no topo quando existir;
- lista scrollavel de linhas;
- coupon compacto;
- totals fixos perto do rodape;
- upsell projetado;
- CTA rodape sticky: `Ver carrinho` ou `Finalizar pedido`, conforme contexto/action;
- continuar comprando.

Desktop pode abrir drawer ao adicionar; mobile deve evitar interrupcao excessiva se isso roubar foco da compra. A decisao e de superficie, mas o cart state e projection.

### Cart Page / Summary

Tarefa: revisar pedido completo e entrar no checkout.

Obrigatorio:

- header com count/subtotal;
- alertas globais antes das linhas;
- lista de linhas detalhada;
- coupon;
- resumo sticky no desktop e abaixo no mobile;
- minimo/upsell;
- CTA de checkout sempre visivel quando possivel;
- bloqueio com reason quando nao for possivel.

Falha fatal: usuario com carrinho valido nao conseguir encontrar como finalizar no desktop.

### Checkout Layout

Tarefa: concluir pedido sem ambiguidade transacional.

Estrutura:

- coluna principal com secoes/steps;
- resumo persistente no desktop;
- resumo colapsavel/sticky no mobile;
- CTA final apenas na etapa de revisao/pagamento ou rodape sticky com estado claro;
- progresso visual simples, nao wizard ornamental;
- cada etapa concluida mostra resumo e botao editar.

Checkout nunca deve ser "form longo sem estado". Cada secao precisa declarar done/current/upcoming/blocked.

### Checkout Section

Padrao para cada secao:

- titulo;
- estado: `current`, `done`, `upcoming`, `blocked`, `error`;
- resumo compacto quando done;
- campos/actions quando current;
- CTA `Continuar` quando ha proxima etapa;
- erros perto do campo;
- dados vindos da projection;
- sem avancar localmente quando a action/projection bloqueia.

### Checkout: Contato/Auth

Tarefa: garantir identidade minima do pedido.

Dados: `checkout.customer_name`, `customer_phone`, `is_authenticated`, `requires_authentication`, `auth_action`.

Requisitos:

- se anonimo e auth exigida: mostrar gate claro e seguir `auth_action`;
- se autenticado: mostrar nome/telefone e permitir editar nome quando sustentado;
- trocar conta deve confirmar e preservar retorno para checkout;
- telefone vem do auth, nao campo livre autoritativo quando ja autenticado.

### Checkout: Fulfillment

Tarefa: escolher pickup/delivery.

Dados: `fulfillment_options`, `has_pickup`, `has_delivery`, `pickup_hint`, `delivery_hint`.

UX:

- radio cards com icone, label e hint;
- opcao indisponivel nao deve aparecer como selecionavel;
- se so houver uma opcao, mostrar como selecionada e explicar brevemente;
- mudanca de fulfillment recalcula etapas dependentes sem perder rascunho irrelevante.

### Checkout: Endereco

Tarefa: escolher ou informar endereco de entrega.

Dados: `saved_addresses`, `preselected_address_id`, geocode endpoint/capability.

UX:

- saved addresses primeiro quando existirem;
- novo endereco em sheet/dialog mobile e inline desktop;
- autocomplete/geocode se disponivel, com fallback manual;
- campos essenciais: formatted address, numero, complemento, bairro/cidade/UF/CEP quando projetados/suportados;
- default/label (`Casa`, `Trabalho`, `Outro`) quando sustentado por account API;
- erro de area/numero/geocode deve apontar campo e recovery.

### Checkout: Quando

Tarefa: escolher data e horario prometivel.

Dados: `pickup_slots`, `earliest_slot_ref`, `closed_dates_json`, `max_preorder_days`.

UX:

- datepicker/calendar canonico da lib;
- slots como radio/lista, com disabled reason quando vier projetado;
- refresh da checkout projection ao trocar data;
- destaque discreto do horario mais cedo;
- nao calcular feriado/fechado localmente.

### Checkout: Pagamento

Tarefa: escolher metodo e informar observacoes finais.

Dados: `payment_methods`, `default_payment_method`, loyalty fields.

UX:

- radio cards de pagamento;
- Pix/card/cash labels vindos da projection;
- loyalty como switch/checkbox so se saldo > 0;
- notas como disclosure discreto, nao campo gigante por padrao;
- explicar bloqueios pelo `reason` da action ou erro backend.

### Checkout: Revisao E Submit

Tarefa: confirmar exatamente o que sera criado.

Dados: `checkout.cart`, escolhas locais de formulario, action `checkout`.

Requisitos:

- resumo de itens e total da projection;
- fulfillment, data/slot, endereco e pagamento escolhidos;
- termos/observacoes quando aplicavel;
- submit com idempotency key;
- loading bloqueia duplo clique;
- resposta segue `next_url`;
- erro preserva rascunho e volta ao bloco que resolve.

Falhas P0:

- submit sem idempotencia;
- total calculado localmente;
- checkout sem CTA visivel;
- permitir submit quando `checkout.actions[checkout].enabled == false`.

### Auth OTP Block

Tarefa: autenticar sem senha e sem ansiedade.

Anatomia:

- telefone com formato e pais;
- request code;
- OTP/pin input canonico da lib;
- metodo real de entrega;
- alert dismissable com OTP debug apenas quando API retornar;
- trocar telefone com confirmacao;
- trusted device prompt apos sucesso;
- WhatsApp recovery.

### Tracking / Promise Block

Tarefa: mostrar o estado do pedido e a proxima expectativa.

Dados: `TrackingResponse`, `promise`, `promise_rows`, `progress_steps`, `timeline`, payment gate, actions.

Anatomia:

- titulo com ref do pedido;
- status/promise dominante;
- proximo evento e prazo;
- timeline/progress;
- itens em accordion/lista;
- pickup/delivery info;
- actions: pagar, cancelar, avaliar, pedir de novo, suporte;
- freshness: atualizado ha X, stale/retry se necessario.

### Payment Block

Tarefa: pagar ou entender o estado do pagamento.

Dados: `PaymentProjection`, `PaymentStatusResponse`.

Anatomia:

- total e pedido;
- promise/tone;
- Pix QR/copia-e-cola ou checkout url;
- prazo/expiracao;
- polling status;
- recovery/action;
- tracking link.

### Account Blocks

Tarefa: relacionamento e memoria sem virar backoffice.

Blocos:

- profile summary;
- address list/form;
- order history card;
- loyalty card;
- preferences toggles;
- trusted devices;
- privacy/export/delete.

Regras:

- pedidos mostram status, data, total e CTA de tracking/reorder;
- toggles chamam account APIs;
- delete/export usam confirmacao e copy forte;
- nunca inferir preferencia/favorito sem projection.

### Alert, Toast, Dialog, Sheet E Empty State

Regras:

- alert inline para bloqueio ou risco no contexto;
- toast para feedback transitorio e undo;
- alert dialog para destrutivo ou troca de conta;
- sheet/drawer para carrinho, PDP rapida, endereco mobile;
- empty state sempre tem proxima acao concreta;
- skeleton deve preservar dimensoes e nao deslocar layout.

Verde/success so para sucesso real. Warning/danger para risco e bloqueio. Informativo/neutro para estado comum.

## Shell E Navegacao

- Primeira tela e experiencia real de compra, nao landing page.
- Header mostra marca, status operacional e acesso a menu, carrinho e conta. Checkout nao e item primario de navbar; ele nasce do carrinho ou de uma action projetada.
- Mobile deve ter navegacao curta, segura para `safe-area`, com carrinho sempre acessivel. Desktop precisa expor carrinho e proxima acao com a mesma clareza, sem depender de bottom nav.
- Breadcrumbs, SEO/PWA/offline e compartilhamento sao shell da superficie, mas conteudo factual vem de projection.
- `home.shop_status` e a unica fonte de verdade para aberto/fechado/pausa/horario. `home.omotenashi` e lente de momento, saudacao e personalizacao.

## Home

Deve renderizar:

- marca, saudacao e momento de `home.omotenashi`;
- status da loja e horario de `home.shop_status`/`opening_hours`;
- hero com uma decisao de atencao por vez, usando `home.hero_copy` e estado real: boas-vindas/aniversario, pedir agora, recompra quando `home.actions` ou `last_order_ref` permitirem, handmade/valor de marca;
- destaques de `home.featured_items`, disponibilidade projetada e CTA para menu/PDP/carrinho;
- categorias/secoes e "proxima melhor acao" derivadas de actions/copy;
- banners de fechamento, origem WhatsApp e suporte quando vierem de projection/config;
- WhatsApp-first: handoff visivel quando `public_config.whatsapp_url` existir.

Nao pode mostrar status contraditorio, colapsar varios heros em uma frase confusa, nem duplicar CTA de checkout sem carrinho/action.

## Menu

Deve renderizar:

- uma unica busca primaria, com categorias/secoes de `catalog.sections` e itens de `catalog.items`;
- filtros por categoria/secao, happy hour, categoria favorita e destaques conforme `CatalogProjection`;
- cards ricos com imagem, nome, descricao curta, preco, promocao, tags/dietas/alergenos, disponibilidade, `qty_in_cart`, `available_qty` e CTA coerente;
- disponibilidade de listing como orientacao projetada. A mutacao de carrinho continua validando estoque/promessa no backend;
- estados vazio, skeleton, erro recuperavel e alternativa WhatsApp quando aplicavel.

Nao deve renderizar dois campos de busca, grids duplicados escondidos, steppers em zero como CTA principal, nem recalcular filtro comercial diferente da projection. Busca client-side e permitida apenas sobre indice vindo da projection.

## Produto

Deve usar `ProductDetailProjection` em rota, dialog ou sheet responsivo. Deve exibir:

- galeria/imagem, breadcrumbs, nome, descricao curta/longa, preco/promocao, disponibilidade e quantidade no carrinho;
- bundle/components, peso, medidas, porcoes, ingredientes, aviso de tracos, alergenos, preferencias dietarias, conservacao e nutricao;
- CTA primario "Adicionar" quando `qty_in_cart == 0`; controle numerico so depois de haver escolha de quantidade ou item no carrinho;
- limite visual baseado em `max_qty`/`available_qty`, sem tratar isso como garantia local;
- stock error/recovery quando a mutation rejeitar ou ajustar quantidade.

Substitutos nao pertencem a PDP por padrao; aparecem em erro de estoque/recovery quando projetados.

## Carrinho

Deve existir como drawer sempre acessivel e como pagina quando a plataforma pedir. Deve renderizar apenas `CartProjection`:

- linhas, quantidade, imagem, preco unitario, total, descontos, availability warnings, holds e prazos;
- subtotal, total original, descontos, frete, total final, coupon, progresso de pedido minimo e upsell;
- avisos de item indisponivel, aguardando confirmacao ou pronto para confirmacao;
- CTA para checkout quando action/projection permitir; se bloquear, mostrar `reason` e proxima action;
- empty state com volta ao menu e suporte quando aplicavel.

Mutacoes: set qty por SKU, atualizar/remover linha, coupon apply/remove. Toda resposta substitui/reconcilia a projection de carrinho; a UI nao mantem total proprio.

## Auth

Login e por telefone/OTP quando a projection/action exigir. Deve renderizar:

- copy de `home.auth_copy`;
- phone input com normalizacao BR/internacional e feedback apenas de formato;
- WhatsApp como opcao/recuperacao quando `public_config.whatsapp_url` ou backend fornecer;
- trusted device por `device-check`/`trust-device`;
- OTP por `request-code`/`verify-code`, mostrando metodo real de entrega retornado pelo backend;
- `debug_otp_code` ou `dev_console_hint` somente em ambiente de dev/staging quando a API retornar explicitamente;
- etapa de nome para novo cliente quando o backend pedir.

A superficie nao decide que login e opcional. Checkout segue `checkout.requires_authentication` e `checkout.auth_action`.

## Checkout

Checkout deve ser acessivel a partir do carrinho mesmo para visitante anonimo. Se `checkout.requires_authentication` for verdadeiro e o cliente nao estiver autenticado, a tela deve seguir `checkout.auth_action` com retorno para checkout.

Jornada minima:

1. contato/identidade: `customer_name`, `customer_phone`, switch account e nome faltante quando projetado;
2. fulfillment: pickup/delivery a partir de `fulfillment_options`, `has_pickup`, `has_delivery`, hints;
3. endereco: saved addresses, criacao/edicao, default e geocode quando endpoint/capability estiver disponivel;
4. quando: data, `closed_dates_json`, `max_preorder_days`, `pickup_slots`, refresh por data via checkout projection;
5. pagamento: `payment_methods`, default, loyalty quando `loyalty_balance_q > 0`, notas;
6. revisao: resumo do carrinho e escolhas atuais sem recalcular total;
7. submit: action `checkout`, payload conforme `payload_schema`, idempotencia obrigatoria e resposta `order_ref`/`next_url`.

Erros devem voltar ao campo ou action que resolve. Nao criar etapa local sem projection/action que a sustente.

## Pagamento

Deve renderizar `PaymentProjection` e `PaymentPromiseProjection`:

- total, metodo, promessa, prazo, proxima acao, recovery e status;
- PIX QR/copia-e-cola/expiracao; card/hosted checkout quando `checkout_url` existir;
- polling por `status_url` e redirecionamento apenas quando `PaymentStatusResponse.should_redirect` indicar;
- botao debug/mock somente quando `payment.is_debug` e action projetada permitirem;
- voltar para tracking por `tracking_url`.

Nao derivar payment gate ou expiracao por relogio local como fonte de verdade. Countdown visual e permitido se reconciliar por status projection.

## Confirmacao E Tracking

Depois do checkout, seguir `next_url`: pagamento quando houver gate, senao tracking/confirmacao. Tracking deve renderizar:

- `status_label`, `promise`, `promise_rows`, timeline, progress steps e freshness (`last_updated`, `stale_after_seconds`);
- itens, total, frete, pickup/delivery fulfillments, pickup info e directions URL;
- payment pending/expired/confirmed e `requires_payment_gate`/`payment_gate_url`;
- actions projetadas: cancelar, avaliar, pedir de novo, mock confirm em debug, suporte/WhatsApp;
- live update por SSE/polling quando a plataforma suportar; fallback visivel quando stale/offline.

Cancelamento, rating e reorder usam actions/mutations canonicas e confirmacao quando destrutivas.

## Conta, Historico E Relacionamento

Quando autenticado e sustentado por projection/API, a superficie deve oferecer:

- resumo de cliente, dados pessoais e telefone;
- enderecos salvos com criar/editar/remover/default;
- pedidos recentes/historico com filtros e CTA de tracking/reorder;
- fidelidade: tier, pontos, carimbos e transacoes;
- preferencias de notificacao e alimentares;
- dispositivos confiaveis;
- exportacao e exclusao de conta com confirmacao forte.

Nao improvisar `customer_summary`, `favorite_product` ou memoria de cliente fora de projection. Se a UX precisar desse insight, canonizar projection pequena reutilizavel.

## Erros E Recovery

- 409/stock: mostrar item afetado, quantidade pedida, quantidade disponivel, motivo, actions de ajustar/remover/substituir/retry quando vierem do backend.
- 400/422: associar erro ao campo/action; manter formulario sem perder rascunho local.
- 401/403: seguir auth/access action, preservando `next`.
- 429: mostrar tempo/retry/support de projection ou resposta.
- 5xx/offline: explicar impacto, manter carrinho local apenas como cache nao autoritativo e oferecer retry/WhatsApp.
- Toda falha recuperavel deve pedir extension de projection/action se a resposta atual nao trouxer caminho claro.

## Design E Omotenashi

- Mobile-first, WhatsApp-first, Omotenashi-first: a proxima acao deve estar evidente antes da explicacao.
- Visual serio e denso o suficiente para compra recorrente; evitar marketing vazio.
- Uma funcao, um controle: sem busca duplicada, quantidade duplicada, status duplo ou CTA escondido.
- Touch targets minimos, foco visivel, labels acessiveis, ordem de teclado, dialog/sheet com foco preso e retorno seguro.
- Success/verde fica para sucesso evidente. Badges comuns usam tom neutro, primary ou outline.
- A tecnologia visual deve usar seus componentes canonicos para command/search, dialog/sheet, tabs, accordion, alert, toast, skeleton, badge, progress, datepicker, radio/select, number field, tooltip, empty state e timeline quando existirem.
- Componentes scaffoldados/copied pertencem a superficie e podem ser ajustados, mas continuam primitives visuais; regra de dominio nao entra neles.

## Referencias Nao Canonicas

Estas referencias ajudam a calibrar UX, mas nao substituem projections/actions:

- Django/Penguin Shopman: referencia interna mais madura para descobrir blocos e gaps.
- iFood consumidor/parceiro: cardapio ativo por dia/horario, categorias, sacola decisiva, produto como vendedor digital, checkout com pagamento/cupom/saldo e acompanhamento honesto.
- iFood Design System: separar linguagem visual/tokens agnosticos da implementacao de componentes por tecnologia.
- Shopify/Polaris: cards escaneaveis, cart/checkout simples e baixa friccao.
- Ionic: componentes mobile como tabs, cards, lists, sheet/modal, searchbar e native-feeling controls.
- Odoo: densidade operacional, formularios, historico e navegacao de sistemas de negocio.

## Extensao Canonica

Quando faltar algo:

1. prove o gap comparando projection/action atual, esta spec e Django/Penguin;
2. classifique como ja canonico, deve ser canonizado, detalhe efemero ou legado descartavel;
3. estenda a projection/action/service/capability no menor no canonico possivel;
4. adicione teste backend do contrato;
5. adicione teste da superficie contra endpoint nao canonico, payload errado ou regra local;
6. registre o gap/decisao no relatorio da superficie.

## Aceite Para Nova Superficie

- Todos os momentos desta spec mapeados para projections/actions ou gap canonizado/documentado.
- Build e smoke local.
- Testes de mutations: serializacao, CSRF/cookies quando aplicavel, idempotencia e refresh de projection.
- Guardrail de endpoint allowlist: nada fora de `/api/v1/storefront/*`, `/api/v1/auth/*`, `/api/v1/cart/*`, `/api/v1/checkout/`, `/api/v1/account/*`, `/api/v1/tracking/*`, `/api/v1/payment/*`, `/api/v1/orders/*`, `/api/v1/geocode/reverse`.
- Guardrail de regra local: proibido derivar status operacional, total, estoque, auth requirement, payment gate, cancel permission ou status de pedido.
- Browser QA mobile e desktop cobrindo home, menu, PDP, carrinho, login OTP, checkout, pagamento, tracking, conta/historico.
- Staging valida rotas publicas esperadas sem quebrar superficies existentes.
