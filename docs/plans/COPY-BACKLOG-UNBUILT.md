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
- **Achado:** o modal kintsugi de erro de estoque foi construído (`SubstituteSheet.vue`, WP-GAP-14,
  "3 variants + substitutes"). O cart tem planned-hold (`is_awaiting_confirmation`). A variante
  **pré-reserva** ("A caminho / O próximo lote sai em breve. Quer pré-reservar?") ficou sem fiar —
  o ponto seria o fluxo de item planejado/indisponível (overlap com "Me avise"/notify).
- **Decisão:** pré-reserva é feature distinta do "Me avise" ou o mesmo? Construir onde?

> Nada disto se deleta sem sua aprovação. As chaves seguem no registro e no
> `copy-wiring-backlog.txt`. Cada decisão vira fiação (via projection) ou arquivamento explícito.
