# Arquitetura das Superfícies — o Contrato das 3 Camadas (Etapa D · WP1)

> Iniciativa [[project_excellence_refactor_initiative]]. Etapa **D (Arquitetura)**, Work Package **WP1**.
> Saída de A→B→C: fundação no [Mapa do Core](00-core-capability-map.md), causa-raiz na
> [Auditoria](01-surface-audit.md), decisões D1–D7 no [Confronto](02-confronto.md), 1ª spec em
> [Storefront](03-spec-storefront.md). Este é o **blueprint** — define o **contrato exato** que todo
> código do redesign vai seguir. **Não contém código de feature.** Ancora as ADRs
> [005](../decisions/adr-005-orchestrator-as-coordination-center.md) (orquestrador = centro de
> coordenação) e [012](../decisions/adr-012-headless-surface-contract.md) (Projection com Actions),
> e é registrado em [ADR-014](../decisions/adr-014-surface-data-presentation-cut.md).

---

## 0. A tese, em uma frase

A dívida ("frankenstein") nasceu de uma fronteira **incompleta**: a regra "superfície nunca toca o
Core" estava certa, mas **faltava a camada de apresentação dentro da superfície** — então a
apresentação (copy, formatação, layout) não tinha pra onde ir e **vazou pra dentro do orquestrador**,
inflando `shop/services/` num BFF de ~7.000 linhas. A correção **não é afrouxar** a fronteira: é
**adicionar a camada de apresentação na superfície** e **cortar dado de apresentação** dentro do
read-side. A mesma regra, agora completa, produz resultado limpo.

```
                  ┌──────────────────────────────────────────────────────────────┐
   CORE (sagrado) │  domínio puro: offerman/stockman/orderman/… — intocado        │
                  └───────────────▲──────────────────────────────────────────────┘
                                  │ services + protocols (acoplamento por ref/uuid/handle)
                  ┌───────────────┴──────────────────────────────────────────────┐
  ORQUESTRADOR    │  shop/services/    = COMANDOS + SAGA + POLÍTICA  (write-side)  │
  (shop/)         │  shop/projections/ = PROJECTIONS de dado         (read-side)   │  ◄── SELO ÚNICO
  editável,       │      frozen · surface-agnostic · policy-laden · semântico      │
  sinalizado      └───────────────▲──────────────────────────────────────────────┘
                                  │ importa a Projection de dado (nunca o Core)
                  ┌───────────────┴──────────────────────────────────────────────┐
  SUPERFÍCIES     │  <surface>/presentation/ = PRESENTATION                       │
  (apresentação   │      consome a Projection de dado + Actions → shape de tela    │
  pura)           │  storefront · pdv(nuxt) · backstage/admin · agentic(headless)  │
                  └──────────────────────────────────────────────────────────────┘
```

**Os dois cortes, ortogonais:**
1. **Mecânico (FICA, intocado):** superfície nunca importa o Core. Já testado; é a parede que torna o
   `cart.py::get_cart` estruturalmente impossível.
2. **Semântico (NOVO, este doc):** dentro do read-side, **Projection de dado** (orquestrador) vs
   **Presentation** (superfície). É o corte que faltava — e que vamos tornar **testável**.

> **Vocabulário (resolve a sobrecarga de "projection").** No orquestrador, **`Projection`** = o dado
> resolvido, policy-laden, agnóstico de superfície — é exatamente a "Projection" da
> [ADR-012](../decisions/adr-012-headless-surface-contract.md), **e fica onde sempre esteve**
> (`shop/projections/`). Cada Projection carrega `actions: list[Action]` (a `Action` é o item
> acionável — renomeada de `SurfaceActionProjection`, ver §1.1). Na superfície, **`Presentation`** = a aparência
> (copy/format/layout). "Presentation" **não** é sinônimo de "projection" — então não há colisão. O
> bug de naming antigo não era a palavra "projection"; era **não existir uma camada de Presentation na
> superfície**, então a apresentação vazava pra `shop/`. Adicionando `Presentation`, "projection"
> volta a significar só uma coisa: dado do orquestrador.

---

## 1. Os dois contratos, com precisão

### 1.1 `Projection` (de dado) — dono: orquestrador

