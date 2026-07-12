# Confronto — Nossos Princípios × Benchmarks × Estado Atual (Etapa B)

> Iniciativa [[project_excellence_refactor_initiative]]. Cruza **nossos princípios de design** ×
> **melhores práticas dos benchmarks** ([Shopify](../research/pos-benchmarks/shopify.md) /
> [STORES](../research/pos-benchmarks/stores.md) / [Take.app](../research/pos-benchmarks/take-app.md)),
> ancorado no **Mapa do Core** ([00](00-core-capability-map.md)) e na **Auditoria** ([01](01-surface-audit.md)).
> Regra do confronto: **só o mais simples, robusto e elegante para o NOSSO caso prevalece** — com
> justificativa. Objetivo declarado: "recriar nosso próprio Shopify" usando o backend sólido.
> Não é proposta de arquitetura (isso é D); é a decisão de *o quê* cada superfície deve fazer.

## Arquitetura âncora (toda decisão abaixo cabe aqui)
**3 camadas, corte política/apresentação, superfície nunca toca o Core:**
- **Core** = domínio (intocado).
- **Orquestrador** = comandos + saga + **política** + **read-models de DADOS** (agnósticos de
  superfície, laden de política). Selo único.
- **Superfícies** = projeção de **apresentação** (consome dado+SurfaceActionProjection, renderiza).
  Shape puro, zero política, zero Core. Tipos: Storefront, PDV, Agentic (headless), Backoffice
  (Unfold canônico p/ gestão + dedicado p/ operacional).

---

## Parte 1 — Onde benchmarks e nossos princípios CONCORDAM (double-down, baixo risco)

Estes não são "decisões" — são confirmações de que nossa direção é a do mercado. Implementar com
confiança.

| Capacidade | Benchmark | Nosso princípio / alavanca Core | Veredito |
|---|---|---|---|
| **Superfícies montadas de blocos config-driven** | Shopify "editor paradigm" (Smart Grid, Checkout editor, Theme sections) | `ChannelConfig` + projections + `SurfaceActionProjection` | ✅ É a MESMA filosofia. Double-down: nossas superfícies = render de projections config-driven. |
| **Checkout = fluidez, não formulário** (one-page, reveal progressivo, **total recalcula ao vivo**) | Shopify v11 | availability-first + pricing-em-contexto (Core decide ao vivo) + projection-driven | ✅ Temos as alavancas (availability/pricing live + SSE push). Adotar. |
| **Endereço Maps-first + "usar localização atual"** | (Shopify é CEP-first = **contra-exemplo**) | [[project_address_ux_spec]] Google Places + geo + CEP fallback | ✅ Nosso princípio GANHA. Shopify CEP-first NÃO copiar. |
| **Confirmação otimista** (auto-confirma; timeout) | Take.app "confirmação automática quando pago"; Shopify confirmation modes | [[feedback_confirmacao_otimista]] + `ChannelConfig.confirmation` (immediate/auto_confirm/auto_cancel/manual + timeout) | ✅ Já é nosso, e config-driven. Validado externamente. |
| **Availability-first** (confirmar disponibilidade antes de cobrar) | Take.app "ignorar página de pagamento p/ confirmar valores/disponibilidade" | availability contract + planned holds + `demand_ok` | ✅ Nosso domínio é mais rico (planned/expected/D-1). Validado. |
| **Mobile-order eat-in/takeout → KDS** | STORES (mesa/handy/KDS) | comanda (`handle`) + Fase 5 (`kds.fire_lines`, `session_key`, fired_lines) | ✅ Já construído e mais robusto (roteamento por receita/coleção/estação vs flag por-item do STORES). |
| **Catálogo unificado por canal** | STORES (1 item → loja/PDV/mobile order) | Offerman `Listing`/`Channel` (preço+disponibilidade por canal) | ✅ Mesma ideia, já modelada. |
| **Ecossistema unificado num dashboard** | STORES + Take.app | Shop singleton + Channels + orquestrador (1 backend, N canais) | ✅ É a arquitetura. Direção estratégica confirmada (passa na frente do Odoo). |
| **Padrões de storefront de conversão** | Take.app (nudge frete-grátis, sticky cart, PWA, "Siga", category circles, cross-sell) | backlog ([[project_pdp_veja_tambem_pending]] cross-sell, etc.) + omotenashi | ✅ Adotar como features de superfície. Copy "Talvez você também goste". |
| **Gestão unificada de usuário+PIN+permissões** | Shopify Settings›Users | doorman PinCredential (User, surface-agnostic) + backstage operator | ✅ Já temos o modelo. Validado. |
| **Taxonomia de notificação por lifecycle** | Shopify (Order processing / Local pickup "Ready for pickup"…) | Directives + handlers + NotificationTemplate (editável) | ✅ Já modelado por evento. |

