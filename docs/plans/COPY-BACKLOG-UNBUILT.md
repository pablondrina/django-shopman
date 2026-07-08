# COPY-BACKLOG — features especificadas: onde deveriam estar fiadas

Arqueologia (2026-07-07, a pedido do Pablo): cada copy "sem tela" foi rastreada até o
**ponto de fiação pretendido** (git blame do commit de origem + rastro de implementação).
Resultado: nenhuma é "ideia solta" — todas têm um lugar de origem. Classificação afinada:

## 🔧 Fiação droppada (feature construída, só faltou conectar) — DÁ PARA COMPLETAR

### Indicador "também avisamos por um canal ativo" no **tracking**
- **Chaves:** `TRACKING_PROMISE_*_ACTIVE_NOTIFICATION` (ready-pickup, ready-delivery, payment, active-update).
- **Achado:** a projection tem o campo `active_notification` + o bool `requires_active_notification`;
  a **página de pagamento popula e renderiza** (`payment.py` resolve `PAYMENT_PROMISE_*_ACTIVE_NOTIFICATION`;
  `pagamento.vue:294` mostra num alerta "Status"). No **tracking**, `_promise_copy` retorna
  `active_notification` **sempre vazio** e o `index.vue` nunca renderizou. A feature existe inteira
  no pagamento e ficou pela metade no tracking.
- **Onde fiar:** popular `active_notification` em `_promise_copy` (order_tracking.py) por estado,
  a partir das chaves `TRACKING_PROMISE_*_ACTIVE_NOTIFICATION`, respeitando `requires_active_notification`;
  renderizar em `pedido/[ref]/index.vue` (espelhando o pagamento). ⚠️ área cliente-facing (promise) —
  decisão do Pablo sobre completar.

## ↔ Supersedidas (a feature existe, com outra copy) — RECONCILIAR

### `TRACKING_DELIVERED_YOIN` ("Bom apetite. Até a próxima.")
- **Achado:** o estado terminal `delivered` já usa `TRACKING_PROMISE_DELIVERED_MESSAGE`
  ("Bom apetite! Esperamos você de novo em breve."). O YOIN é uma variante duplicada da mesma
  mensagem de despedida. → consolidar (adotar o melhor texto numa chave, remover a outra).

### `BIRTHDAY_BANNER_*` ("Feliz aniversário!")
- **Achado:** a home tem um **slide de aniversário** no hero (`HomeHeroThing.vue`, copy
  `birthday_heading`/`birthday_sub`/`birthday_cta` = "Um cuidado especial hoje"). O banner é uma
  copy alternativa não usada. → decidir consolidar no slide do hero ou usar como banner separado.

## ⚠️ Decisão de produto (feature não reconstruída no Nuxt)

### Tela de **confirmação/celebração pós-pedido** — `CONFIRMATION_*`
- **Achado:** foi fiada em `templates/storefront/order_confirmation.html` (Django, commit
  `ea0db46e` "copy registry + email templates"), **removida no cutover headless** e **não
  reconstruída** no Nuxt. Copy: "Ótimo começo de dia" / "Você encomendou" / **"Compartilhar"**.
  Hoje o fluxo é checkout → pagamento → tracking, sem tela de confirmação.
- **Decisão:** reconstruir a tela de confirmação (com compartilhamento) no Nuxt, ou arquivar
  conscientemente? Era uma tela real; sumiu no cutover.

### **Pré-reserva** de lote — `KINTSUGI_PLANNED_OFFER` ("Quer pré-reservar?")
- **Decisão do Pablo (2026-07-07):** opção **(a)** — pré-reservar = adicionar o item e fechar
  para a **data futura** (reusa a pré-encomenda existente). E conceitualmente: pré-reserva é o
  affordance **principal** (padaria assa todo dia → planejado é a norma); **"Me avise" fica como
  fallback** para `unavailable` sem plano (item descontinuado/sem data). Não obsoleta, demove.
