# Spec — PDV (Ponto de Venda) [Etapa C · WP2]

> Iniciativa [[project_excellence_refactor_initiative]]. Pilar **Ponto de Venda**. Ancorada na
> [Arquitetura](04-architecture.md) (contrato `Projection`/`Action`/`Presentation`), nas decisões
> [D2/D3](02-confronto.md) e nos dossiês [Shopify](../research/pos-benchmarks/shopify.md) /
> [STORES](../research/pos-benchmarks/stores.md) / [Take.app](../research/pos-benchmarks/take-app.md).
> É o PDV de balcão da padaria: **ergonomia de balcão (Odoo-fiel) + fluidez Shopify + contrato limpo.**
> Define *o quê* e *o contrato*; **layout (D2) e impressão (D3) são fase de shell**, não desta spec.

## 0. Posição na arquitetura (inegociável)
- O PDV é uma **superfície = apresentação pura**, **headless/Nuxt** (UI Thing). Consome a `Projection`
  de dado + `Action[]` do orquestrador via **API REST** (`backstage/api/operations`) através do **proxy
  Nuxt** (`djangoProxy.ts` — preservar, é ouro). Renderiza. **Zero política, zero Core, zero
  HTML-em-view, zero aritmética de preço/disponibilidade no cliente.**
- **Stack:** Nuxt 3 + UI Thing (não HTMX/Alpine — esse é o storefront). Branding por `Shop` tokens
  (OKLCH/fontes). Sem lib de componentes externa além do UI Thing já adotado ([[feedback_no_external_component_lib]]
  vale pro storefront Django; o PDV é o caso Nuxt já decidido em [[project_pos_uithing_redesign_goal]]).
- **A `Presentation` do PDV é TypeScript no Nuxt** (`surfaces/pos-uithing-nuxt/.../presentation/`): pega
  a `Projection` serializada em JSON e dá shape de tela (numpad, grade, ticket, teclado→qtd). **A
  Projection é a mesma** que storefront/admin/agentic consomem — só a render-tech muda (§2 da arquitetura).
- **Config-driven:** comportamento por `ChannelConfig` do canal `pos`/`balcao` (confirmation, payment
  timing, stock scope incl. `excluded_positions` = D-1 staff-only, manager-approval por permissão),
  copy por `OmotenashiCopy`, branding por `Shop`. **Nada de vertical food/BR hardcoded** no Nuxt.

## 1. Tenets do PDV (regem cada tela)
1. **Ergonomia de balcão primeiro:** alvos de toque grandes, fluxo de 1-2 toques pras ações quentes
   (add item, fire, pagar), numpad inline, teclado→qtd, autosave. O operador é o "cliente" desta
   superfície — *"excelente experiência do cliente nasce de excelente experiência do staff"* (Shopify).
2. **Comanda como handle:** toda venda é uma `Session` aberta por `(handle_type, handle_ref)` (mesa/
   tab/balcão); 1 sessão aberta por handle (constraint do Core). `move_lines` (split/transfer/merge)
   **congela preço** (não re-precifica). Nomeação via `refs` (date_sequence reset diário p/ comandas).
3. **Fire-to-kitchen progressivo** (Fase 5): enviar linhas pra cozinha (`kds.fire_lines`) sem fechar a
   venda; `fired_lines` marca o que já foi. Eat-in/takeout = `fulfillment_type`. KDS roteia por
   receita/coleção/estação (mais rico que o per-item toggle do STORES).
4. **Manager-approval por permissão** (D1, Shopify): ação sensível exige PIN de gerente **por flag de
   permissão** (`requires_manager_approval`), não por 4 gates fixos. PIN via doorman (`verify_manager_pin`).
5. **Caixa cego + confirmação otimista:** fechamento de caixa sem ver o esperado; venda auto-confirma
   por `ChannelConfig.confirmation`. Caixa/turno (`CashRegister`) com sangria/suprimento.
6. **Availability-first também no balcão:** disponibilidade-em-contexto decidida pelo orquestrador
   (inclui D-1 via `excluded_positions` do canal pos). O numpad de peso/qtd respeita o promise.
7. **Tudo é `Action`:** cada botão de operação (pagar, fire, desconto, cancelar linha, aprovar) é uma
   `Action` da Projection (enabled/reason/href/method/idempotency/confirmation). A tela **não inventa**
   CTA nem decide se pode — ela **renderiza** o que a Projection oferece.

