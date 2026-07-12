# Síntese dos Benchmarks → Direção de Redesign

> Cruzamento dos 4 benchmarks ([shopify](shopify.md) · [stores](stores.md) · [take-app](take-app.md)
> · Odoo pendente) em **decisões de design acionáveis** pro redesign do POS (UI Thing/Nuxt) e do
> storefront. Escrito 2026-06-05. Storefront = bem observado ao vivo; **PDV-frontend = anatomia
> (apps nativos), confiança menor** até explorar Odoo demo + screenshots de iPad.

---

## 1. As teses convergentes (onde os benchmarks concordam)

1. **Ecossistema unificado num dashboard** (STORES + Take.app): POS + loja online + mobile order +
   reservas, uma conta. É a direção estratégica que o Pablo escolheu — **passa na frente do Odoo**
   (desktop-first/ERP). Nosso Shopman Suite já é isso por arquitetura (shop orquestra canais).
2. **Checkout = fluidez, não formulário** (Shopify): one-page, reveal progressivo, **total
   recalculando ao vivo**, express checkout antes de pedir dado.
3. **A transação pode morar na conversa** (Take.app): WhatsApp-first como MODO de checkout
   (pedido-como-mensagem), não só notificação.
4. **PDV nativo é o padrão** (Shopify, STORES, Take.app = app iOS/Android; só Odoo é web). Nosso
   **PDV web/Nuxt é escolha contracorrente** — decisão consciente a defender (ver §4).
5. **O backoffice modela as mesmas realidades do nosso Core** (Take.app): confirmação otimista,
   availability-first, draft-até-pago, sinal. Não estamos inventando — estamos alinhados aos líderes.

---

## 2. Decisões de design por superfície

### 2.1 PDV (frontend) — confiança MÉDIA (anatomia, falta feel ao vivo)
| Padrão observado | Fonte | Decisão pro nosso PDV |
|---|---|---|
| Cart **sempre visível à direita** + CTA Checkout grande | Shopify v11 | ⚖️ **TENSÃO** com nosso ticket-à-esquerda Odoo-fiel. Decidir (§4). |
| **Rail vertical de ícones** (home/pedidos/cliente; base lock/conectividade/caixa) | Shopify v11 | ✅ Considerar adotar — hoje empilhamos no header. Limpa e escala. |
| **Tiles de AÇÃO + produto na mesma grade** (venda avulsa, desconto) | Shopify Smart Grid | ✅ Avaliar misturar ações na grade — agilidade de balcão. |
| **Multi-select de linhas** (aplicar a vários itens) | Shopify v11 | ➕ Não temos. Forte pra desconto/remoção em lote. |
| Numpad inline p/ dinheiro | Shopify | ✅ Já temos (`PosNumpad`). |
| Lock screen first-class | Shopify | ✅ Já temos (`PosLockScreen` + PIN doorman). |
| Composição por **seções configuráveis** (Smart Grid + Checkout editor) | Shopify | ✅ Ressoa com nosso **projection-driven**. Reforça a arquitetura. |
| Densidade/ergonomia de balcão, gestão de caixa/turno | Odoo (pendente) | ⏳ Benchmark principal de densidade — explorar demo. |

### 2.2 Storefront (loja online) — confiança ALTA (observado ao vivo)
| Padrão | Fonte | Decisão |
|---|---|---|
| **One-page checkout** + reveal progressivo + **total recalcula ao vivo** (frete no address-complete) | Shopify | ✅ Alvo. Comparar com nosso checkout atual. Feedback imediato > calcular no fim. |
| **Express checkout antes de pedir dado** | Shopify | ✅ Avaliar (PIX 1-toque? handoff WhatsApp?). |
| Endereço: **Maps-first + "usar localização atual" (iFood)**; CEP só fallback | nosso [[project_address_ux_spec]] | ✅ JÁ é nossa spec. ⚠️ Shopify é CEP-first = **contra-exemplo, não copiar**. |
| **Cart drawer overlay** (não navega pra página) | Shopify + Take.app | ✅ Mantém contexto. |
| **Barra de carrinho sticky no rodapé** (mobile) | Take.app | ✅ CTA persistente. (Cf. nosso bug de badge — [[project_bottom_nav_cart_badge_pending]].) |
| **Nudge de frete grátis com progress bar** | Take.app | ✅ Conversão. Replicável. |
| **Cross-sell na PDP "Talvez você também goste"** | Take.app | ✅ = nossa feature [[project_pdp_veja_tambem_pending]] (copy já atualizada). |
| **PWA add-to-home**, **"Siga"** (re-engajamento), **círculos de categoria** (stories) | Take.app | ✅ Backlog de descoberta/retenção. |
| Order summary sticky com total sempre visível | Shopify | ✅ Replicável. |

