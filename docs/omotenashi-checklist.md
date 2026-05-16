# Omotenashi Checklist — Storefront v2

Aplique os **cinco testes** do framework omotenashi
([`docs/omotenashi.md`](omotenashi.md)) a cada tela. Mantenha este documento
atualizado a cada WP. Qualquer falha vira tarefa no próximo WP de kaizen.

Os cinco testes:

1. **Invisível** — o esforço está escondido? Alguém vê o resultado, não o mecanismo?
2. **Antecipação** — a pessoa precisou pedir algo que devíamos ter oferecido?
3. **Ma** — teve respiro, escolha, calma? Ou enchemos cada canto?
4. **Calor** — sentiu-se acolhida ou processada?
5. **Retorno** — sai querendo voltar?

Marque cada célula com ✓ (passa), ~ (parcial) ou ✗ (falha) + nota breve.

---

## Estado atual (após WP-OMO-1..4)

| Tela | Invisível | Antecipação | Ma | Calor | Retorno |
|---|---|---|---|---|---|
| **home.html** | ✓ hero lê hora e pessoa | ✓ temporal_context + customer_name | ✓ seções espaçadas | ✓ saudação com nome | ✓ tomorrow hook após 14h |
| **menu.html** | ✓ subtitle via omotenashi_copy | ✓ MENU_SUBTITLE varia por moment | ✓ categorias via pills | ~ pode usar audience mais | ~ card final não convida |
| **product_detail.html** | ✓ alergênico inline | ✓ PRODUCT_OUT_OF_STOCK contextual | ✓ details para conservação | ✓ accordion humano ("Alérgenos & info") | ~ cross-sell ainda comercial |
| **cart_drawer** | ✓ auto-animate nas listas | ✓ CART_EMPTY varia por moment | ✓ totais com hierarquia | ✓ cupom como pergunta | ~ continuar comprando pode ser mais caloroso |
| **cart.html** | — | — | — | — | — (herda do drawer) |
| **checkout.html** | ✓ seções numeradas | ✓ phone purpose, loyalty default, pickup/delivery hints | ✓ observações sob demanda | ✓ copy humana ("Como você quer receber?") | ~ botão submit pode celebrar mais |
| **payment.html** | ✓ QR code + copia-e-cola | ✓ countdown visível | ✓ 1 método por tela | ~ espera sem feedback → WP-OMO-3 cobriu | ~ Stripe loading genérico |
| **payment_status** | ✓ polling silencioso | ✓ PAYMENT_WAITING vira LONG após 10s | ✓ não interrompe | ✓ PAYMENT_CONFIRMED com yoin | ✓ botão "Gerar novo PIX" (kintsugi) |
| **order_tracking** | ✓ polling HTMX | ✓ ETA + countdown | ✓ abas colapsáveis | ~ status labels podem humanizar | ✓ tomorrow hook |
| **order_history** | ✓ auto-animate | ✓ HISTORY_EMPTY contextual | ✓ cards espaçados | ✓ empty state caloroso | ✓ pedir novamente |
| **login/auth** | ✓ phone mask inline | ✓ feedback DDD em tempo real | ✓ foco no campo atual | ✓ welcome toast | ✓ rate limit com timer + WhatsApp |
| **account.html** | ✓ abas | ✓ saudação personalizada | ✓ bottom-sheet | ✓ farewell toast | ~ pedidos vazios podem sugerir mais |

### Telas com pontos a amadurecer

- **menu.html** — card final pode virar um "Pronto para pedir?" quente, porém só se os 20% de clientes desejarem.
- **tracking** — humanizar status labels (preparando → "no forno"), fora do escopo imediato.

## Regras de regressão (anti-gambiarra)

- Nenhuma string hardcoded para copy que já tem chave em `OMOTENASHI_DEFAULTS`.
- Nenhuma tela deve exibir "PIX expirado" ou "CEP inválido" sem caminho de recuperação.
- Nenhuma seção de checkout ou drawer pode ter campo obrigatório sem propósito explícito.
- Toda jornada autenticada termina com yoin mínimo (toast, frase, confirmação com nome).

---

## WP-OMO-5 — Verificação detalhada por tela

Auditoria com Cinco Testes aplicados tela a tela. Legenda: ✅ Passa · ⚠️ Passa com ressalvas.