A unidade que o orquestrador **expõe** para qualquer superfície ler. É a "Projection (factual, resolvida,
pronta pra render)" da [ADR-012](../decisions/adr-012-headless-surface-contract.md) — este doc só
**fixa suas propriedades** e **dá casa ao read-side** (`shop/projections/`):

| Propriedade | Regra | Por quê |
|---|---|---|
| **Frozen** | `@dataclass(frozen=True)` (ou tuple/enum imutável) | É um selo de leitura; ninguém muta downstream. |
| **Surface-agnostic** | Idêntica p/ storefront, PDV, admin-custom, agentic. Zero conhecimento de HTTP/template/canal-de-render. | Um dado, N telas. A mesma Projection serve Django, Nuxt e mensagem de chat. |
| **Policy-laden** | Toda decisão **já tomada**: preço-em-contexto, disponibilidade-em-contexto, elegibilidade, `next_status`, `can_checkout`, `reason_code`. | A superfície **nunca re-deriva** política. Mata `product_cards` (promo via método privado do Core). |
| **Semântica, não renderizada** | Carrega `_q` (centavos `int`), enums, timestamps ISO, booleanos, refs, `reason_code`, `payload_schema`. **NUNCA** copy PT-BR, formatação de dinheiro, frase de ETA, label, HTML. | "R$ 15,00", "saiu do forno", "Pronto para retirada" são **Presentation**. O dado é `1500`, `Availability.READY`, `ready_at=<iso>`. |
| **Dono = orquestrador** | Construída em `shop/projections/`. A superfície importa o **tipo frozen + o builder** de `shopman.shop.projections`; **nunca** o Core. | Selo único (ADR-005). A fronteira mecânica continua valendo. |
| **Carrega `Action[]`** | Cada `Action` ("o que posso fazer agora": ref/kind/label-key/enabled/reason/href/method/payload_schema/idempotency/confirmation) é um item de `Projection.actions[]` — policy-laden, decidido pelo orquestrador. | Contrato de comando uniforme (ADR-012). `label` aqui é **key** de copy, não a string final. **Renomeado de `SurfaceActionProjection`** — "Surface" mentia (é surface-agnostic) e "Projection" sobrevende um item de `.actions[]`; `Action` é o nome do conceito na própria ADR-012. |

**O que a Projection NÃO carrega (vira Presentation):** strings de UX, `format_money`/locale, frases de
ETA, labels de enum, ordenação-para-exibir, agrupamento visual, ícones, HTML/fragmentos.

> **Nuance do `_q`/`_display`:** hoje as projections carregam par `price_q` + `price_display`. No corte,
> a **Projection de dado carrega só `price_q`** (semântico); o `_display` (`R$ 15,00`, pt-BR) é
> **Presentation**. Formatação monetária é locale, e locale é tela. Idem `Availability` enum (dado) vs
> seu label PT (Presentation, vindo de `OmotenashiCopy`/config — nunca hardcoded; hoje o label PT mora
> em `projections/types.py` e sai no split).

### 1.2 `Presentation` — dona: cada superfície

| Propriedade | Regra |
|---|---|
| **Por superfície** | Vive em `<surface>/presentation/`. Storefront, PDV, backstage e agentic têm a sua. |
| **Consome só o contrato** | Lê **`shop.projections`** (Projection de dado) + `Action`. **Nunca** o Core. **Nunca** `shop.services` (write-side). |
| **Produz shape de tela** | Resolve copy (via Projection de copy do `OmotenashiCopy`), formata `_q`→`R$`, frase de ETA, label de status, agrupa/ordena para exibir, mapeia ícone, escolhe fragmento. |
| **Frozen na saída** | O objeto que o template/JSON consome é frozen; **zero aritmética no template**, zero política. |
| **Específica da tecnologia de render** | Storefront → dataclass/dict de contexto p/ templates HTMX/Alpine. PDV/agentic → JSON-serializável p/ Nuxt/headless. Admin → contexto p/ template Unfold. **A Projection de dado é a mesma; só a Presentation varia.** |

**Copy nunca é hardcoded na superfície.** A *escolha* de qual `key/moment/audience` usar é Presentation;
o *conteúdo* da copy é dado/config (`OmotenashiCopy`, exposto como Projection `shop/projections/copy.py`).
Assim mantemos os dois tenets ao mesmo tempo: "copy = decisão de tela" **e** "vertical food/BR nunca
hardcoded".