---

## Parte 2 — Onde há TENSÃO (decisões explícitas, com justificativa)

### D1 — Manager-approval: 4 gates fixos vs flag por-permissão
- **Benchmark (Shopify):** cada permissão de AÇÃO tem seu toggle `Manager approval` (add custom
  sale, edit taxes, apply discount, return…). Aprovação por PIN.
- **Nosso atual:** `validate_manager_approval` plugado em poucos gates; plano falava em "4 gates".
- **Core:** doorman PIN (verify_manager_pin) + ChannelConfig/RuleConfig (config por canal).
- **GANHA: o modelo por-permissão do Shopify.** Mais simples (uma regra, N permissões) e mais
  flexível que 4 gates hardcoded. **Justificativa:** o Core já tem PIN + config; modelar
  `requires_manager_approval` como flag por-permissão (em ChannelConfig/RuleConfig) é menos código e
  mais poder. Mata a "matriz anti-fraude" como caso particular.

### D2 — Layout do PDV: cart-à-direita (Shopify) vs ticket-à-esquerda (Odoo/nosso)
- **Tensão:** benchmarks #1 e #4 puxam oposto. Sem dado público de A/B (só convenção/ergonomia).
- **DECISÃO: adiar pra fase de Spec visual/shell do PDV** — é decisão de *apresentação*, não de
  arquitetura/contrato. **Justificativa:** com a arquitetura de 3 camadas, layout é trocável sem
  tocar dado/política. Resolver com a equipe Nelson (muscle-memory) quando desenharmos o shell.
  Não bloqueia specs.

### D3 — PDV web/Nuxt vs nativo (3 de 4 benchmarks são nativos)
- **Tensão:** Shopify/STORES/Take.app PDV = app nativo (hardware/scanner/offline). Nós = web/Nuxt.
- **DECISÃO: manter web/Nuxt.** **Justificativa:** impressão sem fricção no Ubuntu é viável
  (kiosk-printing / WebSerial+ESC-POS / ePOS-Print de rede); PWA dá app-like/offline-leve; web é
  multi-plataforma e alinha ao contrato projection+comando único (a mesma superfície serve PDV).
  Trade-off de hardware é gerenciável. (Verificar/prototipar impressão na fase de PDV.)

### D4 — WhatsApp-first: quanto investir como modo de checkout
- **Benchmark (Take.app):** pedido-como-mensagem / skip-checkout / canal plugável é o coração deles.
- **Nossa visão (Pablo):** Rodada 1 = ponte low-friction sem-login pra loja (`AccessLink`); Rodada 2
  = resolução in-chat (princípio binário: resolve tudo no chat OU leva pra web). Transaciona como
  cliente autenticado. ManyChat nos fluxos. Copy via Admin (`OmotenashiCopy`).
