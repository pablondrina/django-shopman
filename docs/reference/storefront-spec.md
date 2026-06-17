# Storefront — SPEC (engenharia reversa do estado atual)

> **Como ler.** Esta spec foi escrita **a partir do código** (não do desejado): descreve o que o
> storefront **de fato entrega hoje**, no estado headless (Django sem páginas de cliente; loja Nuxt
> no apex). Serve para uma "revisão às avessas" — compare com o que você esperava e veja onde há
> brecha. A seção final (**Gaps / a verificar**) é o ponto de partida da revisão.
>
> Data: 2026-06-17. Base: branch `main` pós-merge do headless (PR #10).

---

## 0. Arquitetura (o contrato físico)

- **Desacoplado por domínio.** A loja de cliente é o **Nuxt** (`surfaces/storefront-uithing-nuxt/`),
  servida no **apex** (`/`). O **Django é headless**: serve só `/api/v1/*` (+ `/admin/` + webhooks +
  `/api/v1/backstage/`). Não há **nenhuma** página HTML de cliente no Django.
- **BFF é a ponte.** O servidor Nuxt (`server/api/v1/[...path].ts`, `server/api/auth/[...path].ts`,
  `server/utils/djangoProxy.ts`) proxia o navegador → Django por baixo. O browser só fala com o
  próprio host. O BFF: seta `origin`/`referer` = host do Django (CSRF passa) e repassa o `Set-Cookie`
  **host-only** para o host da loja → **a sessão do cliente nasce no domínio da loja**, sem CORS.
- **1 knob de domínio:** `SHOPMAN_STOREFRONT_BASE_URL` (apex) é a fonte única de todos os links de
  cliente que o Django gera (notificações, magic link). `shopman/shop/services/storefront_links.py`.
- **Topologia (staging validado):** apex→loja, `api.`→Django, `admin.`→admin/operador, `pos.`→PDV.

---

## 1. Superfícies & fluxos de cliente (Nuxt)

Páginas em `surfaces/storefront-uithing-nuxt/app/pages/`. Cada uma é server-driven (consome
projeções do Django via BFF).

| Rota | O que o cliente faz | API principal |
|---|---|---|
| `/` (index) | Home: hero, vitrine (6 itens), "como funciona", CTA WhatsApp, banner de pedido ativo, gancho de recompra do último pedido | `GET /api/v1/storefront/home/` |
| `/menu` | Catálogo: seções com pills sticky (scroll-spy), badge happy hour, contagem por seção | `GET /api/v1/storefront/menu/` (+ `/menu/<collection>/`) |
| `/busca` | Busca + filtros (chips dietéticos/categóricos), deep-link `?q=&filtro=` | reusa `/storefront/menu/` (filtra client-side) |
| `/product/[sku]` | PDP: galeria, preço (com riscado), disponibilidade, badges, acordeões (combo/ingredientes/nutricional/conservação), "veja também", add-to-cart sticky no mobile, JSON-LD | `GET /api/v1/storefront/products/<sku>/` |
| `/cart` | Carrinho: linhas, descontos, progresso de mínimo, upsell, **estados de hold** (aguardando confirmação → pronto p/ confirmar, countdown), alerta de estoque com substitutos | `GET /api/v1/storefront/cart/`; `PUT /api/v1/cart/skus/<sku>/`; cupom `POST/DELETE /api/v1/cart/coupon/` |
| `/checkout` | Checkout multi-step: contato → retirada/entrega → endereço (Google Places + zona) → data/hora (slots) → pagamento (método, cupom, loyalty, presente, observações) → revisão | `GET /api/v1/storefront/checkout/`; `PATCH /api/v1/checkout/draft/` (zona); `PATCH /api/v1/checkout/loyalty/`; `POST /api/v1/checkout/` (commit) |
| `/pedido/[ref]/pagamento` | Gate de pagamento: PIX (QR + copia-e-cola + countdown ancorado em `server_now_iso`) ou cartão (redirect seguro); polling 8s | `GET /api/v1/payment/<ref>/` + `/status/`; ações via `POST` (apiPath) |
| `/tracking/[ref]` | Acompanhamento: promessa (título/msg/deadline), timeline, resumo, fulfillment (retirada/entrega+rastreio), ações (recompra, pagar, cancelar, avaliar, suporte); polling 30s | `GET /api/v1/tracking/<ref>/`; ações `POST /api/v1/orders/<ref>/{cancel,rate,reorder}/` |
| `/account` | Hub: card de loyalty (tier/pontos/carimbos), último pedido (acompanhar/refazer), navegação, logout | `GET /api/v1/account/summary/` |
| `/account/pedidos` | Histórico filtrável (todos/ativos/anteriores) + recompra | `GET /api/v1/account/orders/?filter=` |
| `/account/enderecos` | CRUD de endereços (criar/editar via AddressPicker, default, excluir) | `GET/POST /api/v1/account/addresses/`, `PATCH/DELETE/POST /api/v1/account/addresses/<id>/` |
| `/account/perfil` | Nome/sobrenome/email/aniversário (telefone read-only) | `GET/PATCH /api/v1/account/profile/` |
| `/account/preferencias` | Preferências alimentares + canais de notificação (toggles) | `POST /api/v1/account/preferences/{food,notifications}/` |
| `/account/seguranca` | Dispositivos confiáveis (revogar 1/todos), exportar dados, excluir conta | `GET/DELETE /api/v1/account/devices/…`, `GET /api/v1/account/export/`, `POST /api/v1/account/delete/` |
| `/login` | Auth sem senha: telefone → OTP (WhatsApp/SMS) → (welcome se novo); device-trust 30d | `POST /api/auth/{device-check,request-code,verify-code,trust-device}/` |
| `/a` | Bridge de magic link: lê `?t=`, troca por sessão, navega ao destino derivado | `POST /api/auth/access/` |

**Composables-chave:** `useCartState` (qty/cupom otimista), `useShopSession` (identidade/estado),
`useReorder` (recompra + conflito), `useShopmanApiPath` / `useShopmanCsrfHeaders` (BFF + CSRF).

**Capacidades entregues:** navegar/buscar → PDP → carrinho (com holds vivos) → checkout
retirada/entrega → pagar PIX/cartão → acompanhar → recompra; login OTP/WhatsApp/device-trust/magic-link;
conta completa (perfil/endereços/preferências/dispositivos/LGPD export+delete); presente; cupom;
loyalty; SEO (robots/sitemap domain-aware, JSON-LD na PDP).

---

## 2. Contrato da API (Django, consumido pelo BFF)

Base `/api/v1/`. `AllowAny` + cookie de sessão; mutações usam `SessionAuthentication` + CSRF.
GETs de storefront fazem `ensure_csrf_cookie` (estabelecem sessão+token).

**Descoberta (read):** `storefront/home/`, `storefront/menu/[<collection>/]`,
`storefront/products/<sku>/`, `storefront/cart/`, `storefront/checkout/` — cada um devolve a projeção
+ o carrinho. Catálogo público: `catalog/products/` (filtros collection/search/available, paginado),
`catalog/products/<sku>/`, `catalog/collections/`, `availability/<sku>/` (cache 10s).

**Carrinho:** `PUT /api/v1/cart/skus/<sku>/` (set qty absoluta; 409 com `available_qty`+substitutos+ações
em falta de estoque; 120/m), `cart/coupon/` (POST/DELETE). (`cart/items/…` legado ainda existe.)

**Checkout:** `POST /api/v1/checkout/` (commit; 3/m; valida calendário, slot, endereço, zona, presente,
loyalty), `PATCH /api/v1/checkout/draft/` (cotação de zona antes do commit), `PATCH /api/v1/checkout/loyalty/`.

**Pagamento:** `GET payment/<ref>/` (projeção; redireciona p/ tracking se terminal/sem ação),
`GET payment/<ref>/status/` (polling), `POST payment/<ref>/mock-confirm/` (**só DEBUG**).

**Tracking/pedido:** `GET tracking/<ref>/` (acesso por dono/sessão/grant), `POST orders/<ref>/cancel/`,
`POST orders/<ref>/rate/`, `POST orders/<ref>/reorder/` (409 com modal de conflito se carrinho tem itens),
`GET orders/<ref>/conversation/` (projeção WhatsApp/ManyChat).

**Auth:** `auth/session/`, `auth/request-code/` (5/m), `auth/device-check/` (10/m), `auth/verify-code/`
(10/m), `auth/trust-device/`, `auth/access/` (magic link, 10/m), `auth/logout/`. Bridge ManyChat:
`POST /api/auth/access/create/` (doorman, API-key) — emite o link da loja `…/a?t=`.

**Conta (autenticada):** `account/profile/`, `account/addresses/…`, `account/summary/`,
`account/orders/[active/]`, `account/preferences/{food,notifications}/`, `account/devices/…`,
`account/export/`, `account/delete/`. **Geocode:** `POST geocode/reverse/` (sem expor chave; 30/m).

---

## 3. Read-models & o contrato `Action`

Camada dupla (ADR-012): **projeção de dados** (surface-agnostic, em `shopman/shop/projections/`) →
**presentation** (copy/moeda/tom renderizados, em `shopman/storefront/presentation/`). O Nuxt consome
a presentation via `projection_data()`.

**`Action` é o contrato canônico de toda afordância** (`shop/projections/types.py`):
`ref, kind ("link"|"mutation"|"external"|"copy"), label (pt-BR), priority, enabled, reason, href,
method, payload_schema, idempotency ("required"|"recommended"|"none"), confirmation`. O Nuxt renderiza
por `kind` (link→navega; mutation→POST com schema+confirm; external→nova aba; copy→clipboard).

**Máquinas de estado de promessa** (emitem `Action` + tom + deadline): **pagamento**
(`payment_status.py`: pix_*/card_*/paid/expired/cancelled/intent_error) e **tracking**
(`order_tracking.py`). Copy resolvida via `OmotenashiCopy`/catálogo (`projections/copy.py`).

Read-models por tela: home, catalog, product_detail, cart, checkout, payment, order_tracking,
order_confirmation, account (profile/loyalty), order_history, shop/shop_status, reorder (conflito).

---

## 4. Regras de negócio (o que o sistema enforça)

- **Commit do checkout:** `intents/checkout.py` → `shop/services/checkout.py:process()` → `CommitService`
  (idempotente). Propaga chaves explícitas de `session.data`→`order.data` (customer, fulfillment_type,
  delivery_address[_structured], saved_address_id, delivery_date/time_slot, payment, loyalty, gift…).
  Pedido nasce `status=new`.
- **Fulfillment:** pickup (slot obrigatório, sem mínimo) vs delivery (endereço obrigatório, mínimo do
  canal, zona valida cobertura+taxa via `DeliveryZone.match()` por CEP/bairro).
- **Disponibilidade & holds:** `availability.reserve()` cria hold pendente por `(session_key, sku)`,
  TTL ~30min. **Planned hold (fermata):** produção sob demanda → `metadata.planned=True`,
  `expires_at=None` até materializar; estados `is_awaiting_confirmation`→`is_ready_for_confirmation`
  (com deadline). Web: `check_on_commit=False` (confia nos holds); POS/marketplace re-verifica.
- **Slots de retirada:** mediana do `WorkOrder.finished_at` por SKU (30d, arredonda p/ 30min) → gargalo
  define o slot mais cedo. **Regra de hora:** não vende retirada/entrega HOJE após o fechamento; slot
  passado é rejeitado. Preorder: `today ≤ data ≤ today+max_preorder_days`, fora de `closed_dates`.
- **Pagamento:** timing `at_commit`/`post_commit`/`external` por `ChannelConfig`. PIX (QR+copia-cola,
  `expires_at`) / cartão (intent + captura na confirmação). Expiry → cancela + libera holds.
- **Confirmação otimista:** `immediate`/`auto_confirm`/`auto_cancel`/`manual` via `ChannelConfig`;
  auto-confirma se operador não cancelar no prazo (Directive `confirmation.timeout`, resolvido quando
  a superfície do cliente abre o pedido).
- **Recompra:** `last_reorder_context()` (último pedido do cliente) + `add_reorder_items()` (re-resolve
  SKU publicado/vendável; pula indisponíveis). Conflito se carrinho tem itens (append/replace).
- **Cupom/loyalty:** cupom valida `Coupon` ativo+disponível+promo vigente → `session.data["coupon_code"]`;
  loyalty `redeem_points_q` em `session.data["loyalty"]`; ambos re-rodam os modifiers de preço. Earn
  pós-conclusão (1 ponto/R$1, no handler).
- **Presente:** delivery exige recipient (nome+telefone); pickup opcional; `gift_hide_values`.

---

## 5. Auth & cross-cutting

- **OTP:** request-code (HMAC, nunca plaintext; TTL ~10min; entrega WhatsApp via ManyChat → SMS → email)
  → verify-code → sessão Django (bridge doorman→Guestman). Debug OTP exposto só em dev/staging
  (`SHOPMAN_EXPOSE_DEBUG_OTP`).
- **Device trust:** cookie HttpOnly (HMAC), 30d; `device-check` pula OTP.
- **Magic link:** link da LOJA `…/a?t=<token>` (sem `next` na query — destino derivado da metadata
  server-side → zero open-redirect); `POST /api/auth/access/` troca token→sessão (cookie host-only via
  BFF), concede acesso ao pedido (`order_ref` na metadata), redireciona (tracking/payment/account).
  Bridge ManyChat (`access/create/`, doorman Core) emite o link via `DOORMAN.ACCESS_LINK_ENTRY_URL`.
- **Welcome gate:** **client-side no Nuxt** (flag `requires_welcome` no payload de sessão + passo
  "welcome" no `/login`). *(O `WelcomeGateMiddleware` do Django foi REMOVIDO no headless.)*
- **Omotenashi:** copy única por 6 momentos (QUANDO) × 4 audiências (QUEM: anon/new/returning/vip),
  cascata `OmotenashiCopy` (admin) → `OMOTENASHI_DEFAULTS`. Alimenta home/menu/checkout/etc.
- **SEO:** `server/routes/robots.txt.ts` (bloqueia /account /checkout /cart /login /pedido/ /tracking/
  /api) + `sitemap.xml.ts` (home/menu/produtos, domain-aware). JSON-LD Product+Breadcrumb na PDP.
- **Notificações:** assíncronas via Directive → entrega síncrona em cadeia (manychat→sms→email);
  templates "ativos" exigem canal; links nas mensagens são magic links da loja. `origin_channel`
  (via `?channel=` ou metadata do AccessLink) roteia a notificação de volta ao canal de entrada.
- **Models do storefront:** `Promotion` (desconto auto, segmentos/aniversário/validade/mínimo),
  `Coupon` (código + limite de uso), `DeliveryZone` (taxa por CEP/bairro).

---

## 6. Gaps / a verificar (o foco da revisão às avessas)

> Itens que o **código sugere** estarem faltando, inconsistentes ou só pela metade. Cada um é um
> "confere comigo?" — alguns podem ser intencionais.

> **Atualização 2026-06-17:** os itens 1, 2, 3, 4 e 9 abaixo foram **RESOLVIDOS**
> (backends WP-1..6 + camada visual Nuxt fase A; ver
> [`STOREFRONT-GAPS-ACTION-PLAN.md`](../plans/STOREFRONT-GAPS-ACTION-PLAN.md)).
> Mantidos aqui como registro da revisão original.

### Funcionais (candidatos a brecha real)
1. **✅ RESOLVIDO — Checkout via API não persiste endereço novo / `ensure_customer` / `save_defaults`.**
   A view de página (deletada) chamava `checkout_service.{ensure_customer,persist_new_address,save_defaults}`
   *depois* do commit. A `CheckoutView` da API (`storefront/api/views.py`) chama só `process()` +
   `grant_order_access` + limpa carrinho. **Confirmar** se isso é coberto por um handler de lifecycle
   ou se a loja Nuxt deixou de salvar o endereço novo na conta / criar o cliente / salvar defaults.
   *(Coberto por teste de serviço `test_persist_address.py`, mas o serviço pode não estar sendo chamado
   no caminho da API.)*
2. **✅ RESOLVIDO — Preferência alimentar não filtra o menu.** WP-5: aviso dietético (badge âmbar)
   no card+PDP + filtro opcional "Só compatível com minhas preferências" (off, contador de ocultos).
3. **✅ RESOLVIDO — Sem "Me avise quando voltar".** WP-3: `StockNotifyButton` na PDP/cards quando
   is_notifiable (logado 1-clique / anônimo só-telefone).
4. **✅ RESOLVIDO — favoritos do cliente.** WP-4: coração explícito (PDP/cards) + coleção "Seus
   favoritos". "Veja também" (cross_sell) segue sendo lista do backend (WP-6, ok).
5. **Sem assinatura/pedido recorrente, sem gift card/créditos** na superfície.
6. **Reorder só lê do último pedido elegível** (`min_days`); sem escolher qual pedido refazer.

### Pagamento / lifecycle
7. **Cartão depende de webhook** como único retorno confiável (PCI SAQ A) — o gate de pagamento faz
   polling; confirmar UX se o webhook atrasar.
8. **`mock-confirm` é DEBUG-only** — em staging com `DEBUG=false` não há atalho de confirmação PIX
   (hoje staging usa adapter mock com auto-confirm via `SHOPMAN_MOCK_PIX_AUTO_CONFIRM`).

### Contratos / consistência
9. **✅ RESOLVIDO (parcial) — Disponibilidade colapsava pausado vs esgotado.** WP-2: flags
   `is_paused`/`is_notifiable` nas projeções + UX ("Pausado" vs "Me avise"). Enum segue com 4
   estados (decisão deliberada); a distinção fina é por flag semântica.
10. **Label de endereço:** `label_key` vs `label_custom` — qual ganha na renderização não é explícito.
11. **Loyalty sem tom/cor canônico** (diferente dos status de pedido) — UI define o estilo do tier.
12. **Copy em cascata dupla** (orchestrator + fallback por módulo) sem auditoria de chaves usadas →
    risco de drift; chave ausente degrada para string vazia.

### Operacional / infra (follow-ups já conhecidos)
13. **e2e Playwright + `locustfile`** ainda apontam p/ rotas Django legadas (apagadas) — reescrever
    contra a loja Nuxt/API. O gate de browser-QA Omotenashi foi **removido do CI** no headless.
14. **`_sse_emitters`** ainda emite canais de cliente (`stock-`/`order-`) sem assinante (no-op) junto
    com os do operador — podar.
15. **`.do/app.yaml`** (staging path-routed) ficou stale no repo (staging agora é subdomínios).
16. **Cleanup de device-trust expirado** tem método mas não há tarefa agendada.
17. **AccessLink `audience`** é validado na criação mas não enforçado na troca (débito de segurança a
    confirmar).

### Fluxo de Entrega (WP-11 — pedido do Pablo, 2026-06-17)
19. **Taxa de entrega por faixa de distância (admin-configurável)** — hoje a taxa vem do `DeliveryZone`
    (CEP/bairro) como modifier. Falta calcular por distância (loja→endereço, via lat/lng) com faixas
    configuráveis no admin.
20. **Taxa de entrega como ITEM do pedido** — hoje é `delivery_fee_q` no total; Pablo quer como linha
    do pedido (visível carrinho/KDS/fiscal).
21. **Facilitador "teleporte" de endereço (sem API)** — o serviço de entrega usado não tem API; um
    facilitador operador leva os dados de endereço pro site externo (pré-preenche/copia) só p/ reduzir
    erro de digitação; despacho segue manual num primeiro momento. Detalhes no
    [`STOREFRONT-GAPS-ACTION-PLAN.md`](../plans/STOREFRONT-GAPS-ACTION-PLAN.md) WP-11.

### Produção (não é gap, é o próximo passo)
18. **Cutover de produção** no apex real ainda não feito (staging-first). Falta pagamentos reais +
    secrets + desligar debug OTP; o apex hoje aponta p/ a landing `nb-site`.

---

## 7. Referências

- Nuxt loja: `surfaces/storefront-uithing-nuxt/` (`app/pages/`, `server/utils/djangoProxy.ts`).
- API Django: `shopman/storefront/api/` (urls + views).
- Read-models: `shopman/storefront/presentation/` + `shopman/shop/projections/`.
- Regras: `shopman/storefront/services/`, `shopman/storefront/intents/`, `shopman/shop/services/`,
  `shopman/shop/lifecycle.py`.
- Auth: `shopman/storefront/api/auth.py`, `shopman/storefront/identity.py`, `shopman/shop/services/access*.py`,
  `packages/doorman/`.
- Links de cliente / cutover: `shopman/shop/services/storefront_links.py`,
  `docs/plans/DJANGO-HEADLESS-PLAN.md`, `.do/app.staging-subdomains.yaml`.