### 1.3 A mesma Projection, quatro telas (exemplo: carrinho)

```
shop/projections/cart.py::build_cart(session_key, channel_ref) -> CartProjection(frozen)
   ├─ lines: [CartLine(sku, qty, unit_price_q, line_total_q, availability=Availability.READY,
   │                    discount_q, planned=False, ...)]
   ├─ totals: CartTotals(subtotal_q, discount_q, delivery_fee_q, total_q)
   ├─ free_shipping: FreeShippingProgress(threshold_q, remaining_q, reached=False)
   └─ actions: [Action(ref="checkout", enabled=True, href="/api/v1/...", ...)]
        │
        ├── storefront/presentation/cart.py::present(proj, copy)  →  R$ 27,50 · "Faltam R$ 12,50 p/ frete grátis" · drawer
        ├── pdv (nuxt)/presentation/cart.ts                       →  JSON → grade Smart-Grid, total no rail
        ├── backstage/presentation/order_queue.py (admin)         →  linha da fila, ações Unfold
        └── agentic: render da Projection como mensagem WhatsApp   →  "Seu carrinho: 2× Croissant…"
```

Um builder de dado. Quatro Presentations. **Nenhuma re-deriva preço, desconto ou disponibilidade** — o
`discount_q`, o `line_total_q` e o `Availability` já vêm decididos. Isso mata, por construção, a
divergência preço-vitrine vs preço-carrinho (audit §Storefront).

---

## 2. As quatro superfícies consomem o contrato de forma idêntica

O **padrão é um só**: `Projection de dado (shop/projections) → Presentation (surface) → render`;
mutação via `shop.services` (comando) ou REST + `Action`. **Só a tecnologia de render
varia.**

| Superfície | Tech de render | Lê o dado via | Presentation em | Emite comando via |
|---|---|---|---|---|
| **Storefront** | Django + HTMX/Alpine | view chama `shop.projections.*.build()` | `storefront/presentation/` → template | `shop.services.cart/checkout/…` |
| **PDV** | Nuxt/UI-Thing (headless) | proxy → endpoint Django serializa a Projection em JSON | TS no Nuxt (schema POS gerado do contrato) | REST (`backstage/api/operations`) + `Action.href` |
| **Backoffice (admin-custom)** | Unfold canônico | `UnfoldModelAdminViewMixin+TemplateView` → `backstage/presentation/` que envolve `shop.projections` | template Unfold (gold standard `admin_console`) | `shop.services.*` (comando) |
| **Backoffice (operacional)** | dedicado (KDS/fila) | view chama `shop.projections.*` | `backstage/presentation/` | `shop.services.kds/operator_orders` |
| **Agentic** | headless (sem UI própria) | `shop.projections.conversation` (`RemoteConversationProjection`) | render da Projection como **mensagem** (Presentation fina) | `shop.services.remote_mutations` + `Action` |

**Invariante:** se uma superfície precisa de um campo que a Projection de dado não tem, a resposta
**nunca** é "a superfície calcula" — é "a Projection passa a expor o campo (decidido pela política do
orquestrador)". A superfície é cega para política, sempre.

**Agentic é o teste de fogo do contrato:** por ser headless, ele só funciona se a Projection de dado for
100% surface-agnostic. Se o storefront "puxar" Presentation pro dado, o agentic quebra. Manter o agentic
barato (rodada 2 in-chat, D4) = manter a Projection limpa. O agentic é o canário do corte.

---

## 3. Onde o orquestrador expõe as Projections de dado

### 3.1 `shop/` parte em dois eixos (CQRS explícito, dentro do mesmo app)

| Pasta | Papel | Natureza |
|---|---|---|
| `shop/services/` | **Write-side:** comandos (única mutação cross-context), saga/lifecycle, política, ports/adapters. | A **espinha — SAGRADA**. Preservar. |
| `shop/projections/` | **Read-side:** as `Projection` frozen, surface-agnostic, policy-laden. | Hoje só tem `types.py` (contrato). **Cresce** para abrigar o dado drenado dos `*_context`/`order_tracking`. |

