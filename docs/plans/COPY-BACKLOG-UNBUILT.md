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
- **Ponto de fiação confirmado:** o 409 de escassez (`surface.py`) já carrega `is_planned` **e**
  `planned_target_date`; o `SubstituteSheet.vue` recebe `cartIssue.is_planned` mas não usa. Itens
  `planned_ok` são addable (criam planned-hold); "Me avise" só aparece em `unavailable`.
- **⚠️ É FEATURE, não fiação de copy.** Precisa de:
  1. Backend: uma ação "reservar planejado" (adicionar a qtd pedida como planned-hold para
     `planned_target_date`, além do `set_available_qty` que só pega o disponível-agora).
  2. Front: no `SubstituteSheet`, quando `is_planned`, trocar o enquadramento para
     `KINTSUGI_PLANNED_OFFER` ("A caminho. O próximo lote sai em breve. Quer pré-reservar?") +
     ação "Pré-reservar" que chama a ação nova e leva ao checkout com a data pré-selecionada.
  3. Checkout: pré-selecionar `planned_target_date` (a pré-encomenda já valida datas futuras).
- **Status:** aprovada, especificada, **pendente de build focado** (toca carrinho+checkout;
  não faço sozinho/remoto sem fingir ação inexistente).

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
