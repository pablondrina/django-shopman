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

### ✅ `TRACKING_DELIVERED_YOIN` ("Bom apetite. Até a próxima.") — FIADA (2026-07-08)
- O estado `delivered` renderizava por `TRACKING_PROMISE_DELIVERED_MESSAGE` (chave que nem
  existia no registro — só fallback no código). Repontado para `TRACKING_DELIVERED_YOIN`
  (`order_tracking.py`): a despedida do `delivered` agora é a yoin, configurável no registro.

### ✅ `BIRTHDAY_BANNER_*` — CONSOLIDADO no hero (2026-07-08)
- Eram duplicatas órfãs do slide de aniversário do hero (`BIRTHDAY_HERO_HEADING`/`_SUB`, usados
  em `home.py`). O "!" do banner foi adotado no `BIRTHDAY_HERO_HEADING` ("Feliz aniversário!") e
  as chaves `BIRTHDAY_BANNER_TITLE`/`_SUB` foram removidas do registro (o hero é o único lugar
  do aniversário). Sub do hero mantém o desconto (a informação acionável).

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
- **✅ CONSTRUÍDO (2026-07-08, decisão do Pablo "vamos completar"):** o Perfil agora abre em
  **modo leitura** (cartão rótulo:valor, com **"Não informado"** nos vazios via
  `PROFILE_MISSING_VALUE`; nome único via `PROFILE_NAME_FIELD`) + botão **"Editar"**
  (`PROFILE_EDIT_CTA`) que revela o formulário. As 3 chaves saíram do backlog. Balde B do
  Perfil fechado — todas as chaves `PROFILE_*` agora chegam à tela.

## 🙈 Ausência que não vale anunciar (esconder > avisar)

### `LOYALTY_UNAVAILABLE` ("Programa de fidelidade não disponível.")
- **Achado:** a chave existe só para **afirmar a ausência** do programa de fidelidade. Hoje a
  vitrine de fidelidade (`conta/index.vue`, `home`) some quando `loyalty.available` é falso
  (`v-if`). Quando um programa é configurado, ela aparece sozinha — nada mais a fazer.
- **Decisão do Pablo (2026-07-09, revisão A/B da conta/index):** **não construir.** Avisar que
  uma feature não existe é ruído (ninguém sente falta do que não sabia que existia). O
  esconder-quando-indisponível é o comportamento certo. A chave fica arquivada — se um dia
  quisermos um estado explícito, está aqui.
- **Status:** arquivada como decisão consciente. Segue no registro **e no
  `copy-wiring-backlog.txt`** (continua órfã: a copy não chega a tela alguma — de propósito).

### `NOTIFICATION_PREFS_EMPTY` ("Nenhuma preferência de notificação configurável no momento.")
- **Achado:** a chave existe, mas `conta/preferencias.vue` **não tem estado-vazio** — a página
  só renderiza os toggles de notificação (`v-for`); se a lista vier vazia, a seção some sem
  mensagem. "Religar" exigiria **construir uma UI nova** (um bloco `UiEmpty` de notificações),
  não reconectar um texto já em tela.
- **Decisão do Pablo (2026-07-09, revisão A/B das sub-páginas da conta):** **documentar, não
  deletar.** Um empty-state de notificações é uma tela plausível de construir depois e a frase
  já rascunhada é copy boa para reaproveitar. Não vale inventar UI que ninguém pediu agora.
- **Status:** arquivada. Segue no registro **e no `copy-wiring-backlog.txt`** (órfã de propósito
  — sem tela). Quando/se o empty-state de notificações for construído, ligar via projection.

## 🙈 Tracking — superseded/duplicadas (decisão Pablo 2026-07-09, revisão caso-a-caso)

O acompanhamento já resolve 80+ chaves via `build_copy("TRACKING")`. Destas órfãs, umas
duplicam copy já fiada, outras descrevem um design que a tela não usa. Arquivadas (seguem
no registro e no `copy-wiring-backlog.txt` — órfãs de propósito):

- `TRACKING_PROMISE_LABEL_ACTION` ("Sua ação:") — a ação é **botão**, não linha (`_build_promise_rows`
  é deliberadamente enxuto). Sem linha de ação.
- `TRACKING_PROMISE_LABEL_UPDATED` ("Última atualização:") — a tela mostra *"Atualizado há X"*
  (tempo vivo relativo, `freshness.text`), melhor que um prefixo estático.