A espinha (`lifecycle.py`, `production_lifecycle.py`, `config.py`, `rules/`, `handlers/`, `adapters/`,
`modifiers.py`, `protocols.py`, `notifications.py`) **não muda**. O que muda é: os read-models de tela
que hoje moram, inflados e misturados com copy, em `shop/services/` **migram pra `shop/projections/`,
purgados de apresentação**. A apresentação que estava junto **sai pras superfícies** (em
`<surface>/presentation/`).

### 3.2 Mapa de drenagem (o que vira o quê) — executado na WP4, cada passo sinalizado

| Hoje (`shop/services/`) | Vira (DADO em `shop/projections/`) | Presentation migra para |
|---|---|---|
| `order_tracking.py` (1.652 ln) | `projections/order_tracking.py` (status, timeline events, `eta_at`, fulfillment, payment) | `storefront/presentation/order_tracking.py` (copy/ETA/steps) |
| `storefront_context.py` | `projections/catalog.py` + `projections/home.py` (merchandising como flags/dados) | `storefront/presentation/home.py` (fresh-from-oven, happy-hour, nudge) |
| `cart_context.py` | `projections/cart.py` (linhas, totais, descontos, fee, `can_checkout`, actions) | `storefront/presentation/cart.py` |
| `catalog_context.py` | `projections/catalog.py` (itens c/ preço-em-contexto + disponibilidade-em-contexto) | `storefront/presentation/catalog.py` (UM card só) |
| `checkout_context.py` | `projections/checkout.py` (fulfillment options, addresses, slots, métodos, totais) | `storefront/presentation/checkout.py` |
| `customer_orders.py` / `customer_context.py` | `projections/customer.py` (perfil, endereços, histórico, insights) | `storefront/presentation/account.py` |
| `pos.py` (2.179 ln — só o **payload de UI**) | `projections/pos.py` (comanda/tab, linhas, actions) | Presentation TS no Nuxt (schema gerado) |
| `payment_status.py` | `projections/payment_status.py` | `storefront/presentation/payment.py` |
| `conversation.py` | `projections/conversation.py` (já é DATA — só realocar) | render-como-mensagem (agentic) |
| `projections/types.py` | **fica** (contrato compartilhado: `Action`, `Availability` enum, `OrderItem`…) — só **sai o label PT** do enum (vira Presentation) | label PT → Presentation/`OmotenashiCopy` |
| `operator_orders.next_status_for` (lifecycle) | permanece **single source**; `projections/operator_queue.py` o consome | mata `order_queue.py::NEXT_STATUS_MAP` duplicado |
| copy/thresholds hardcoded (`"está esgotado"`, `> 0.05`, freshness 15/60min, happy-hour) | externalizar p/ `OmotenashiCopy`/`ChannelConfig`/`RuleConfig`; expor via `projections/copy.py` | a superfície lê a Projection de copy/flag |

> **`pos.py` (2.179 ln) — corte cirúrgico:** a parte **commit/orquestração** (build_session_ops,
> validate_manager_approval, fire/move) **fica em `shop/services/pos.py`** (write-side, espinha). Só o
> **payload-de-UI** sai para `projections/pos.py`. Não é split de tudo — é separar comando de leitura.

> **`shop/projections/types.py` não muda de casa.** O contrato compartilhado (ADR-012) fica onde está.
> A única mexida é remover o **label PT** do `Availability` (que é Presentation), mantendo o enum (dado).

---

## 4. Refinamento do `test_import_boundaries` — o corte política/apresentação, testável

**Princípio (decisão Pablo 2026-06-05):** o refinamento **não é** sobre "quem lê o Core" — essa
fronteira **fica intocada** (superfície segue sem importar o Core). O refinamento **adiciona** a
fronteira dado/apresentação como **nova regra testável**.

### 4.1 Regras que FICAM (mecânica — zero mudança)

Todas as 17 checagens atuais de `shop/tests/test_import_boundaries.py` permanecem. As centrais:
- `test_kernel_packages_do_not_import_host_layers`
- `test_surfaces_do_not_import_each_other`
- `test_shop_imports_surfaces_only_through_adapters`
- `test_framework_does_not_import_protected_kernel_internals`
- `test_surfaces_do_not_import_orderman_write_primitives`
- `test_storefront_surface_reads_delegate_kernel_domains` ← **a regra que provou o ponto:** a Presentation
  já não pode importar o Core. Era *incompleta* (não havia camada de Presentation), não *errada*. **Fica.**