### 2.3 WhatsApp-first (modo de checkout) — confiança ALTA
- **Pedido-como-mensagem** + opção **"pular checkout → carrinho direto pro WhatsApp"** + **canal
  plugável** (WhatsApp/SMS/Messenger/Telegram). Fonte: Take.app.
- Alinha com [[feedback_whatsapp_via_manychat]] (nosso WhatsApp via ManyChat). Take.app dá o
  **padrão de UX do handoff** — vale desenhar nosso "finalizar no WhatsApp" como modo, não só aviso.

### 2.4 Backoffice / ecossistema — confiança ALTA
- **Gestão unificada de usuário+PIN+permissões** (Shopify Settings›Users) **valida nosso modelo
  doorman** (PinCredential + operador, reusável POS/KDS/gestor).
- **Dashboard multicanal único** (STORES/Take.app: Site/WhatsApp/Insta/Google/POS + reservas) =
  direção estratégica.
- **Toggles de pagamento = nosso Core** (Take.app): "confirmar valores/disponibilidade antes de
  cobrar" (availability-first), "auto-confirmar quando pago" (confirmação otimista), draft-até-pago,
  entrada/sinal. Validação externa direta.
- **Onboarding por trilha/canal** (STORES: checklist por POS/loja/mobile order) — padrão de ativação
  a emular no backstage.

### 2.5 Operação de restaurante — confiança ALTA
- **Mobile order eat-in(mesa)/takeout → KDS** (STORES) **valida nossa Fase 5** (comanda + handoff de
  cozinha por `session_key`/`fired_lines`). É como o líder JP de restaurante opera. Eat-in/takeout =
  nosso `fulfillment_type`.

---

## 3. O que cada benchmark contribui (resumo de uma linha)
- **Shopify (#1):** estado-da-arte de **fluidez** (checkout one-page, recálculo ao vivo) + vocabulário
  de UI maduro (Smart Grid, rail, multi-select) + Polaris/extensions como referência de arquitetura.
- **STORES (#2):** **ecossistema unificado** + **operação de restaurante** (mesa/handy/KDS) que
  espelha nosso domínio.
- **Take.app (#3):** **WhatsApp-first como modo** + backoffice cujos toggles são o nosso Core +
  padrões de storefront (nudge, cross-sell, sticky cart, PWA).
- **Odoo (#4, pendente):** **densidade/ergonomia de balcão** e gestão de caixa — o único PDV web
  explorável ao vivo.

---

## 4. Tensões / decisões abertas (precisam do Pablo, lado a lado)
1. **Layout do PDV: cart-à-direita (Shopify) vs ticket-à-esquerda (Odoo, nosso atual).** Os dois
   benchmarks #1 e #4 puxam em direções opostas. É a decisão de shell mais importante.
2. **PDV web/Nuxt vs nativo.** 3 de 4 são nativos (hardware/scanner/offline). Manter web é escolha —
   precisa defesa consciente dos trade-offs (PWA? capacidades de hardware via web?).
3. **Quais padrões de storefront priorizar** primeiro (checkout one-page? express? nudges?).
4. **WhatsApp-first como modo de checkout** — quanto investir vs. o checkout próprio.

---

## 5. Pendências de exploração (deep-dive depois — Pablo: "consolidar já, deep-dive depois")
- ~~**Odoo POS** (demo web) — preenche o buraco de PDV-frontend ao vivo. **Maior prioridade do que falta.**~~
  ✅ **FEITO 2026-06-08** — deep-dive ao vivo da tela de pagamento em [odoo.md](odoo.md). Validou a
  direção "Conta + Instrumento" (herói = total estável + numpad universal + linhas de tender). Resta
  só a tela de **fechamento de caixa** (densidade de turno) pra um deep-dive de Caixa futuro.
- **Screenshots de iPad** (Shopify/STORES PDV nativo em ação) — Pablo manda quando puder.
- **Shopify deep backoffice** — descontos, Settings›Users (PIN/permissões), entrega, analytics.
- **STORES** — popular itens + ver mobile order/KDS config (fricção JP).
- **Take.app Conversas** (inbox WhatsApp) — precisa WhatsApp conectado.

---

## 6. Próximo movimento sugerido pós-síntese
Com os deep-dives feitos (sobretudo **Odoo PDV**), sentar **lado a lado com o Pablo** pra cravar as
4 decisões abertas do §4 — natureza visual/iterativa (ver [[project_pos_uithing_redesign_goal]],
seção "redesign de shell"). A síntese é o input; as decisões do §4 destravam a implementação.
