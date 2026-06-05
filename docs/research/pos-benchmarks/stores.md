# STORES (ストアーズ) — Dossiê de Especialista

> **Estado (2026-06-05):** acesso ao **dashboard real** conquistado (Pablo completou o cadastro JP
> com dados placeholder, guiado campo a campo — eu não preenchi/submeti, barreira de criação de
> conta). Conta **nova e vazia** → gerenciamento profundo (pedidos/produtos reais) não explorável,
> mas a **estrutura do ecossistema** foi mapeada na home de onboarding. JP-only (dashboard.stores.app).

Benchmark **#2**. O que queremos dele: **ecossistema unificado** (POS + loja + reserva + mobile
order num dashboard) e a **operação de restaurante** (mesa/handy/KDS) — o mais próximo do nosso
domínio entre os benchmarks.

## O ecossistema unificado (confirmado na home)
A home de onboarding (`dashboard.stores.app`) organiza tudo em **3 trilhas de setup** sob uma conta
única — a prova da tese "um dashboard, vários canais":

### 1. レジ (Reji = Caixa/PDV)
Setup: **アプリをダウンロード** (baixar o app — **PDV é app NATIVO**) · 決済手段の準備 (preparar
meios de pagamento) · 商品データの登録 (cadastrar produtos) · 周辺機器の準備 (preparar periféricos
— gaveta, scanner) · テスト会計 (venda de teste).