- `test_*_delegates_*_mutations` (cart/pos/checkout/auth/payment) — comando sempre via `shop.services`.

> Nota: as regras hoje escritas contra `<surface>/projections/` passam a apontar para
> `<surface>/presentation/` (a pasta de Presentation) — é renomeação de alvo, não mudança de intenção.

### 4.2 Regras que ENTRAM (semântica — o corte novo)

| Regra (nova) | Intenção | Esboço de checagem |
|---|---|---|
| **R-A · Presentation lê só o read-side** | `<surface>/presentation/` pode importar `shopman.shop.projections` (Projection + builders), mas **não** `shopman.shop.services` (write-side). | AST: em `*/presentation/`, proibir `from shopman.shop.services …`. (Mutação continua nas views/intents.) |
| **R-B · Projection de dado não carrega apresentação** | `shop/projections/` não importa `format_money`/locale, não importa template/HTML utils, e não contém literal de copy PT-BR de UX. | AST + scan de literais: proibir import de `utils…format_money`, `django.template`, `django.utils.html` em `shop/projections/`; flag de string PT-BR de UX. |
| **R-C · Projection é frozen + agnóstica** | DTOs de `shop/projections/` são `frozen=True` e ignoram HTTP/canal-de-render. | AST: `@dataclass` exige `frozen=True`; proibir `django.http`/`request` em `shop/projections/`. |
| **R-D · uma forma de card** | impedir o retorno do 2º shape de card e do template paralelo. | "módulo/template proibido existe" (igual aos guards atuais): `product_cards.py` e `availability_preview.html` não voltam. |

Estas quatro regras **codificam o corte** que hoje é só convenção. Com elas, "apresentação no
orquestrador" e "política na superfície" viram **estruturalmente impossíveis** — exatamente como o corte
mecânico já fez com "superfície lê o Core".

---

## 5. Estrutura de pastas (alvo do redesign)

```
shopman/shop/                         ORQUESTRADOR (editável, cada mexida sinalizada)
├── lifecycle.py  production_lifecycle.py        ← ESPINHA SAGRADA (não tocar)
├── config.py  protocols.py  modifiers.py  notifications.py  middleware.py
├── rules/  handlers/  adapters/  webhooks/  models/  management/        ← espinha (não tocar)
├── services/                          WRITE-SIDE: comandos + saga + política
│   ├── sessions.py  checkout.py  cart.py(mutação)  availability.py(decide/reserve)
│   ├── payment.py  cancellation.py  fulfillment.py  notification.py  fiscal.py  loyalty.py
│   ├── operator_orders.py  kds.py  pos.py(commit/orquestração)  remote_mutations.py
│   ├── customer.py(ensure)  auth.py  access.py  devices.py  business_calendar.py …
│   └──  (purgado dos read-models de tela)
├── projections/                      READ-SIDE: Projection de dado (frozen·agnóstica·policy-laden)
│   ├── types.py                      contrato compartilhado (Action, Availability, OrderItem…)  [FICA — ADR-012]
│   ├── catalog.py  home.py  cart.py  checkout.py  product_detail.py     [NOVO — drenado dos *_context]
│   ├── order_tracking.py  payment_status.py
│   ├── customer.py  customer_orders.py
│   ├── pos.py  operator_queue.py     [next_status_for = single source em services/operator_orders]
│   ├── conversation.py               [já-DATA, só realocado]
│   └── copy.py                       OmotenashiCopy resolvido (key/moment/audience) como dado
└── tests/test_import_boundaries.py   [+ R-A/R-B/R-C/R-D]

shopman/storefront/                   SUPERFÍCIE cliente — apresentação pura (Django/HTMX/Alpine)
├── views/                            HTTP/HTMX/permissão; chama projections.build + presentation.present; mutação→shop.services
├── presentation/                     PRESENTATION: Projection de dado → shape de tela (copy/format/layout)  [← era projections/]
├── intents/                          parse request→ops (sem resolver Core)
├── cart.py                           adapter session-key↔shop (sem política — get_cart aposentado)
├── templates/  context_processors.py  middleware.py  omotenashi/

shopman/backstage/                    SUPERFÍCIE operador
├── admin_console/                    Unfold canônico (gold standard) — consome projections via presentation
├── presentation/                     PRESENTATION (consome shop.projections; order_queue sem lifecycle próprio)  [← era projections/]
├── views/                            KDS/POS/fila dedicados; mutação→shop.services (POS para de montar HTML)
├── api/operations.py                 transporte de comando REST headless — serve PDV + agentic
├── permissions.py                    ⭐ NOVO único (mata as 5 cópias de _can_*)
├── models/  templates/

surfaces/pos-nuxt/            SUPERFÍCIE PDV (Nuxt/UI-Thing, headless)
├── presentation em TS                consome Projection serializada + Action; schema POS GERADO do contrato
└── server/utils/djangoProxy.ts       transporte (preservar — é ouro)

(agentic)                             SUPERFÍCIE headless — SEM UI própria
└── consome shop.projections.conversation → render como mensagem; comando via remote_mutations + Action

instances/nelson/                     → DISSOLVER como código (§6)
```