- **GANHA: a superfície agentic é HEADLESS = consumidor do MESMO contrato** projection+comando.
  Rodada 1 agora (ponte), Rodada 2 prevista (in-chat) — barata SE o contrato for uniforme.
  **Justificativa:** `conversation.build_order_conversation` + `remote_mutations` + `AccessLink` +
  `OmotenashiCopy` já existem. Não construir UI própria; renderizar projection como mensagem +
  emitir comando como o cliente. #4 (agente IA autônomo/ACP) = opcionalidade grátis, não feature.

### D5 — Unfold Admin × UI dedicada (parte do frankenstein)
- **Estado atual:** mix com incoerências (KDS em 2 casas, registro por reflexão).
- **DECISÃO (princípio):** por NATUREZA do trabalho — **gestão/config/CRUD → Unfold Admin canônico**
  (paga permissões/CRUD/segurança; é o **gold standard** já provado no `admin_console`);
  **operacional real-time bespoke → UI dedicada** (PDV, KDS); **cliente → storefront**; **agentic →
  headless**. **Unificador:** as 4 consomem o **MESMO contrato projection+comando** (inclusive
  páginas Admin custom, via Unfold Canonical Gate). **Justificativa:** é "usar os dois bem +
  integrar", com rigor — como o Shopify (admin gestão + PDV/checkout dedicados + agentic, um backend
  só). Reforça [[feedback_no_standalone_admin]].

### D6 — Design do storefront: section-based (Shopify) vs template-gallery (STORES)
- **Benchmark:** Shopify = seções config-driven (1 tema customizado por blocos); STORES = galeria de
  templates prontos.
- **GANHA: section-based config-driven**, alinhado ao nosso `ChannelConfig`/projections + branding do
  `Shop` (OKLCH/fontes/logo). **Justificativa:** mais poder + consistência com a filosofia
  config-driven; mas **sem** virar um theme-editor genérico de mercado — nosso storefront é **um**,
  branded (Nelson), omotenashi-first; "config-driven" aqui = seções/copy/branding editáveis, não um
  builder multi-tenant. Simplicidade pro nosso caso.

### D7 — Amplitude de pagamento local
- **Benchmark:** STORES (conveniência/Paidy/PayPay…) + Take.app (100+ métodos locais) = bundle do
  mercado-alvo.
- **Pra BR:** PIX + boleto + cartão + COD. **Core:** payman + adapters (efi/stripe) swappable.
- **GANHA: bundle BR via adapters** (PIX-first, omotenashi). Não perseguir "100+ métodos"; cobrir o
  que o mercado BR usa, config-driven por canal.

---

## Parte 3 — Confronto por superfície (o que cada pilar deve fazer)

### Storefront (loja online) — "fluidez Shopify + omotenashi nosso"
- **Adotar:** one-page checkout com **recálculo ao vivo** (frete/disponibilidade/preço via Core);
  express/atalho (PIX 1-toque? — avaliar); cart drawer + **sticky cart mobile**; nudge de frete
  grátis; cross-sell "Talvez você também goste" na PDP; PWA add-to-home; "Siga" (re-engajamento);
  category circles; order summary sticky com total sempre visível.
- **Nosso diferencial (manter/elevar):** **omotenashi-first** (copy acolhedor, acessibilidade,
  idosos, contraste); **Maps-first + localização atual** (≠ CEP-first); **availability UX acionável**
  ([[project_stock_ux_spec]] alerta 1-clique; planned-hold "Aguardando confirmação/Tudo pronto");
  **SEO como capítulo** ([[project_seo_chapter]]); timeouts transparentes ([[feedback_transparent_timeouts]]).
- **Conserto (do audit):** matar `cart.py::get_cart` e `product_cards` (apresentação consumindo
  read-model de DADO do orquestrador; zero re-política). Um shape de card só.

### PDV (operador) — "ergonomia de balcão + contrato limpo"
- **Adotar:** Smart-Grid-like (grade de produtos + tiles de AÇÃO juntos? — avaliar); **multi-select
  de linhas** (Shopify, novo p/ nós); rail vertical de funções (lock/caixa/board); numpad inline (já
  temos); customer-facing display (futuro).