- `TRACKING_ETA_PREFIX` ("Previsão para ficar pronto às") — a ETA já vem **embutida na mensagem**
  do estado ("Fica pronto por volta das {eta}"), não há linha de ETA separada.
- `TRACKING_ACTION_NONE` ("Nenhuma ação necessária") / `TRACKING_ACTION_WAITING_COURIER`
  ("Aguardando entregador") — labels de estado de ação; as ações são botões específicos por estado.
- `TRACKING_PAYMENT_CONFIRMED` ("Recebemos a confirmação do pagamento deste pedido.") — duplica
  `TRACKING_PAYMENT_CONFIRMED_NOTICE` (fiada: "Pagamento confirmado. Acompanhe o próximo passo…").
- `TRACKING_PROMISE_PAYMENT_CONFIRMED_MESSAGE` ("Nenhuma ação necessária agora.") — superseded pelas
  mensagens por status `TRACKING_PROMISE_PAYMENT_CONFIRMED_MESSAGE_NEW/_CONFIRMED` (fiadas).

**Ainda no backlog p/ follow-up focado (mudam a estrutura do countdown/freshness, não é swap de
string):** `TRACKING_AUTO_CONFIRM_PREFIX/SUFFIX` (enquadrar o countdown de disponibilidade),
`TRACKING_PAYMENT_TIME_LEFT` (rótulo do countdown de pagamento por contexto), `TRACKING_PROMISE_STALE`
(mensagem quando o poll falha, no composable de frescor), `TRACKING_PROMISE_AVAILABILITY_RECOVERY` +
`TRACKING_PROMISE_RECOVERY_HELP` (preencher o slot `recovery` por estado).

> Nada disto se deleta sem sua aprovação. As chaves seguem no registro e no
> `copy-wiring-backlog.txt`. Cada decisão vira fiação (via projection) ou arquivamento explícito.

## 🙈 Pagamento — superseded pelo painel `promise` (decisão Pablo 2026-07-09, revisão da tela)

A tela `/pagamento` (`pedido/[ref]/pagamento.vue`) tem o **painel de status fiado via
`payment.promise.*`** (resolvido em `presentation/payment.py` por estado: pix/cartão/pago/
cancelado/expirado/erro). O chrome estático + UI de PIX/cartão foi religado (canal `copy` na
`OrderPaymentView`, 10 chaves). Estas 13 descrevem estados que o `promise` **já resolve** ou
telas que a UI **não usa** — arquivadas (seguem no registro e no `copy-wiring-backlog.txt`,
órfãs de propósito):