---

## 6. Dissolução do app da instância (Nelson = config + dados + marca)

**Decisão (Pablo 2026-06-05):** no modelo "nosso próprio Shopify", **tenant não é pacote de código**. O
`Shop` já é **singleton** (single-tenant por deployment), então "Nelson" = `Shop` singleton + dados no DB
+ assets de marca + settings do deployment. `instances/nelson/` como **pacote Python é vestígio** de
tratar tenant como código → **eliminar**. (Multi-tenant futuro = outra conversa: tirar `Shop` de
singleton. Fora de escopo.)

### 6.1 Tabela de relocação (cada item de `instances/nelson/` até o pacote sumir)

| Item hoje | Natureza real | Destino | WP |
|---|---|---|---|
| `modifiers.py` (D-1, Happy Hour) | regra de negócio **genérica** disfarçada de bespoke | **rule types genéricos** em `shop/rules/` ("desconto por flag de disponibilidade", "desconto por janela de horário") + params via `RuleConfig` por canal | WP5 |
| `customer_strategies.py` (`register_strategy`) | estratégia de cliente — quase toda genérica | **default genérico no orquestrador**; resíduo Nelson = thin ou zero | WP5 |
| `migrations/0001_sync_collection_taxonomy.py` | **dado** (taxonomia), não estrutura | **seed/fixture** (não migration em models compartilhados) | WP5 |
| `static/` (ícones PWA) | **marca** | `Shop` branding/assets | WP5 |
| `management/commands/seed.py` | **dado de bootstrap** do deployment | fixture/comando de **deployment** (nível `config/`), não pacote de tenant | WP5 |
| `apps.py` (`AppConfig`) | wiring do pacote | **desaparece** quando não há pacote de código | WP5 |

**End-state:** `instances/nelson/` **deixa de existir como código**. "Nelson" passa a ser:
`Shop` singleton + linhas de DB (`Channel`/`ChannelConfig`/`RuleConfig`/`OmotenashiCopy`/catálogo) +
assets de marca + `.env`/settings do deployment. Detalhe de execução (e se sobra um harness fino de
deployment) é da **WP3** (spec `08-instance-drain.md`) e da **WP5** (execução). WP1 fixa o **princípio e
o alvo**: zero código de tenant.

> Confirma o tenet #3 (vertical food/BR nunca hardcoded) e [[feedback_zero_residuals]]: ao dissolver,
> zerar tudo — nada de `# formerly Nelson`.

---

## 7. Mudanças no `shop/` — todas sinalizadas (Core sagrado)

Conforme o mandato: **kernel (`packages/`) só com autorização explícita do Pablo**; **`shop/` editável,
mas cada mudança sinalizada**. Este blueprint **não altera nada** — apenas registra o que a Fase 2
(WP4/WP5) vai tocar no `shop/`, para o Pablo aprovar item a item:

- **S1 — Expandir `shop/projections/`** (hoje só `types.py`) para abrigar o read-side de dado. *Aditivo.*
- **S2 — Drenar dado de tela** de `services/{order_tracking,*_context,payment_status,customer_orders}`
  para `projections/`, purgando apresentação. *Move + purga.*
