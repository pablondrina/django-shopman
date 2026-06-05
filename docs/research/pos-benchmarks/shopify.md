# Shopify POS — Dossiê de Especialista

> **Estado (2026-06-05):** código/docs ✅ · tela de venda PDV v11 (preview do Smart Grid editor) ✅
> · loja online Horizon (PDP, cart drawer) ✅ · **checkout web one-page preenchido ao vivo, com
> frete recalculando em tempo real** ✅. Trial `acrhyn-zr`, Pro/BR. **Falta só:** fluxo transacional
> do **app PDV nativo** (checkout/pagamento em ação) → screenshots do iPad do Pablo; e tour mais
> fundo do backoffice/ecossistema (Settings>Users PIN, Discounts, Payments, Cash). Ver abaixo.

Benchmark **#1**. O que queremos dele: **estado-da-arte de fluidez de checkout** (redesign v11.0,
fev/2026) e o vocabulário de UI de um PDV maduro.

## Disponibilidade & planos (BR)
- Disponível no Brasil. Plano **Básico** → Shopify PDV grátis (vendas ocasionais, pop-up/evento).
- **Shopify PDV Pro** US$ 89/mês/loja (US$ 79 anual): relatórios detalhados, análises,
  permissões e contas de equipe.
- Hardware: parceria **Verifone** (Victa Mobile all-in-one, 2026); POS Hub (periféricos via USB
  com monitoramento, elimina desconexão Bluetooth).

## Arquitetura de UI (de código aberto + docs de dev)

### Modelo de extensão = mapa das zonas da tela
As **POS UI extensions** revelam como a tela do PDV é composta. 3 tipos de ponto de extensão:

- **Tile** (`s-tile`) — blocos clicáveis no **Smart Grid** (tela inicial). Mostram status,
  ações rápidas, iniciam fluxos.
- **Action** — `menu item` (botão nos menus nativos de uma tela) ou `modal` (tela cheia p/
  fluxos multi-etapa, formulários, processos).
- **Block** (`s-pos-block`) — inline dentro de telas nativas (métricas, instruções, conteúdo
  de recibo).

### Stack técnico
- **Web components** renderizados com **Preact + remote-dom** (lib cross-plataforma da Shopify).
- Objeto global **`shopify`** centraliza: Storage (persistência entre sessões), Toast, Action
  (`shopify.action.presentModal()`), contexto (`shopify.customer.id`, `shopify.product.id`).
- **Offline-first** (`runs_offline = true`): APIs offline cobrem Storage, Locale, Toast,
  Connectivity, Device, **Scanner**, Navigation, Action, **PinPad**, **Cash Drawer**, Camera.
  → PDV de verdade não depende de rede; primitivas de hardware são first-class.
- Config por extensão em `shopify.extension.toml` (API version, target → módulo TS/JS).

### Catálogo de componentes (Polaris web — o vocabulário de UI)
Polaris é **open source** (GitHub `Shopify/polaris`), web components, "menor e mais rápido" que a
versão React anterior, framework-agnóstico.

- **Layout:** `Stack` (h/v), `Box`, `Section`, `Page`, `Tabs`
- **Ação:** `Button`, `Clickable`, `Link`, `Tile`
- **Form:** text/email/number, `ChoiceList`, `Switch`, date/time, `TextArea` (validação +
  formatação otimizadas p/ toque)
- **Status:** `Badge` (estados de pedido/comércio), `Banner`, `Modal`, `Spinner`
- **Mídia:** `Image`, `Icon` (catálogo padronizado do POS), `Embed` (conteúdo imprimível)

## Redesign v11.0 (o coração do benchmark de fluidez)

- **Carrinho:** reescrito p/ velocidade. **Multi-select** (aplica mudança a 1 ou vários itens de
  uma vez); ações abrem em **painel lateral** mantendo o carrinho sempre visível.
- **Checkout:** ancorado no carrinho, **"fluxo único contínuo"** — transições de tela trocadas
  por animações on-page (−centenas de ms/passo). Alvos de toque maiores p/ método de pagamento;
  **numpad inline** p/ dinheiro.
- **Cliente:** adicionar cliente é "uma das ações mais comuns e sensíveis a tempo" — busca
  prioriza nome/email/telefone; **criar cliente inline**.
- **Busca global:** mostra o texto exato que casou (SKU/barcode) no próprio resultado, sem abrir
  detalhe.