- **Nosso (manter):** comanda/handle + move_lines (split/transfer/merge, preço congelado); fire-to-
  kitchen progressivo (Fase 5); manager-PIN; caixa cego; confirmação otimista.
- **Conserto (do audit):** PDV-HTMX para de montar HTML em f-string → consome o `SurfaceActionProjection`
  + API que já existem. Schema POS compartilhado (gerar tipos). Decisão D2/D3 valem aqui.

### Agentic / conversational — "headless, mesmo contrato"
- **Rodada 1:** ponte low-friction (`AccessLink` sem-login) carrinho/conversa → loja. Fluxos
  ManyChat. Copy via `OmotenashiCopy`.
- **Rodada 2 (prevista):** in-chat (disponibilidade/carrinho/pagamento/confirmação na conversa) —
  binário: resolve tudo OU leva pra web. Transaciona como cliente autenticado.
- **Núcleo:** `conversation` projection + `remote_mutations` + SurfaceActionProjection. **Nenhuma UI
  própria** — renderiza projection como mensagem, emite comando.

### Backoffice — "Unfold canônico + dedicado, um contrato" (D5)
- **Unfold Admin (gestão/config/CRUD/relatórios):** catálogo, ChannelConfig, RuleConfig, clientes
  (CRM/RFM/loyalty/insights — Guestman é rico), pagamentos, NotificationTemplate, OmotenashiCopy,
  fechamento/caixa, produção (board/planning). Replica o rigor do `admin_console` (gold standard).
- **Dedicado (operacional real-time):** PDV, KDS station, fila de pedidos do operador.
- **Conserto (do audit):** lifecycle único (`operator_orders.next_status_for`, não duplicar em
  projection); `backstage/permissions.py` único; decidir destino do KDS-no-Admin; um transporte.

---

## Parte 4 — Tenets de design consolidados (entram nas Specs, etapa C)
1. **Superfície = apresentação pura.** Consome read-model de DADO + SurfaceActionProjection; zero
   política, zero Core, zero HTML-em-view, zero aritmética em template.
2. **Um contrato projection+comando**, consumido idêntico por web/PDV/admin-custom/agentic.
3. **Config-driven é a regra:** comportamento, copy e branding por `ChannelConfig`/`RuleConfig`/
   `OmotenashiCopy`/`NotificationTemplate` — vertical food/BR NUNCA hardcoded na superfície/orquestrador.
4. **Omotenashi + acessibilidade são first-class**, não polish ([[feedback_accessibility_omotenashi_first_class]]).
5. **Availability-first + confirmação otimista + timeouts transparentes** atravessam todas as
   superfícies.
6. **Fluidez (Shopify) com alma (omotenashi):** one-page, recálculo ao vivo, low-friction — mas
   branded, acolhedor, BR.
7. **Maps-first** no endereço; **PIX-first** no pagamento; **WhatsApp via ManyChat** no agentic.
8. **Unfold canônico p/ gestão; dedicado p/ operacional** — fronteira por natureza do trabalho, um
   contrato unificando.
9. **Core sagrado**; orquestrador = comando+política+dado; mudanças no shop/ sinalizadas; kernel só
   com autorização explícita.
10. **Sem jargão, ref-not-code, `_q` centavos, no-residuals** — convenções do projeto mantidas.

## Pendências/decisões que sobem pra C/D
- Detalhar a forma do **read-model de DADO** (DTO surface-agnostic) vs **projeção de apresentação**
  (por superfície) — o contrato exato. [D]
- Tiles-de-ação-na-grade do PDV (avaliar com Pablo). [shell do PDV]
- Express/PIX-1-toque no checkout (avaliar). [C storefront]
- Layout PDV (D2) e impressão web (D3) — fase de shell do PDV.
</content>