| Tela | Invisível | Antecipação | Ma | Calor | Retorno |
|------|-----------|-------------|-----|-------|---------|
| **home** | ✅ SSE silencioso, carrossel pausa on-hover | ✅ birthday banner, quick reorder, temporal_greeting | ✅ seções espaçadas, collapse/expand | ✅ nome do cliente, HTMX copy contextual | ✅ tomorrow hook, WhatsApp, tracking entry |
| **menu** | ✅ scroll-spy, busca client-side | ✅ MENU_SUBTITLE contextual, hint categoria favorita | ✅ busca x-show, categorias colapsáveis | ⚠️ reorder_skipped com "indisponível" seco | ✅ reorder hint, scroll-spy |
| **product_detail** | ✅ SSE, qty stepper com hint de máximo | ⚠️ sem "avise-me" para indisponível | ✅ accordions `<details>` para info extra | ⚠️ modal de erro de estoque sistêmico | ⚠️ sem "Veja também" |
| **cart / drawer** | ✅ progress bar mostra progresso (não meta) | ✅ upsell, PICKUP_READY_NOTICE, coupon reveal | ✅ coupon/notas via Padrão C | ✅ undo com notificação, CART_EMPTY omotenashi | ✅ checkout CTA claro, resumo inline |
| **checkout** | ✅ step machine Alpine, URL reflete step | ✅ contato sempre ✓, slots fechados ocultos, loyalty | ✅ steps progressivos, notas Padrão C | ✅ modal de nome, contato legível em mobile | ✅ summary lateral em tempo real |
| **payment** | ✅ QR + copia-e-cola, countdown | ✅ total e método exibidos antes de qualquer ação | ✅ tela focada: QR, código, countdown | ⚠️ transição "expirado" ainda fria no pix template | ⚠️ sem CTA de "enquanto aguarda" |
| **payment_status** | ✅ HTMX substitui área, x-transition | ✅ WAITING vs WAITING_LONG após 10s | ✅ spinner discreto, sem blinking alerts | ⚠️ cancelled: "Pedido cancelado" sem copy omotenashi | ✅ confirmed: link direto ao tracking |
| **order_confirmation** | ✅ `{% human_eta %}`, sem expor cálculo | ✅ ETA imediato, tomorrow hook, link tracking | ✅ celebração discreta, header limpo | ✅ nome do cliente, share CTA | ✅ share + tracking CTAs, tomorrow hook |
| **order_tracking** | ✅ SSE, countdown automático | ✅ ETA, reorder pós-entrega, tomorrow hook | ✅ timeline limpa, rating só após entrega | ✅ RATE_PROMPT/THANKS, WhatsApp, kintsugi cancel | ✅ rating hover, reorder CTA |
| **order_history** | ✅ pull-to-refresh, filtros sem reload | ✅ reorder por pedido, HISTORY_EMPTY omotenashi | ⚠️ lista densa em histórico longo | ✅ HISTORY_EMPTY acolhedor | ✅ reorder CTA, acesso ao menu |
| **account** | ✅ loyalty animado, tab indicator, bottom-sheet | ✅ stamp grid, prefs pré-preenchidas | ✅ accordions, tabs sem conteúdo simultâneo | ⚠️ "Programa indisponível" seco quando loyalty off | ✅ loyalty gamification, histórico |
| **login** | ✅ máscara de telefone automática | ✅ hero contextual por step | ✅ tela focada: só telefone ou OTP | ⚠️ "DDD inválido" / "Número longo demais" clínicos | ✅ fluxo rápido, SMS fallback |
| **welcome** | ✅ nome sugerido pré-preenchido | ✅ nome pré-preenchido, "pode ser apelido" | ✅ minimalista: ícone + heading + input + CTA | ✅ "Que bom te ver aqui!", "pode mudar depois" | ✅ onboarding rápido, sem fricção |
| **rate_limited** | ✅ countdown automático | ✅ countdown + WhatsApp alternativo | ⚠️ funcional mas sem respiro visual | ⚠️ KINTSUGI_RATE_LIMITED presente mas tom frio | ⚠️ WhatsApp como saída; humanização pendente |

### Pontos pendentes pós-WP-OMO-5

| Tela | Gap | Prioridade |
|------|-----|-----------|
| menu | Suavizar linguagem no banner `reorder_skipped` | Baixa |
| product_detail | "Me avise" quando produto voltar | Ouro (feature futura) |
| product_detail | "Veja também" — descoberta lateral | Ouro (feature futura) |
| payment | CTA "enquanto aguarda" no estado pending | Baixa |
| payment_status | Usar omotenashi copy no estado cancelled | Média |
| account | Copy warmth quando loyalty indisponível | Baixa |
| login | Suavizar mensagens de validação inline | Baixa |
| rate_limited | Copy humanizado no countdown ("Respira!") | Baixa |

---

## Cenários E2E (Plano Manual — Playwright não instalado)

### Cenário 1: Checkout completo

**Fluxo:** Anônimo → Login → Carrinho → Checkout → Pagamento → Confirmação

**Pré-condições:** loja aberta, produto disponível, usuário não autenticado.