- **S3 — Realocar `conversation.py`** (já-DATA) para `projections/`; remover o **label PT** do
  `Availability` em `projections/types.py` (vira Presentation); **renomear `SurfaceActionProjection` →
  `Action`** (zero-residual; "Surface" mentia, é surface-agnostic). *Move + purga + rename; contrato ADR-012 mantido.*
- **S4 — Recortar `pos.py`**: payload-de-UI → `projections/pos.py`; commit/orquestração fica. *Recorte.*
- **S5 — Externalizar vertical** (copy/thresholds) p/ `OmotenashiCopy`/`ChannelConfig`/`RuleConfig`. *Config.*
- **S6 — `operator_orders.next_status_for` vira single source**; `order_queue` para de duplicar. *Dedup.*
- **S7 — Adicionar R-A/R-B/R-C/R-D** ao `test_import_boundaries` (+ reapontar alvos `projections/`→
  `presentation/` nas superfícies). *Aditivo (teste).*
- **S8 — Rule types genéricos** (D-1/Happy Hour) em `shop/rules/` (WP5). *Aditivo + drain da instância.*

**Intocado (SAGRADO):** `packages/` inteiro; e no `shop/`, a espinha — `lifecycle.py`,
`production_lifecycle.py`, `config.py`, `protocols.py`, `rules/engine.py`, `handlers/`, `adapters/`,
`modifiers.py`, `notifications.py`, `webhooks/`, `models/`. O contrato ADR-012 (Projection com Actions)
e ADR-005 (orquestrador = centro) são **preservados e refinados**, nunca contraditos.

---

## 8. Como isto satisfaz os princípios inegociáveis

| Princípio | Como o blueprint entrega |
|---|---|
| **Core sagrado** | `packages/` intocado; toda mudança é em `shop/` (read-side) e nas superfícies, cada uma sinalizada (§7). |
| **Superfície = apresentação pura** | `<surface>/presentation/` consome só a Projection de dado; R-A/R-B/R-C tornam política-na-superfície e apresentação-no-dado estruturalmente impossíveis. |
| **Um contrato projection+comando** | `Projection` de dado + `Action` (ADR-012) consumidos idêntico por web/PDV/admin/agentic (§2). |
| **Config-driven é a regra** | vertical (copy/thresholds/D-1/Happy Hour) drenado p/ `OmotenashiCopy`/`ChannelConfig`/`RuleConfig`; nada hardcoded (§3.2, §6). |
| **Instância = config+dados+marca** | `instances/nelson/` dissolvido como código (§6). |
| **Não contaminar com o frankenstein** | superfícies reconstruídas do zero (Fase 3) sobre o contrato; só a espinha é preservada; o read-side é split, não pescado. |

---

## 9. Aberto / handoff

- **WP2 (specs restantes):** PDV (`05`), Agentic (`06`), Backoffice (`07`) — usam este contrato como
  âncora. Backoffice inclui gestão de sync de catálogo (WP10) e anúncios/automação (WP11).
- **WP3:** `08-instance-drain.md` detalha a execução da §6.
- **WP4:** executa S1–S7 (split do read-side) com `make test` verde; cada passo sinalizado.
- **Decisão fina pendente (não bloqueia):** formato exato da Projection de copy (`projections/copy.py`) —
  um builder por superfície/moment vs catálogo único resolvido. Resolver na WP4 com o 1º caso real
  (order_tracking copy).
- **Branch limpa do redesign:** criar na transição Fase 1→2 (decisão Pablo), antes da WP4.

---

## Glossário (este doc)

| Termo | Significado | Casa |
|---|---|---|
| **`Projection`** (de dado) | dado resolvido, frozen, surface-agnostic, policy-laden, semântico. A "Projection" da ADR-012. | `shop/projections/` (orquestrador) |
| **`Action`** | uma ação disponível agora — item de `Projection.actions[]` (contrato de comando, ADR-012). Era `SurfaceActionProjection`. | `shop/projections/types.py` |
| **`Presentation`** | aparência: copy/format/layout/ETA/label/ícone. Consome a Projection de dado. | `<surface>/presentation/` |
| **write-side** | comandos + saga + política (a espinha). | `shop/services/` |
| **read-side** | as Projections de dado. | `shop/projections/` |
