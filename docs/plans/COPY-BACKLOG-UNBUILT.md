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

### Perfil **"ler-depois-editar"** — `PROFILE_SECTION_TITLE` · `PROFILE_EDIT_CTA` · `PROFILE_NAME_FIELD` · `PROFILE_PHONE_FIELD` · `PROFILE_MISSING_VALUE` · `PROFILE_NAME_LABEL`
- **Achado:** o registro descreve um **cartão de leitura** do perfil (rótulo: valor,
  **"Não informado"** nos vazios) com botão **"Editar"** e o convite humano
  **"Como quer ser chamado?"** (`PROFILE_NAME_LABEL`) + nome **único** (`PROFILE_NAME_FIELD`
  = "Nome"). A tela `conta/perfil.vue` no ar é um **formulário sempre-editável** com nome
  **dividido** (Primeiro nome + Sobrenome), que **substituiu** aquele design.
- **Decisão do Pablo (2026-07-08):** nome **dividido** confirmado; os 4 labels editáveis
  (`PROFILE_FIRST_NAME_FIELD`/`LAST_NAME_FIELD`/`EMAIL_FIELD`/`BIRTHDAY_FIELD`, com E-mail e
  Aniversário) **religados** via `ProfileView._profile_copy()`. As 6 chaves acima descrevem o
  modo leitura **não construído** → **backlog** (não apagar; a intenção omotenashi é boa,
  sobretudo o "Como quer ser chamado?" e o nudge "Não informado").
- **Status:** aguarda visão do Pablo — construir o modo leitura+editar (toca a UX da tela) ou
  arquivar conscientemente. Enquanto isso, seguem no registro e no `copy-wiring-backlog.txt`.

> Nada disto se deleta sem sua aprovação. As chaves seguem no registro e no
> `copy-wiring-backlog.txt`. Cada decisão vira fiação (via projection) ou arquivamento explícito.