| # | Passo | Verificação |
|---|-------|-------------|
| 1 | Acessa `/menu` | `{% temporal_greeting %}` contextual aparece |
| 2 | Adiciona produto | Drawer abre com item, total, botão checkout |
| 3 | Acessa `/checkout` sem login | Redirecionado para `/login?next=/checkout` |
| 4 | Login via OTP | Retorna ao checkout com step "Como receber" aberto |
| 5 | Seleciona Retirada | Step avança para "Quando"; "Como receber" vira resumo ✓ clicável |
| 6 | Seleciona data e horário | Step avança para "Pagamento" |
| 7 | Seleciona PIX | Resumo lateral atualiza com valor e método |
| 8 | Confirma pedido | POST → redirecionado para `/payment/<ref>/` |
| 9 | HTMX polling | Status atualiza para "Confirmado" após pagamento |
| 10 | Tracking | `/order/tracking/<ref>/` com ETA via `{% human_eta %}` |

**Gates:**
- [ ] Step inicial é "Como receber" (Contato sempre ✓)
- [ ] `?step=X` refletido na URL a cada avanço
- [ ] F5 em qualquer step restaura o step correto (popstate listener)
- [ ] Summary lateral (sidebar) atualiza em tempo real com Alpine x-text
- [ ] Botão "Confirmar pedido" aparece apenas no step Pagamento

---

### Cenário 2: PIX expirado → Regenerar → Sucesso

**Fluxo:** Pagamento pendente → PIX expira → regenera → paga

**Pré-condições:** pedido criado com PIX, expiração curta em ambiente de teste.

| # | Passo | Verificação |
|---|-------|-------------|
| 1 | Acessa `/payment/<ref>/` | Countdown visível; barra de progresso diminuindo |
| 2 | Timer chega a zero | Alpine: `timeLeft === 'expirado'` → "PIX expirado" via `x-show` |
| 3 | HTMX polling (30s) | `payment_status.html` substitui área com estado `is_expired` |
| 4 | Estado expired | `PAYMENT_PIX_EXPIRED` copy + botão "Gerar novo PIX" |
| 5 | Clica "Gerar novo PIX" | Novo QR gerado; novo countdown inicia |
| 6 | Paga PIX | Polling detecta pagamento → estado `is_paid` → redireciona para tracking |

**Gates:**
- [ ] "PIX expirado" em `_payment_pix.html` está em `x-show` (transiente, não estático)
- [ ] `payment_status.html` expired state usa `PAYMENT_PIX_EXPIRED` omotenashi tag
- [ ] Botão "Gerar novo PIX" presente e funcional
- [ ] Após regenerar, contador reinicia a partir do novo `pix_expires_at`
- [ ] Após pagamento confirmado, redireciona para tracking com ETA

---

### Cenário 3: Cancelamento recusado → Kintsugi contextual

**Fluxo:** Pedido em preparação → cliente tenta cancelar → backend recusa → mensagem contextual

**Pré-condições:** pedido em estado que não permite cancelamento (ex: `in_preparation`).

| # | Passo | Verificação |
|---|-------|-------------|
| 1 | Acessa `/order/tracking/<ref>/` | Pedido em preparação; botão "Cancelar pedido" visível |
| 2 | Clica "Cancelar" | Modal de confirmação abre (Alpine `x-show`) |
| 3 | Confirma cancelamento | POST para endpoint de cancel |
| 4 | Backend retorna `can_cancel=False` | `tracking.cancel_refused_message` preenchido |
| 5 | Template renderiza kintsugi block | Warning com `cancel_refused_message` + link WhatsApp |
| 6 | Cliente clica WhatsApp | Nova aba com `storefront.whatsapp_url` contextual |

**Gates:**
- [ ] Modal de confirmação existe antes do POST (não cancela direto)
- [ ] Mensagem de recusa aparece no bloco de warning (não como toast genérico de erro)
- [ ] Link WhatsApp presente no bloco `cancel_refused_message`
- [ ] Mensagem usa copy de `KINTSUGI_CANCEL_REFUSED` (configurável via admin)
- [ ] Não há dead-end: cliente sempre tem próximo passo

---

## Anti-regressão automatizada

Os testes em `shopman/storefront/tests/test_omotenashi_cold_strings.py` guardam automaticamente:

| # | Guard | O que testa |
|---|-------|-------------|
| 1 | `test_unavailable_badge_has_badge_class` | "Indisponível" sempre em `badge-neutral` |
| 2 | `test_unavailable_string_absent_outside_badge_component` | "Indisponível" nunca fora do componente de badge |
| 3 | `test_pix_expired_display_is_transient_alpine_state` | "PIX expirado" em `x-show` (transiente) |
| 4 | `test_payment_status_expired_has_omotenashi_copy_and_regenerate` | Estado expired: copy + botão de regeneração |
| 5 | `test_cancelled_order_has_navigation_recovery` | Estado cancelado: link de recovery obrigatório |
| 6 | `test_cancel_refused_has_whatsapp_recovery` | Cancel recusado: WhatsApp como saída |
| 7 | `test_kintsugi_cancel_refused_copy_defined` | `KINTSUGI_CANCEL_REFUSED` definido no copy |

Ver também `test_omotenashi_regression.py` — strings frias completamente banidas dos templates.