- **Customer-facing display:** brand theming (vídeo em idle, cores da marca no checkout, tela de
  PIN customizada).
- **Navegação:** barra vertical com funções críticas (registro, lock, conectividade) a 1 toque,
  liberando espaço pro Smart Grid.
- Outros: transferências de inventário nativas no PDV (pick/pack/receive c/ scanner); permissão
  granular "View Customer Details".

Princípio-mãe declarado: **"excelente experiência do cliente nasce de excelente experiência do
staff."**

## Leituras pro nosso UI Thing (hipóteses a validar na passada ao vivo)

- `s-tile` / Smart Grid **valida** nossa grade de produtos image-forward (Zona 1 do shell).
- "Carrinho sempre visível + ações em painel lateral" **tensiona** com nosso checkout 3-zonas
  Odoo-fiel (full-width dedicado). Decisão de design a tomar: Shopify mantém carrinho on-screen o
  tempo todo; Odoo separa em workspace. Qual serve melhor o operador de balcão?
- **Numpad inline** p/ dinheiro: já temos (`PosNumpad`). Convergente.
- **Multi-select de linhas** no carrinho: **não temos** e é forte (descontar/remover vários de
  uma vez).
- Offline-first com PinPad/Cash Drawer como primitivas: nosso modelo tem PIN (doorman) + caixa
  (CashRegister) — comparar ergonomia.

## Passada ao vivo — tela de venda v11 (Smart Grid editor preview, 2026-06-04)

O **Smart Grid editor** do admin (`.../point-of-sale-channel/editor`) renderiza um **preview fiel
da tela de venda do PDV** — então a anatomia v11 foi mapeada via navegador, mesmo o app sendo
nativo. Tema escuro, formato tablet landscape. Composição (painel esquerdo do editor): o PDV é
montado de **Smart grid pages** (N páginas, templates trocáveis) + **Lock screen** + **Checkout**,
cada um seção configurável.

**Anatomia da tela (3 colunas):**
- **Rail vertical de navegação (extrema esquerda, estreito, só ícones):** topo = Home, Pedidos,
  Produtos, Cliente, Mais (`...`); base = ícone de loja/PDV, Conectividade (broadcast), **Lock
  (cadeado)**. Funções críticas a 1 toque, ocupando o mínimo de largura.
- **Coluna central (Smart Grid):** busca **full-width** no topo (com ícone de scan à direita);
  abaixo, grade de **tiles** — defaults "Add custom sale" e "Apply discount". Tiles misturam
  AÇÕES e (configurável) produtos/coleções. Paginação por **dots** no rodapé central (swipe entre
  páginas de grid).
- **Coluna direita (Cart, SEMPRE visível):** header "Cart" + overflow (`...`) + limpar (lixeira);
  link **"Add customer"**; linhas (thumb + nome + variante + preço); **Subtotal** (expansível ⌄) +
  **Taxes**; e **CTA primário grande "Checkout R$XX,XX"** ancorado no rodapé (azul, full-width).

**Fluxo implícito:** construir carrinho com cart-rail sempre à vista → tocar **Checkout** → tela
de checkout/pagamento dedicada (a "single continuous flow" do v11; não capturada ao vivo — app
nativo). Cart-rail durante a montagem ≠ checkout dedicado no pagamento.

**Comparação direta com nosso `app.vue` / shell atual:**
| Aspecto | Shopify POS v11 | Nosso POS (UI Thing) |
|---|---|---|
| Carrinho | Rail DIREITO sempre visível | Ticket ESQUERDO (invertido, Odoo-fiel) |
| Checkout | CTA no carrinho → tela dedicada | Workspace 3-zonas dedicado (matou gaveta 420px) |
| Nav de funções | Rail vertical de ícones (lock/conectividade/board) | Botões no header (lock/caixa/terminal) |
| Grid | Tiles de AÇÃO + produto na mesma grade, paginado | Grade só de produtos + rail de categorias |
| Lock screen | Seção first-class | PosLockScreen first-class ✅ |
| Busca | Full-width topo, com scan | F3/busca ✅ |

**Decisões de design que isso levanta (pra co-revisar com Pablo):**
1. **Rail vertical de ícones** (lock/conectividade/caixa/board) — padrão limpo que NÃO temos;
   hoje empilhamos no header. Vale considerar.