- **Achado real (investigação 2026-07-08, com arquivo:linha) — corrige imprecisão anterior:**
  a máquina de pré-encomenda **já existe e funciona**. O Core cria planned-hold com data futura
  (`packages/stockman/.../holds.py:85`, teste `test_planned_holds.py:27`) e o **checkout com data
  futura JÁ cria planned-holds** no commit (`shop/services/stock.py:hold(order)`, `target_date =
  get_commitment_date(order)`, linhas 66-131). **NÃO precisa inventar hold novo.** O que falta:
  o caminho do **carrinho descarta `target_date`** (`shop/services/cart.py:322` passa `None` →
  reserva contra hoje), o **409 nunca preenche `planned_target_date`** (sempre `is_planned=false`
  no carrinho; o `true` dos testes é mock), e o **projection do produto não expõe a data do
  próximo lote** (só `availability:'planned_ok'`). O botão "Pré-reservar N" do `SubstituteSheet`
  hoje é **fachada**: chama `acceptAvailableQty()` (`useCartState.ts:335`) = disponível-AGORA.
- **Decisão do Pablo (2026-07-08): REAPROVEITAR A PRÉ-ENCOMENDA.** Em vez de reserva-por-linha no
  add-to-cart, o "Pré-reservar" grava `delivery_date` = próximo lote e leva ao checkout; o commit
  já cria os planned-holds (caminho testado). Escopo mínimo:
  1. **Backend (pequeno):** expor a **data do próximo lote** ao front para itens `planned_ok`
     (surfacer a próxima data disponível — no projection do produto e/ou no payload do 409).
  2. **Front:** no `SubstituteSheet` (e/ou no card/PDP), quando `planned_ok`, enquadrar com
     `KINTSUGI_PLANNED_OFFER` + ação "Pré-reservar" que grava `session.data["delivery_date"]` =
     próximo lote e roteia ao checkout (a pré-encomenda já valida datas futuras).
  3. **Zero** código novo de hold — o commit já faz.
- **Status:** aprovada + semântica travada (reuso). Pendente de build focado.

### Perfil — resíduo do modo **"ler-depois-editar"** — `PROFILE_EDIT_CTA` · `PROFILE_MISSING_VALUE` · `PROFILE_NAME_FIELD`
- **Achado:** o registro descrevia um **cartão de leitura** do perfil (rótulo: valor,
  **"Não informado"** nos vazios) com botão **"Editar"**. A tela `conta/perfil.vue` no ar é um
  **formulário sempre-editável** com nome **dividido**, que **substituiu** aquele design.
- **Decisão do Pablo (2026-07-08, revisão linha a linha A/B):** nome **dividido** confirmado.
  **Religados** via `ProfileView._profile_copy()`: os 4 campos editáveis
  (`PROFILE_FIRST_NAME_FIELD`/`LAST_NAME_FIELD`/`EMAIL_FIELD`/`BIRTHDAY_FIELD` — E-mail e
  Aniversário), o título de seção **"Dados pessoais"** (`PROFILE_SECTION_TITLE`), o convite
  humano **"Como quer ser chamado?"** (`PROFILE_NAME_LABEL`, sobre o par de nome) e o rótulo
  **"Telefone"** (`PROFILE_PHONE_FIELD`).
- **Resíduo (3 chaves) → backlog:** `PROFILE_EDIT_CTA` ("Editar"), `PROFILE_MISSING_VALUE`
  ("Não informado") e `PROFILE_NAME_FIELD` ("Nome" único) só fazem sentido no **modo leitura**
  não construído (form sempre-editável não tem estado vazio nem botão Editar; nome é dividido).
- **Status:** aguarda visão do Pablo — construir o modo leitura+editar (com o nudge "Não
  informado") ou aposentar as 3. Seguem no registro e no `copy-wiring-backlog.txt`.

> Nada disto se deleta sem sua aprovação. As chaves seguem no registro e no
> `copy-wiring-backlog.txt`. Cada decisão vira fiação (via projection) ou arquivamento explícito.