### 2. ネットショップ (Net Shop = Loja online)
Setup: 送料の設定 (frete) · 商品データの登録 (produtos) · 決済手段の設定 (pagamento) · ショップの
デザイン (design da loja) · ショップを公開 (publicar). → **Construtor de e-commerce convencional**
(diferente do WhatsApp-first do Take.app, #3).

### 3. モバイルオーダー (Mobile Order) — o mais relevante pra nós
Setup: **提供方法の設定（イートイン / テイクアウト）** (método de entrega: **comer no local / viagem**)
· クレジットカード決済の利用申請 (habilitar cartão) · アイテムの作成 (criar itens) · カタログの作成
(catálogo no site de pedido) · **キッチンディスプレイの設定 (configurar KDS)**.
> **Isto é o mesa+KDS que já construímos (Fase 5).** STORES modela: cliente pede pelo mobile order
> (na mesa/eat-in ou takeout) → pedido cai na **Kitchen Display** da cozinha. Mesma cadeia
> comanda→handoff de cozinha do nosso domínio. Eat-in (mesa) vs takeout = nosso fulfillment_type.
> Pela pesquisa de docs (JP), o restaurante também tem **table order, função "handy"** (garçom tira
> pedido e sincroniza) e conta por mesa num tablet — coerente com este setup.

Há ainda **予約 / Table Booking** (reservas) como produto do ecossistema (visto na pesquisa de docs
e no paralelo com o Take.app).

## Achados estruturais
- **PDV nativo** (app iOS/iPad) — confirma o padrão cross-benchmark: **Shopify, STORES e Take.app
  têm POS nativo; só o Odoo é web.** Nosso POS web/Nuxt é contracorrente (trade-off a discutir).
- **Onboarding por trilhas** (POS / loja / mobile order) com checklist de passos por canal — UX de
  ativação clara. Widget **STORES Play** (assistente de IA) no canto.
- Plano: oferta "Standard 1 mês grátis"; usamos o tier de entrada.

## Leituras pro nosso projeto
1. **Ecossistema unificado num dashboard** (POS + loja + mobile order + reserva) = a direção
   estratégica que o Pablo quer (passa na frente do Odoo). STORES e Take.app convergem nisso.
2. **Mobile order eat-in/takeout → KDS** valida nossa arquitetura comanda + handoff de cozinha
   (Fase 5, `session_key`/`fired_lines`). Não é teoria — é como o líder JP de restaurante opera.
3. **Onboarding por trilha/canal** (checklist por produto) é um padrão de ativação que podemos
   emular no backstage (setup guiado por superfície).

## DEEP DIVE (2026-06-05) — modelagem de item (dashboard.stores.jp/items)
Alcancei o form de criação de item da loja online (a conta nova destrava o cadastro de item; KDS
ao vivo / app PDV seguem gated). **O dashboard é por-produto** (`dashboard.stores.jp` = loja
online; `dashboard.stores.app` = hub unificado). Dica do form confirma o **catálogo unificado**:
um item se cadastra p/ **loja online / レジ(PDV) / mobile order** (3 canais, mesma ficha).

**Tipos de item:** mercadoria (físico) · digital · 定期便/assinatura · bilhete eletrônico (e-ticket
p/ eventos) · cadastro em lote.

**Modelo do item (mercadoria):** imagem (até 15) · nome (obrigatório) · descrição · **taxa de
imposto** · **preço com imposto INCLUÍDO** (convenção JP) · **desconto por item** (%/valor) ·
**custo** · **SKU** (品番) · **código de barras** (+ auto-gerar) · **Múltiplas variações** (toggle)
· **estoque por variação** + "Ilimitado" · envio nacional (frete) · **público/privado**.

**⭐ Achado de modelagem:** toggle por-item **"Exibido na tela da cozinha ao fazer o pedido pelo
caixa"** = **flag de KDS no nível do ITEM**. STORES marca explicitamente quais itens vão pro
Kitchen Display quando vendidos no PDV.
> **Contraste com o nosso:** roteamos KDS por **receita/coleção/estação** (craftsman + adapter KDS,
> mais poderoso — sabe a estação certa). O per-item toggle do STORES é mais simples/explícito.
> Vale ter em mente os dois modelos (flag simples vs roteamento inteligente) ao evoluir o KDS.
> (Cf. nossa Fase 5: `kds.fire_lines`, roteamento `_match_instances`.)

## Guia de setup oficial (faq.stores.jp, lido via browser — WebFetch deu 403)
Guia "初期設定" da **loja online** (ネットショップ), 5 passos: (1) abrir conta (id.stores.jp/signup
→ dashboard.stores.app); (2) **registro de item + config de frete** (preço por região de entrega);
(3) **aplicação de uso de pagamento** ("決済利用申請") — **análise leva ~4 dias úteis**; (4) design
da loja (fundo/layout); (5) **publicar** (aí fica comprável). Cada passo tem sub-artigo + vídeo.
> **Isto EXPLICA o gate:** cartão/pagamento exige **aplicação + ~4 dias úteis de revisão** — não
> forjável. Por isso a parte transacional ao vivo (checkout pago, KDS em ação) fica fora do nosso
> alcance nesta conta nova. Estrutura/modelagem nós já capturamos.

## DEEP DIVE 2 — seguindo o guia na prática, entrando em cada tela (2026-06-05)
Pablo: "siga o guia na prática, entre em cada link". Percorri a trilha ネットショップ no dashboard.

- **Frete (送料設定, /store/shipping):** por **método de envio** (cards: ポスト便/post · 宅配便/parcel
  · 普通郵便/regular mail · +追加) com **abas 日本/海外** (Japão/exterior); taxa por região por
  método; **por-item escolhe quais métodos** valem. (Padrão JP.)
- **Design da loja (ストアデザイン, /store_design):** "sem HTML/CSS". Dois caminhos — **かんたん設定**
  (fácil: escolher layout+estilo) ou **自分で設定** (manual) → leva a uma **galeria de TEMPLATES**
  responsivos (PC+mobile), "tema customizável no design editor depois". → **template-based** (tema
  pronto + customização), **contrasta com o section-based de tema único do Shopify**.
- **Pagamento (決済手段, /store/payment_method) — conjunto RICO de métodos locais JP:** コンビニ決済
  (loja de conveniência) · **atone / Paidy (あと払い)** (pague-depois) · PayPal · 銀行振込
  (transferência) · キャリア決済 (cobrança na operadora) · 楽天ペイ (Rakuten Pay) · PayPay. **Cartão
  de crédito GATED:** exige registro de **特商法** (Act on Specified Commercial Transactions —
  disclosure legal obrigatório de e-commerce JP) **+ 審査 (revisão de uso, ~4 dias úteis)**. ESSE é
  o gate que trava o transacional ao vivo.
  > **Leitura:** a amplitude de métodos de pagamento LOCAIS espelha a tese do Take.app ("100+
  > métodos locais"). Plataformas commerce empacotam os meios de pagamento do mercado-alvo. **Pra
  > nós (BR):** PIX, boleto, cartão, COD — o equivalente. (Cf. nosso payman/adapters.)
- **Publicar (公開):** passo final do guia — torna a loja comprável. (1 ação; não executei.)

Guia oficial tem sub-artigos por passo (item/frete/pagamento/design/publicar), cada um com vídeo.

## Pendente / limitações
- Conta **vazia** (recém-criada) → não dá pra ver pedidos/produtos/KDS reais em ação sem popular.
- **Verificação de identidade/banco japonês** provavelmente bloqueia uma conta 100% ativa (não
  forjável). Acesso atual = dashboard de onboarding + estrutura; transacional real fica limitado.
- Telas internas (商品 produtos, 注文 pedidos, KDS ao vivo, app de PDV nativo) → só com conta
  populada / screenshots / docs JP. Help center JP (`stores.jp/regi`) tem material com screenshots.