## 2. Telas e o contrato que cada uma consome

### 2.1 Lock / Operador (entrada)
- **Projection:** sessão de operação (operador atual, caixa aberto?, permissões do operador). **Auth:**
  doorman `PinCredential` (surface-agnostic). `eligible_operators` + `verify_operator_pin`.
- **Presentation:** `PosLockScreen` (já first-class), PIN pad, troca rápida de operador.

### 2.2 Venda / Smart Grid (o coração)
- **Projection:** `pos` (read-model de dado: comanda atual + linhas + totais + disponibilidade por linha
  + `actions[]`) + catálogo do canal pos (`CatalogService.get_sellable_products` → itens c/
  preço-em-contexto + disponibilidade-em-contexto). **Um shape de tile só** (mesma disciplina do card do
  storefront — sem 2º shape).
- **Presentation:**
  - **Grade de produtos** image-forward + **rail de categorias** (já temos) — e, a avaliar no shell,
    **tiles de AÇÃO na grade** (venda avulsa, desconto), estilo Smart Grid.
  - **Ticket/comanda** (lado Odoo-fiel) com linhas, qtd, total; **teclado→qtd** + **numpad inline**
    (`PosNumpad`, já temos); autosave serial.
  - **Multi-select de linhas** (novo, Shopify v11): aplicar desconto/remoção/fire a várias linhas — forte
    pra balcão. As ações em lote são `Action`s com `payload` multi-ref.
  - **Rail vertical de funções** (a avaliar no shell, Shopify): lock/caixa/conectividade/board a 1 toque.
- **Comando:** ops de sessão (`add_line`/`set_qty`/`remove_line`/`replace_sku`/`merge_lines`) via
  `shop.services.pos` (que chama `ModifyService`). **Idempotente.** O Nuxt emite a op; o orquestrador
  resolve modifiers/validators/checks.
- **Cliente:** adicionar/criar cliente inline (Shopify: "ação comum e sensível a tempo") — busca
  Guestman por nome/telefone; `find_or_create_customer`.

### 2.3 Comanda / mesas (move_lines)
- **Projection:** mapa de comandas abertas (handles), linhas por comanda, `actions[]` (transferir/
  dividir/juntar). `move_lines` congela preço.
- **Presentation:** seleção de comanda destino, split por linha/qtd, merge. Confirmação via `Action`.

### 2.4 Pagamento (estilo Odoo)
- **Projection:** `payment_status`/pos payment (métodos do canal via `ChannelConfig.payment`, total,
  troco, split tender, entrada/sinal) + `actions[]` (registrar pagamento, finalizar). PIX-first BR
  (payman + adapters).
- **Presentation:** tela de pagamento dedicada (não gaveta) — métodos com alvos grandes, **numpad p/
  dinheiro/troco**, split tender, prova de pagamento. Fluxo contínuo (Shopify "single continuous flow").
- **Comando:** `close_sale`/registrar pagamento via `shop.services.pos` → `CommitService.commit` (Session
  →Order) → lifecycle dispara o saga (hold/payment/KDS/fiscal/notify) por `ChannelConfig`. **A tela não
  orquestra** — emite o comando idempotente.

### 2.5 Fire-to-kitchen
- **Projection:** linhas firáveis vs `fired_lines` + `actions[]` (fire/unfire/cancel fired). Aviso
  inequívoco do estado da cozinha (já entregue no atual).
- **Presentation:** botão fire progressivo; estado visual claro do que já foi pra cozinha.
- **Comando:** `kds.fire_lines`/`unfire`/`cancel_fired` via `shop.services`.

### 2.6 Caixa / fechamento (cego)
- **Projection:** estado do caixa (aberto/fechado), movimentos (sangria/suprimento), **sem o esperado**
  (caixa cego); `actions[]` (abrir/fechar/sangrar/suprir).
- **Presentation:** abertura/fechamento, contagem cega, sangria/suprimento. Relatório de turno fica no
  **backoffice** (Unfold), não no PDV (ver 07-spec-backoffice).