- `PAYMENT_WAITING` ("Aguardando seu banco confirmar…") / `PAYMENT_WAITING_LONG` ("Ainda
  processando…") — o estado de espera é a **mensagem do promise**, não uma linha à parte.
- `PAYMENT_CONFIRMED` ("Pagamento recebido" / "Seguimos com o preparo…") — = `PAYMENT_PROMISE_PAID_*`.
- `PAYMENT_CANCELLED` ("Pedido cancelado") + `PAYMENT_CANCELLED_DETAILS_CTA` ("Ver detalhes") —
  = `PAYMENT_PROMISE_CANCELLED_*` + ações do promise.
- `PAYMENT_ERROR_TITLE` / `PAYMENT_ERROR_MESSAGE` — a tela usa `errorView` (orderAccess) para acesso
  e `payment.error_message` (do gateway) para falha de intent; estas chaves não são as usadas.
- `PAYMENT_PIX_EXPIRED` ("Este PIX expirou" / "Geramos um novo…") — o terminal expirado vem do
  promise; o inline "O prazo do PIX expirou." cobre o countdown.
- `PAYMENT_PIX_REGENERATE_CTA` ("Gerar novo PIX") — é **ação** do promise (label vem da action).
- `PAYMENT_DEADLINE_NOTICE` ("Conclua dentro do prazo indicado abaixo.") — sem aviso separado; o
  countdown com barra fala por si.
- `PAYMENT_REDIRECTING_PREFIX` ("Redirecionando em") / `PAYMENT_REDIRECTING_SUFFIX` ("s…") — não há
  countdown de redirect na UI; o `watchEffect` navega direto quando há `redirect_url`.
- `PAYMENT_PAGE_TITLE` ("Concluir pagamento") — a tela usa título dinâmico por pedido
  ("Pagamento {ref}"), mais informativo que o estático.

> Se algum estado ganhar tela própria no futuro (ex.: aviso de deadline dedicado), ligar via a
> projection ao registro. Nada se deleta sem aprovação.

## 🙈 Menu — subtítulo sem lugar no design filter-first (decisão Pablo 2026-07-10)

### `MENU_SUBTITLE` (6 variantes por momento: madrugada/manhã/almoço/tarde/fechando/fechado)
- **Achado:** copy boa de subtítulo por horário ("Fresquinho do forno.", "Para o café da tarde.",
  "Olhe à vontade. Atendemos assim que abrirmos."), mas `menu.vue` **não tem header de página** —
  o `h1 "Cardápio"` é `sr-only` e a tela vai direto pra barra de filtro (`sticky top-16`) + headers
  **por seção** (`section.description`, ex.: "Os mais vendidos e curados pela casa."). O subtítulo
  de página moraria numa faixa nova acima do filtro.
- **Decisão do Pablo (2026-07-10, revisão A/B com mockup lado a lado):** **arquivar.** O menu é
  enxuto filter-first de propósito; um header de página empurra o catálogo pra baixo. A copy fica
  guardada — se um dia o menu ganhar um header, ligar via a projection do menu (`/api/v1/storefront/menu/`)
  resolvendo `MENU_SUBTITLE` por momento.
- **Status (2026-07-10):** arquivada, mantida no registro. **Superseded pela decisão definitiva de
  2026-07-11** (ver a seção "arquivamento definitivo" abaixo): a chave foi removida do registro para
  zerar o backlog.

## 🙈 Kintsugi — superseded ou sem touchpoint limpo (decisão autônoma 2026-07-10, Pablo pediu "fazer tudo")

A família `KINTSUGI_*` (copy de erro/degradação) tem 5 fluxos. **4 chaves religadas**
(`SHORTAGE_GENERIC`, `SHORTAGE_SUBSTITUTES_INTRO`, `PAUSED_COPY` via `_stock_error_payload`;
`CANCEL_REFUSED` via `execute_cancel`). Estas **6 ficam arquivadas** — cada uma por um motivo
concreto, não por preguiça. Todas seguem no registro e no `copy-wiring-backlog.txt`:

- `KINTSUGI_ITEM_REMOVED` ("Removido.") — **superseded**: o toast real ao remover é
  `"{nome} removido"` (`sacola.vue`), específico e melhor que o genérico. Nada a ganhar.
- `KINTSUGI_CEP_NOT_FOUND` ("Não encontrei esse CEP. Quer digitar o endereço?") — o CEP é buscado
  **client-side direto no ViaCEP** (`AddressPicker.vue`, sem passar pelo Django) e o "não
  encontrado" hoje é **silencioso** (o dropdown só não abre). Religar exigiria (a) UI nova de
  "não encontrado" e (b) um canal de copy pro componente — que é **compartilhado com o checkout
  da mãe** (`finalizar.vue`). Risco desproporcional pra um edge (Places é o buscador primário).
  Reavaliar se o CEP migrar pro servidor (`geocode.py`).
- `KINTSUGI_RATE_LIMITED` + `_CONTACT` + `_RETRY_CTA` + `_RETRY_PREFIX` — descrevem um **painel
  estruturado genérico** (título + mensagem + "prefere falar conosco?" + botão retry + countdown).
  O storefront hoje usa mensagens **context-specific** ("Muitas tentativas de recompra" vs "Muitas
  alterações na sacola", `surface.py`) num alert flat (`sacola.vue`, título "Aguarde um instante").
  As específicas são **melhores** que a genérica; o painel estruturado não existe. Religar seria
  downgrade + UI nova. Se um dia quiser unificar o rate-limit num painel omotenashi com escape
  pra WhatsApp, as 4 chaves estão prontas.

> ⚠️ Decisões autônomas reversíveis: se o Pablo quiser a mensagem genérica de rate-limit (com o
> escape pra WhatsApp) ou o aviso de CEP construídos mesmo assim, é só pedir.

### `TRACKING_PROMISE_RECOVERY_HELP` ("Se precisar de ajuda, fale com o estabelecimento.")
- **Achado:** o slot `recovery` do tracking vira uma row rotulada **"Se o tempo acabar:"**
  (`TRACKING_PROMISE_LABEL_RECOVERY`, em `_build_promise_rows`) — um safety-net de deadline.
  `RECOVERY_HELP` **não é sobre tempo acabar** (é ajuda genérica), então não cabe nesse rótulo; e
  a tela já tem o CTA **"Fale conosco"** em destaque no painel pra esse fim.
- **Decisão (2026-07-10):** arquivar — semanticamente não encaixa na row de recovery (deadline) e
  seria redundante com o CTA de suporte. A gêmea `TRACKING_PROMISE_AVAILABILITY_RECOVERY` (que É
  sobre deadline) foi religada no estado `availability_check`.
- **Status:** arquivada. Segue no registro e no `copy-wiring-backlog.txt` (órfã de propósito).

## 🧹 Varredura do backlog restante (decisão autônoma 2026-07-10, "siga!")

Triado o que sobrava. Nenhuma era wire limpo de alto valor (ao contrário do item 2):
não há bug de copy a corrigir; todas são superseded, client-only, backstage, da mãe, ou
já-melhores-na-tela. Cada uma abaixo segue órfã de propósito no `copy-wiring-backlog.txt`.

**Superseded por chave dinâmica já fiada:**
- `PRODUCT_OUT_OF_STOCK` / `PRODUCT_SCHEDULED_UNAVAILABLE` ("Indisponível") — o badge de
  disponibilidade vem de `availability_label()` → `AVAILABILITY_{estado}` (prefixo dinâmico, sempre
  alcançável). Estas duas duplicam o conceito; nunca são lidas.

**Client-only (sem servidor no momento):**
- `OFFLINE_TITLE` / `OFFLINE_MESSAGE` / `OFFLINE_RETRY_CTA` — o `OfflineBanner.vue` dispara por
  `navigator.onLine` (offline = sem fetch de copy). Hoje é um banner mínimo auto-reconectante
  ("Sem conexão. Tentando reconectar…"), que supera a estrutura título+mensagem+retry. Copy de
  offline precisa estar embarcada no cliente; não há canal de projection viável.

**Fora do escopo storefront (operador/backstage):**
- `CLOSING_AWARENESS_PREFIX` / `_SUFFIX` / `_OLD_D1_ALERT` — renderizam em
  `backstage/projections/closing.py` (tela de fechamento do operador, D-1 = staff). Copy de
  operador, não do cliente. Se for fiar, é no burndown do backstage, não aqui.

**Fluxo de login/device-trust (território VIVO da mãe — [[project_whatsapp_access_link_pivot]]):**
- `DEVICE_TRUST_GREETING` ("Bem-vindo de volta") / `DEVICE_TRUST_ERROR` — aparecem no fluxo de
  confiar-no-dispositivo durante o LOGIN. A mãe reescreve o login inteiro; não tocar.
- `WELCOME_*` (9: greeting, name-heading×3, page-title, confirm-cta, account-note, suggested-name,
  whatsapp), `LOGIN_CHANGE_PHONE_*` (3), `LOGIN_WELCOME_BACK` — a tela `/entrar` (boas-vindas +
  trocar telefone + saudação recorrente). **DEFERIDAS à mãe**, não arquivadas por mim: ela é a dona
  dessa superfície (pivô access-link/F4). Sair do meu backlog quando ela religar/consolidar.

**On-screen já melhor que o registro (baixo valor em admin-config):**
- `DEVICE_REVOKE_CONFIRM` / `DEVICE_REVOKE_ALL_CONFIRM` / `DEVICE_REVOKE_ALL_CTA` /
  `DEVICE_LIST_UNKNOWN` / `DEVICE_LIST_LAST_USED_PREFIX` — `seguranca.vue` já fia o principal via
  `_devices_copy()`; os diálogos de revoke na tela são MELHORES que os stubs do registro (separam
  título-pergunta de consequência e interpolam o nome do aparelho). Microcopy de segurança que muda
  raramente — baixo ROI pra tornar admin-config.
- `PICKUP_READY_NOTICE` ("Avisamos quando ficar pronto.") — nota do planned-hold por linha na sacola.
  Customer-facing e a copy é boa, mas o projection do carrinho não tem canal `copy`; wire exigiria
  infra nova pra uma copy que já está certa.

> ⚠️ Reversível: se o Pablo quiser admin-config de qualquer uma (ex.: PICKUP_READY_NOTICE ou os
> diálogos de revoke), é só pedir e eu abro o canal de copy no projection correspondente. As de
> login saem sozinhas quando a mãe fechar o `/entrar`.

## 🙈 Login (`WELCOME_*`/`LOGIN_*`) — superseded pelo canal `auth_copy` da mãe (2026-07-10)

**Resolvido.** O loop acima ("saem quando a mãe fechar o /entrar") fechou: a mãe mergeou o pivô
access-link (#45) e **reescreveu a copy de login com o próprio canal `auth_copy`** — `_auth_copy()`
em `shopman/storefront/presentation/home.py` resolve ~24 chaves **`LOGIN_*`/`DEVICE_TRUST_*`** novas
(`LOGIN_PHONE_HEADING`, `LOGIN_NAME_HEADING`, `LOGIN_CODE_HELP`, `LOGIN_AUTH_CONFIRMED`, `LOGIN_WA_*`…),
consumidas em `entrar.vue` via `copyTitle(authCopy.X, fallback)`. O login **já é registro-driven**.

As 13 chaves órfãs antigas ficaram **duplicatas mortas** — arquivadas (seguem órfãs de propósito no
`copy-wiring-backlog.txt`):
- `WELCOME_NAME_HEADING` (+ `_PREFIX`/`_SUFFIX`) → superseded por `LOGIN_NAME_HEADING`.
- `WELCOME_CONFIRM_CTA` → superseded por `LOGIN_NAME_CTA`.
- `WELCOME_GREETING` / `WELCOME_PAGE_TITLE` / `WELCOME_ACCOUNT_NOTE` / `WELCOME_SUGGESTED_NAME_MESSAGE`
  / `WELCOME_WHATSAPP` → superseded pelo fluxo enxuto novo (headings por passo + `LOGIN_AUTH_CONFIRMED`),
  ou UI que o fluxo não tem mais.
- `LOGIN_WELCOME_BACK` → superseded por `LOGIN_AUTH_CONFIRMED` ("confirmação automática").
- `LOGIN_CHANGE_PHONE_TITLE` / `_MESSAGE` → descrevem um **diálogo de confirmação que o fluxo enxuto
  não tem** (o "Trocar telefone" só volta pro passo do telefone, sem diálogo).
- `LOGIN_CHANGE_PHONE_CTA` ("Trocar telefone") → ✅ **RELIGADA** (2026-07-11, a pedido do Pablo): era o
  único resíduo hardcoded no `entrar.vue`. Adicionado `change_phone_cta` ao `_auth_copy()` (home.py) +
  dataclass/tipo, consumido via `copyTitle(authCopy?.change_phone_cta, 'Trocar telefone')`. Saiu do backlog.

> Fecha o item A: toda `WELCOME_*`/`LOGIN_*` agora está religada (pela mãe, ou `change_phone_cta` por mim)
> ou arquivada como superseded. **Zero resíduo hardcoded.**

## 🍞 `MENU_SUBTITLE` — arquivamento definitivo (decisão do Pablo, 2026-07-11)

**Arquivada e REMOVIDA do registro.** A chave descrevia um subtítulo do cardápio momento-aware
(6 variantes: madrugada/manhã/almoço/tarde/fechando/fechado). Não era religação — `menu.vue` tinha
só um `h1` sr-only e **nenhum slot de subtítulo**, e a projection do catálogo não entregava campo de
copy. Era **feature nova** (um header de página acima do filtro sticky).

**Decisão (2026-07-11, confirmando a revisão A/B de 2026-07-10): arquivar definitivo.** O cardápio é
filter-first de propósito — na loja mobile-first, o acima-da-dobra é para produto, e uma faixa de
saudação competiria com o filtro sticky (`sticky top-16`) empurrando o catálogo para baixo. A
calorosidade omotenashi já é entregue onde melhor cai: hero da home (momento-aware), `CART_EMPTY`
(momento-aware) e os headers de seção com voz curada. O menu é superfície de tarefa, não de saudação.

**Diferença desta vez:** o arquivamento anterior mantinha a chave no registro como órfã-de-propósito,
mas o guardrail `test_copy_wiring_backlog` **só tolera órfã que esteja no backlog** — manter no registro
E zerar o backlog é impossível. Como a decisão é definitiva, a chave saiu de `shopman/shop/omotenashi/copy.py`
por inteiro (zero resíduo). As 5 referências em teste (`test_omotenashi_tag.py`, `test_omotenashi.py`) — que
usavam `MENU_SUBTITLE` só como cobaia de infra do tag — foram repontadas para `CART_EMPTY` (outra chave com
variantes por momento). **Backlog de copy = ZERO.**

Se um dia o menu ganhar um header de página, a copy está preservada no git (commit deste arquivamento):
recriar as 6 variantes no registro e ligar via a projection do menu (`/api/v1/storefront/menu/`) resolvendo
por momento/audiência com o `OmotenashiContext` que `build_catalog()` já instancia.