2. **Tiles de ação na grade** (custom sale, desconto) lado a lado com produtos — hoje nossas ações
   vivem em botões/header. Misturar pode dar agilidade de balcão.
3. **Cart à direita (Shopify) vs ticket à esquerda (nosso, Odoo)** — tensão real entre os dois
   benchmarks #1 e #4. Decisão de layout a tomar deliberadamente.

## Loja online + checkout (tela a tela ao vivo, 2026-06-04)

Trial com 1 produto publicado ("Produto Teste Benchmark", R$25). Tema **Horizon** (flagship
Shopify 2025). Percorrido PDP → cart drawer → estrutura de checkout.

**PDP (Horizon):** announcement bar ("Welcome to our store"); header minimal (logo, nav
Home/Catalog/Contact, ícones busca/conta/sacola); **título enorme**, preço, **stepper de qtd**
(− 1 +), **"Add to cart"** (preto, ícone sacola); **checkout acelerado** abaixo — "Pay with
PayPal" + "More payment options". Muito whitespace, tipografia grande, sóbria.

**Cart drawer** (slide-in overlay à direita, NÃO página — preserva contexto): "Cart N" + fechar;
linha (nome, preço, stepper, lixeira); **"Discount +"** colapsável; **Estimated total**; nota
"Duties and taxes included. Shipping is calculated at checkout."; CTA **Check out** (preto) +
**PayPal** express.

**Checkout — one-page (via Checkout Editor; preview ao vivo + árvore de seções):**
Estrutura (ordem na página, scroll único): **Header** (Logo, Cart link) → **Express checkout** →
**Contact** (email ou telefone) → **Delivery** (endereço) → **Shipping method** (lista de opções)
→ **Payment** (payment option). Características:
- **Express checkout no TOPO** (PayPal/Shop Pay), antes de pedir qualquer dado → compra em 1 toque
  pra quem já tem conta. Divisor "OR" e então o fluxo manual.
- **Order summary colapsável** com **total sempre visível** (R$35,00) — sticky.
- **Contact**: email + link "Sign in" + opt-in de marketing.
- **Responsivo:** desktop = form à esquerda + summary sticky à direita (padrão Shopify); **mobile =
  coluna única** empilhada, order summary colapsável no topo. Confirmado ao vivo (toggle mobile).
- **Configurável via Checkout Editor** — mesma "editor paradigm" do POS Smart Grid (arrastar
  seções, brand theming, app blocks). Surfaces config-driven.

**Leituras pro nosso storefront/checkout:**
- **One-page checkout** (não wizard multi-step) é a aposta de fluidez do #1. Comparar com nosso
  storefront checkout.