## 3. Cross-cutting (config-driven, não hardcoded)
- **Schema POS compartilhado (mata a dupla manutenção):** o payload de ops POS é **gerado do contrato**
  — uma fonte de verdade. Hoje `posIntent.ts::buildPosSaleIntent` (cliente) e
  `shop/services/pos.py::build_session_ops` (servidor) reconstroem o mesmo `intent_version v1` à mão,
  sync frágil. **Alvo:** tipos TS gerados do schema do contrato (a `Action.payload_schema` é a âncora).
- **Manager-approval:** `requires_manager_approval` por permissão (ChannelConfig/RuleConfig), PIN doorman.
- **Copy:** `OmotenashiCopy` (avisos, confirmações, toasts) — zero string PT-BR no Nuxt.
- **Branding:** `Shop` tokens.
- **Comportamento:** `ChannelConfig` do canal pos (confirmation/payment/stock scope/editing).

## 4. O que o PDV NÃO faz (anti-frankenstein)
- **Não monta HTML em f-string** numa view Django (mata `backstage/views/pos.py:130-251`, 40 f-strings).
  O PDV é Nuxt consumindo Projection+Action — não há HTML-em-Python no caminho POS.
- **Não calcula preço/desconto/disponibilidade** no cliente (consome a Projection).
- **Não reconstrói o payload à mão** dos dois lados (schema gerado, fonte única).
- **Não decide lifecycle/transição** (emite comando idempotente; orquestrador decide).
- **Não duplica lifecycle** (`next_status` é single-source no orquestrador).
- **Não tem payload-de-UI no orquestrador** além da Projection: o `shop/services/pos.py` (2.179 ln)
  mantém commit/orquestração; o **payload-de-UI sai pra `shop/projections/pos.py`** (Projection de dado),
  e o shape de tela vive no Nuxt (Presentation). Ver split S4 da arquitetura.

## 5. Conserto concreto (do audit → para a superfície limpa)
1. **POS-HTMX para de montar HTML** (`backstage/views/pos.py` 40 f-strings) → consome a Projection +
   `Action[]` que a `projections/pos.py` já publica (hoje 20 ações ignoradas pela tela). A tela vira
   casca sobre o contrato.
2. **Schema POS compartilhado** (gerar tipos) → mata a dupla manutenção `posIntent.ts` ↔ `build_session_ops`.
3. **Recortar `shop/services/pos.py`** (2.179 ln): payload-de-UI → `shop/projections/pos.py`;
   commit/orquestração fica no service (write-side). [split S4]
4. **Lifecycle único:** PDV/backstage consomem `operator_orders.next_status_for` (não duplicar).
5. **Um transporte de comando:** a REST `backstage/api/operations` + `Action` — o mesmo que admin/agentic.

## 6. Decisões adiadas para a fase de shell (D2/D3 — não bloqueiam esta spec)
- **D2 — Layout:** cart-à-direita (Shopify) vs ticket-à-esquerda (Odoo, nosso atual). **Adiado** — é
  apresentação, trocável sem tocar dado/política (3 camadas). Resolver com a equipe Nelson (muscle-memory).
- **D3 — Impressão Ubuntu:** kiosk-printing / WebSerial+ESC-POS / ePOS-Print de rede. **Prototipar na
  fase de PDV.** Web/Nuxt mantido (multi-plataforma, contrato único, PWA app-like).
- **Tiles-de-ação-na-grade** + **rail vertical de funções** + **multi-select**: avaliar feel no shell.
- **Customer-facing display** (brand theming idle/checkout): futuro.

## 7. Alavancas do Core que o PDV consome (referência)
- Comanda/sessão: `sessions` (get-or-open por handle), `ModifyService.modify_session`/`move_lines`,
  `CommitService.commit` (idempotency_key). Refs: date_sequence (comandas).
- Disponibilidade: `availability_for_skus` + scope do canal pos (`excluded_positions` = D-1 staff-only).
- Catálogo/preço: `CatalogService.get_sellable_products`/`get_price` (preço-em-contexto).
- KDS: `kds.fire_lines`/`unfire`/`cancel_tickets`.
- Pagamento: payman + adapters (PIX-first); `payment_status`.
- Auth/operador: doorman `PinCredential` (`verify_operator_pin`/`verify_manager_pin`),
  `backstage/services/operator.py`.
- Caixa: `CashRegister*` (backstage models).
- Config/copy: `ChannelConfig` (canal pos), `OmotenashiCopy`, `Shop` branding.