- **Express checkout antes de pedir dado** — padrão forte de conversão. (No nosso caso: PIX em 1
  toque? handoff WhatsApp? — ver Take.app, benchmark #3.)
- **Order summary colapsável + total sempre visível** — replicável já.
- **Cart como drawer overlay** (não navega pra página) — mantém o cliente no contexto.
- **Editor paradigm repetida** (Smart Grid + Checkout Editor) = superfícies montadas de seções
  configuráveis → ressoa com nossa arquitetura **projection-driven**.

### Checkout real preenchido AO VIVO (2026-06-05, password desabilitado c/ OK do Pablo)
Percorrido o checkout real preenchendo dados de teste (parei ANTES de "Pay with PayPal" — sem
finalizar compra). Layout **2 colunas**: form à esquerda + **order summary sticky à direita**.
Sequência numa **página única** (sem steps), com **total recalculando ao vivo**:
- **Express checkout** (PayPal) no topo → "OR" → **Contact** (email + Sign in + opt-in).
- **Delivery**: Country=Brazil → **First/Last name** → **CEP (Postal code) com ícone de lookup**
  (CEP-first, autopreenche endereço — **igual ao nosso ADDRESS-UX-PLAN iFood-style**) → Address →
  Apartment (opcional) → City | State.
- **Cálculo de frete EM TEMPO REAL:** ao completar o endereço, o summary mudou de "Shipping:
  Enter shipping address" → **Shipping R$22,00**, e o Total saltou R$25 → **R$47,00** sem reload,
  sem botão. Esse feedback imediato é o núcleo da "fluidez".
- **Payment**: "All transactions are secure and encrypted." + método (só PayPal apareceu — trial
  sem gateway de cartão; "You'll be redirected to PayPal").
- **Billing address**: radio "Same as shipping address" (default) / "Use a different billing".
- **Additional information**: campo **CPF/CNPJ** (localização fiscal BR).
- CTA final "Pay with PayPal".

**Localização BR de série** (relevante: nosso mercado é o mesmo): CEP-lookup, CPF/CNPJ, moeda R$,
estados BR. Sai pronto — não é customização.

**Lições pro nosso checkout (storefront E POS):**
1. **Recalcular total ao vivo conforme o cliente preenche** (frete no address-complete) — feedback
   imediato > "calcular no fim". 
2. **CEP-first com autopreenchimento** valida nosso ADDRESS-UX-PLAN — Shopify faz exatamente isso.
3. **Order summary sticky sempre visível** com a linha Shipping mudando de placeholder→valor.
4. **Uma página, reveal progressivo** (não wizard) — o address-complete destrava payment na mesma
   tela.

**Nota de estado:** password protection da loja foi DESABILITADO (com OK do Pablo) p/ esta passada;
produto teste "Produto Teste Benchmark" criado. Ambos reversíveis (re-ligar password + apagar
produto) quando quiser. Nenhum pedido/pagamento real foi feito.

## DEEP DIVE backoffice (2026-06-05) — "explore ao máximo"

### ⭐ Roles & permissões (Settings › Users › Roles) — o achado mais relevante pro nosso Core
Shopify tem **gestão unificada de usuário + roles + segurança** (valida nosso doorman). Roles têm
**categoria**: Organization / **Point of Sale** / Store. Roles POS prontas (ex.: **Cashier**).
- A role tem `Grant manager approval` (no nível da role): **"Allows staff to approve other staff
  actions by entering their PIN."** = nosso manager-approval-via-PIN.
- **As permissões são granulares, agrupadas por domínio** (Checkout 1/4, Discounts 1/2, Orders
  0/12, Customers 3/8, Inventory, Apps, Analytics, Products…), cada uma com checkbox de concessão.
- **⭐ REFINAMENTO-CHAVE:** cada permissão de AÇÃO tem um **toggle `Manager approval` PRÓPRIO**.
  Exemplos (Checkout): *Add custom sales · Ship to customer · Edit taxes · Accept offline
  payments*. (Discounts): *Apply custom discounts · Apply discount codes*. (Orders): *Return and
  exchange orders*. Permissões de ADMIN (ex.: *Manage orders at all locations*) NÃO têm o toggle
  (são grant/deny puro).
> **Implicação pro nosso backstage:** em vez dos **4 gates hardcoded**, modelar manager-approval
> como **flag por-permissão** — `permission = {granted: bool, requires_manager_approval: bool}`.
> Qualquer ação sensível pode exigir PIN de gerente por config, não só 4 fixas. Mais flexível e é
> o que o líder de mercado faz. Conversar com Pablo (estende a matriz anti-fraude). Ver
> [[project_pos_uithing_redesign_goal]] (manager_approval / 4 gates).

### Discounts (motor) — padrão de e-commerce
Tipos: amount-off-products / amount-off-order / buy-X-get-Y / free-shipping. Método: **código** vs
**automático**. Valor: % ou fixo. Escopo: coleções/produtos/pedido. Condições: elegibilidade de
cliente, **mínimo de compra**, **limites de uso**, **combinação** com outros, **agendamento**
(active dates). Nada novo conceitualmente vs. nosso modifier/discount.

### Shipping & delivery (fulfillment) — VERIFICADO entrando nas telas (2026-06-05)
**Shipping profiles** (zonas/rates por produto/local) + estimated delivery dates + packages +
carrier accounts + **Delivery customizations** (esconder/reordenar/renomear opções no checkout) +
**Custom order fulfillment**. **Additional delivery methods: Local delivery** e **Pickup in
store** (off por padrão) = mapeiam nossos fulfillment types (delivery/pickup).
- **Local delivery (observado, não inferido):** configurado **POR LOCALIZAÇÃO** ("Your locations" →
  clicar no endereço da loja, status "Doesn't offer delivery" → ligar `Location status`). Área por
  **raio (km/mi)** em **zonas** ("Up to 10km"); **cada zona** tem **pedido mínimo** + **preço**
  (Free); **múltiplas zonas** ("Add zone"). + integração com apps de rota/entrega.
- **Pickup in store (observado):** também **POR LOCALIZAÇÃO** (selecionar local → habilitar pickup;
  suporta store transfers / pickup mesmo sem o item no local). Detalhe (prep time/instruções) ao
  habilitar.
> Confirma o modelo per-location de fulfillment. Mapeia nosso DeliveryZone (storefront) + pickup
> slots. (Correção de honestidade: na 1ª passada eu só vi os dois "Off" na lista e inferi; aqui
> entrei e confirmei — Pablo cobrou com razão.)

### Storefront homepage (Horizon, section-based)
Default: announcement bar + **hero** ("Browse our latest products" + Shop all) + **featured
products**. Tema montado de **seções** (hero, featured collection, etc.) — config-driven, mesma
"editor paradigm". Storefront UX agora coberto ponta a ponta: home + PDP + cart drawer + checkout.

## DEEP DIVE 2 — varredura exaustiva entrando em cada área (2026-06-05)
Pablo: "extraia o máximo agora, entre em TODOS os links pertinentes". Entrei de fato em cada tela.

- **Produto (modelo completo):** título · descrição rich-text · preço/Compare-at/Unit-price/**Cost
  per item**/Charge-tax · **Inventory** (track on/off, SKU, barcode) · **Shipping** (physical
  toggle, Package, **Product weight**, Country of origin, HS Code) · **Variants** = opções (nome
  ex."Size" + valores ex."Medium", até 3 opções → matriz de variantes c/ preço/SKU/estoque/imagem
  por variante) · **Search engine listing** (handle URL + meta) · Theme template · Tags.
- **Collections:** **Manual** vs **Smart/automática** (produtos que batem nas condições entram
  sozinhos) · publishing **por canal** (Online Store / Point of Sale) · imagem · SEO.
- **Draft order (Orders › Create order):** construtor de pedido no admin = POS-adjacente. **Add
  product** / **Add custom item** (linha arbitrária) · Payment (Subtotal/**Add discount**/**Add
  shipping or delivery**/Estimated tax/Total) · Customer (busca) · **Markets/Currency** · Notes.
  Mapeia nosso order/session + cart building.
- **Theme editor (Horizon) — storefront é SECTION-BASED:** Header(Announcement bar, Header) +
  Template(**Hero**, **Featured collection**) + Footer; cada seção tem **blocos** internos +
  "Add section". Catálogo de seções por categoria (**Banners:** Hero / Hero bottom / Marquee /
  Large logo / Layered slideshow…) + **"Generate" (IA gera seção)** + aba **Apps**. Mesma "editor
  paradigm" do Smart Grid/Checkout → reforça nosso **projection/config-driven**.
- **Payments:** payment providers ("Choose a provider", 3rd-party) + supported methods (PayPal
  2%, manual methods). 
- **Notifications (taxonomia de lifecycle):** **Customer notifications** agrupadas por fase —
  *Order processing* (Order confirmation, Draft order invoice, **Shipping confirmation**), *Local
  pick up* (**Ready for local pickup**)… + **Staff notifications** + "Customize email templates".
  Mapeia nossos directives/handlers de notificação por evento. "Ready for local pickup" = nossa
  notificação de retirada pronta.
- **Customer accounts:** Sign-in links (header/checkout) · Configurations (Customize) ·
  **Authentication** (métodos de sign-in / account access) — moderno é passwordless (email code) =
  ressoa com nosso OTP/doorman.
- **Shipping local delivery/pickup:** ver §"Shipping & delivery" acima (verificado entrando — por
  localização, zonas de raio com min+taxa).

> **Padrão transversal confirmado:** TUDO no Shopify é **superfície montada de seções/permissões
> configuráveis** (Smart Grid · Checkout editor · Theme sections · Roles granulares · Notification
> templates). É a mesma filosofia da nossa arquitetura **projection-driven** — validação forte.

## Ainda pendente da passada ao vivo
- [ ] **Fluxo transacional do app nativo** (checkout contínuo em ação, pagamento, numpad inline,
  split tender, multi-select de linha, customer-facing display) → **screenshots do iPad do Pablo**.
- [ ] **Backoffice/ecossistema** ao vivo: Products, Orders, Discounts, Customers, Settings>Users
  (gestão unificada de PIN), Cash tracking, Payment types, Receipts.
- [ ] **Loja online + checkout web** (storefront) — fluidez de compra do cliente. (Trial hoje só tem
  "Example product"; pra walkthrough de checkout real convém ter 1 produto publicado.)
