# Revisão frontend — UI de acompanhamento de pedidos (storefront Nuxt)

**Data:** 2026-07-17
**Escopo:** `surfaces/storefront-nuxt/` — páginas `pedido/[ref]/` (acompanhamento, pagamento, confirmação), presentation layer, copy do cliente, estados visuais, mobile-first, dark mode e consistência back↔front.
**Natureza:** revisão crítica com lente omotenashi. **Não corrige — só aponta.**

**Arquivos lidos integralmente:**
- `app/pages/pedido/[ref]/index.vue` (acompanhamento, 550 l.)
- `app/pages/pedido/[ref]/pagamento.vue` (322 l.)
- `app/pages/pedido/[ref]/confirmado.vue` (103 l.)
- `app/presentation/orderTracking.ts`, `payment.ts`, `deadline.ts`, `orderAccess.ts`
- `app/utils/operationalCopy.ts`
- `app/composables/useOrderTrackingStream.ts`
- `app/components/OrderSummaryRows.vue`, `Ui/Timeline/Timeline.vue`
- `app/error.vue` (consistência)

> **Nota de método:** a maior parte da copy de acompanhamento vem das projeções do backend (`tracking.copy.*`, `promise.*`, `action.label`) e não pôde ser auditada string-a-string por este lado; auditamos o que a camada Nuxt controla (fallbacks e strings hardcoded). A **dimensão 9 (contrato back↔front)** foi verificada com leitura dos serializers/projeções Django e do BFF — ver seção própria ao final.

---

## Sumário por severidade

| Sev | Qtd | Leitura |
|-----|-----|---------|
| **P0** | 0 | Nenhum defeito que, incondicionalmente, bloqueie o cliente ou mostre informação errada. |
| **P1** | 12 | Estados faltando / becos sem saída / a11y / bug de correção / lacuna omotenashi. Alguns são condicionais (dependem de payload nulo). |
| **P2** | ~26 | Polimento, consistência de copy, alvos de toque, contraste dark, tom, payload morto. |
| **N** | ~13 | Notas / escolhas conscientes / pontos já corretos. |

**Base é sólida.** O fluxo tem SSE + poll de fallback, countdown ancorado no relógio do servidor, indicador de frescor com CTA, estados de erro com login/retry/cardápio, diálogo de conflito de recompra e confirmação de cancelamento. Os achados abaixo são refinamentos sobre uma fundação boa — não um resgate.

---

## P0 — nenhum

Nenhum defeito dispara incondicionalmente. Os piores (botões mortos, check verde em pedido cancelado) são **condicionais** e ficam em P1.

---

## P1 — estados faltando / beco sem saída / a11y / correção / omotenashi

### P1-1 · `confirmado.vue` não tem estado de loading nem de erro → página em branco
**Arquivo:** `app/pages/pedido/[ref]/confirmado.vue:29-44`
**Dimensão:** estados visuais / omotenashi
**Problema:** `const { data } = await useFetch(...)` desestrutura **só** `data`; o template inteiro está sob um único `<div v-if="data">`. Se o fetch falhar (404/403/500, cookie de sessão não propagado no primeiro paint SSR, blip de rede) ou ainda estiver pendente, o cliente — que **acabou de finalizar o pedido** — vê um `<main>` totalmente vazio. É o momento de maior ansiedade do funil, sem nenhum fallback. `pagamento.vue` (linha 181) e `index.vue` (273-287) têm skeleton + erro; esta página não.
**Sugestão:** desestruturar `pending, error` e adicionar skeleton + ramo de erro omotenashi (reusar `orderAccessErrorView(..., 'tracking')`), com CTA para `/entrar` e para o acompanhamento.

### P1-2 · `confirmado.vue` renderiza "Pagar agora" morto quando `payment_url` é nulo
**Arquivo:** `app/pages/pedido/[ref]/confirmado.vue:35,63-66`
**Dimensão:** estados / contrato
**Problema:** `paymentRoute = localRouteFromBackend(data.value?.payment_url || null)`; o botão usa `:to="paymentRoute || undefined"`. Se `requires_payment_gate` é `true` mas `payment_url` vem nulo, o CTA primário renderiza sem destino — um botão que parece clicável e não vai a lugar nenhum, justo na ação que o cliente precisa fazer (pagar).
**Sugestão:** se `requires_payment_gate && !payment_url`, cair para a rota de acompanhamento ou mostrar "estamos preparando seu pagamento", nunca um primary no-op.

### P1-3 · Conflito de recompra só oferece "Substituir" — o modo "Adicionar" some
**Arquivo:** `app/pages/pedido/[ref]/index.vue:534-547` (esp. 542)
**Dimensão:** estados / omotenashi / funcional
**Problema:** o diálogo de conflito (sacola já com itens) só renderiza **uma** ação: `performReorderSafely(conflict.actions.find(a => a.ref.includes('replace')) || conflict.actions[0])` com label hardcoded **"Substituir"**. O backend manda também o modo *append* (adicionar à sacola), que é descartado. Um cliente que quer **somar** o pedido anterior ao carrinho atual é forçado a substituir ou cancelar. Além disso, "Substituir"/"Cancelar" (linhas 541,543) são hardcoded e ignoram a copy/labels que vêm em `conflict.actions`.
**Sugestão:** renderizar um botão por `conflict.actions` (Adicionar + Substituir), usando `action.label`; manter Cancelar como saída.

### P1-4 · `aria-live="polite"` num countdown que muda a cada segundo inunda leitores de tela
**Arquivos:** `app/pages/pedido/[ref]/index.vue:311-316` **e** `app/pages/pedido/[ref]/pagamento.vue:251`
**Dimensão:** acessibilidade
**Problema:** o contêiner do countdown é `role="timer" aria-live="polite"` e `{{ mmss }}` recomputa a cada segundo (tick de 1s). Um live region "polite" que muda a cada segundo faz o leitor de tela anunciar "04:59… 04:58… 04:57" sem parar, soterrando todo o resto. O `role="timer"` já marca a região para AT que o suportam.
**Sugestão:** remover `aria-live` do valor que tica (manter `role="timer"`), ou anunciar só em limiares (ex.: ao entrar em urgência / ao expirar).

### P1-5 · Na expiração, o timer some sem ponte — não é transparente
**Arquivos:** `app/pages/pedido/[ref]/index.vue:311` (guard `!isExpired`) **e** `app/pages/pedido/[ref]/pagamento.vue:259`
**Dimensão:** estados / omotenashi
**Problema:** no instante em que a contagem zera, o bloco inteiro do timer/barra desaparece (guard `v-if="deadlineCount && !deadlineCount.isExpired"`) e um refresh de reconciliação roda uma vez. Entre o 00:00 e a projeção atualizada, o cliente vê o timer simplesmente piscar e sumir — no momento mais tenso (prazo de PIX/confirmação). Em `pagamento.vue` sobra só `O prazo do PIX expirou.` em vermelho, sem próximo passo.
**Sugestão:** renderizar um estado explícito de expiração ("O prazo terminou. Estamos atualizando seu pedido…") até a projeção chegar; no PIX, ver P1-9.

### P1-6 · Bug: refresh-ao-expirar só dispara **uma vez** por vida da página
**Arquivo:** `app/pages/pedido/[ref]/index.vue:160,173-178` (watcher em `:114`)
**Dimensão:** correção
**Problema:** `deadlineHandled` é um `let` setado para `true` na primeira expiração e **nunca** resetado. O watcher de `deadline_at` (linha 114) zera `deadlineWindowSeconds` mas não `deadlineHandled`. Logo, um **segundo** prazo sequencial (ex.: janela de PIX → janela de confirmação) que também expire **não** dispara o refresh de reconciliação; o cliente espera até o próximo poll (≥15s) olhando um timer velho/ausente.
**Sugestão:** resetar `deadlineHandled = false` dentro do watcher de `deadline_at`.

### P1-7 · Pedido cancelado mostra um "check" verde de concluído na timeline
**Arquivos:** `app/presentation/orderTracking.ts:60-65` + `app/pages/pedido/[ref]/index.vue:399-420`
**Dimensão:** estados / consistência de sinal
**Problema:** `timelineActiveStep` devolve o índice de um passo com `state === 'cancelled'` como passo ativo, e o template marca todos os passos até o ativo como `data-completed` (fundo primary + ícone de check). Um pedido cancelado exibe, então, um check de "feito" no passo de cancelamento, sugerindo sucesso. O painel de status em tom `danger` mitiga, mas a timeline o **contradiz**.
**Sugestão:** dar ao estado `cancelled` um indicador próprio (ícone X / destructive), não dobrá-lo em `completed`.

### P1-8 · "Regularizar pagamento" (fallback) pode ser beco sem saída (href nulo)
**Arquivo:** `app/pages/pedido/[ref]/index.vue:60-63,377-379` (e `:45`)
**Dimensão:** estados / contrato
**Problema:** `showPaymentStatusFallback` é `true` quando `requires_payment_gate` e não há ação de pagamento; o botão liga `:to="paymentHref"`, mas `paymentHref` = `localRouteFromBackend(payment_gate_url || <href da ação payment> || null)`. Se o pedido tem `requires_payment_gate` mas nem `payment_gate_url` nem ação de pagamento, o cliente vê "Regularizar pagamento" que navega para lugar nenhum — a única coisa que ele precisa fazer (pagar) fica quebrada.
**Sugestão:** esconder o fallback quando `paymentHref` for nulo e oferecer contato/suporte no lugar.

### P1-9 · PIX expirado é beco sem saída — sem CTA de gerar novo código no template
**Arquivo:** `app/pages/pedido/[ref]/pagamento.vue:259`
**Dimensão:** estados / omotenashi / copy
**Problema:** na expiração, o único feedback renderizado é `<p>O prazo do PIX expirou.</p>`. O bloco QR/copia-e-cola some, o poll para (`shouldPollPayment` vira `false` em estado terminal) e **não há** "Gerar novo código PIX"/"Tentar de novo" no template. A recuperação depende inteiramente de o backend acaso emitir `payment.promise.recovery` (linha 281) ou uma `payment.actions` (299). Se não emitir, o cliente fica preso com um PIX morto e só "Acompanhar pedido".
**Sugestão:** garantir um CTA de regenerar/pagar de novo no ramo expirado (ou tornar explícito no contrato que o backend sempre manda `recovery`/`action` para PIX expirado, e confiar nisso deliberadamente).

### P1-10 · Acompanhamento não tem banner de offline explícito; `onerror` do SSE é vazio
**Arquivos:** `app/pages/pedido/[ref]/index.vue:126-130,320-339` + `app/composables/useOrderTrackingStream.ts:39-42`
**Dimensão:** estados / offline
**Problema:** há degradação graciosa (poll de fallback, `watchConnectivity` refaz o fetch, indicador de frescor), mas **nenhum** estado imediato de "você está offline / reconectando". O único sinal é o frescor virar `isStale`, que por design só dispara em idade ≥ 2× `stale_after_seconds` (~60s no default). Um aparelho que perde conexão pode mostrar dado velho, sem marca, por ~60s. `onerror` do SSE (useOrderTrackingStream:39-42) é corpo vazio. **Contraste:** `pagamento.vue` **tem** banner de conexão perdida (linha 248, após 3 polls falhos) — bom; falta o equivalente no acompanhamento.
**Sugestão:** expor o estado de conectividade (via `useConnectivity`) como banner inline imediato, independente do limiar de frescor.

### P1-11 · Título "Gateway" — jargão de infra na tela de falha de pagamento
**Arquivo:** `app/pages/pedido/[ref]/pagamento.vue:277`
**Dimensão:** copy
**Problema:** `<UiAlertTitle>Gateway</UiAlertTitle>` renderiza sempre que `payment.error_message` existe (falha de pagamento). "Gateway" é jargão de infra de pagamentos, sem sentido para o cliente — justo quando a confiança está frágil.
**Sugestão:** "Não foi possível concluir o pagamento" (ou "Problema no pagamento") e deixar `error_message` carregar o detalhe.

### P1-12 · `rating_comment_aria_label` é enviado pelo backend mas nunca aplicado (a11y)
**Arquivo:** `app/pages/pedido/[ref]/index.vue:526` ↔ backend `serializers.py:235` / `order_tracking.py:1030`
**Dimensão:** acessibilidade / contrato
**Problema:** o backend manda deliberadamente um ARIA label para a caixa de comentário da avaliação (`copy.rating_comment_aria_label`, configurável no Admin), mas o `<UiTextarea>` só liga `:placeholder="tracking.copy.rating_comment_placeholder"` — placeholder **não** é nome acessível para leitor de tela. Com acessibilidade first-class no projeto, é regressão real.
**Sugestão:** `:aria-label="tracking.copy.rating_comment_aria_label"` no textarea.

---

## P2 — polimento / consistência / mobile / dark / tom / payload morto

### Copy
- **`index.vue:153`** — `paymentLabel = t.payment_status_label || t.payment_status`. **Correção de análise:** o backend (`tracking.py:88`) já seta `payment_status = payment_status_label` (a **mesma** string localizada), então **não** há vazamento de enum cru no acompanhamento — meu apontamento inicial de "enum vazando" estava errado. O que resta é um campo **mal-nomeado e duplicado**: `payment_status` sugere estado cru (`pending`/`authorized`) mas carrega rótulo humano. Sem bug visível; renomear/remover a duplicação. *(consistência de contrato)*
- **`pagamento.vue:249`** — travessão (—) na copy do banner de conexão perdida: **proibido**. Trocar por ponto: "Sem conexão no momento. Se você já pagou, a confirmação chega assim que a internet voltar."
- **Casing de "Pix" inconsistente** — padrão do Bacen é "Pix" (só o P maiúsculo). O código mistura: `pagamento.vue:34` "Copia e cola PIX", `:35` "Código PIX copiado.", `:238` `alt="QR Code PIX"`, `:259` "O prazo do PIX expirou." — vs. correto em `:32` ("código Pix") e `payment.ts:46` ("Pix"). Padronizar "Pix"; para o copia-e-cola, o termo oficial é "Pix Copia e Cola".
- **`pagamento.vue:30-31`** — inconsistência de fornecedor: uma string nomeia "Stripe", a seguinte diz "provedor seguro". Escolher um registro (para padaria, o genérico é mais quente).
- **`index.vue:378`** — "Regularizar pagamento": verbo frio/burocrático e **inconsistente** com "Pagar agora" (`confirmado.vue:65`) e "Pagar com cartão" (`pagamento.vue:226`) para a mesma ação. Usar "Pagar agora"/"Concluir pagamento". *(overlap com P1-8 — aqui é o ângulo de tom/consistência)*
- **`pagamento.vue:257`** — "atualizamos esta tela sozinhos": "sozinhos" soa coloquial/antropomórfico. Usar "automaticamente".
- **`index.vue:196`** — toast fallback "Não foi possível executar a ação.": registro de dev, sem caminho. "Não foi possível concluir. Tente de novo ou fale conosco."
- **`error.vue:34`** — "Vamos te levar de volta…": mistura tu/você ("te") com o registro "você" do resto. Usar "Vamos levar você de volta ao cardápio."
- **`operationalCopy.ts:14`** e **`error.vue:35`** — "em instantes" está na watchlist de overpromise (promessa de tempo). Trocar por "para continuar" / "em alguns segundos".

### Mobile-first
- **`index.vue:332-338`** — CTA de refresh no estado stale é `variant="link" size="sm"` com `h-auto p-0` inline após o texto: alvo de toque sub-44px, e é justo a recuperação de tela velha. Dar um botão de tamanho real.
- **`pagamento.vue:246`** — botão "Copiar código" do PIX é tamanho default (`class="w-full sm:w-auto"`) enquanto o CTA de cartão (224) e o mock (264) são `size="lg"`. É a ação mais tocada do PIX no celular; a hierarquia a subvaloriza. `size="lg"`.
- **`pagamento.vue:245`** — o `<pre>` do copia-e-cola (`text-xs`, `max-h-40 overflow-auto`) não é tap-to-copy; selecionar 100+ chars manualmente no celular é penoso. Fazer o próprio `<pre>` chamar `copyPix` no toque, além do botão.
- **`index.vue:454,465`** — botões "Rastrear"/direções `size="sm"` ficam perto do piso de 44px. Secundários, baixa prioridade.

### Dark mode
- **`pagamento.vue:248`** — banner de conexão perdida `text-amber-700 dark:text-amber-400` sobre `bg-amber-500/5` (5% de opacidade): contraste baixo no dark; pode ficar abaixo de AA. Subir a opacidade do fundo ou usar foreground mais forte.

### Estados / omotenashi
- **`index.vue:194`** — toast genérico "Atualizado." para cancelar, confirmar-recebido e avaliar. Um cancelamento ou "recebi meu pedido" merece confirmação específica e mais quente.
- **`index.vue:378`** — label "Regularizar pagamento" hardcoded ignora a copy do backend (todo o resto usa `action.label`), podendo derivar em tom/idioma.
- **`index.vue:26`** — `rating = ref(5)`: a folha de avaliação abre já em 5/5 e o submit manda o que estiver lá; dá pra enviar sem escolher, enviesando a nota pra cima. Começar sem seleção e exigir um toque.
- **`index.vue:398-423,430-435`** — abas Histórico/Resumo sem estado vazio: se `progress_steps` ou `items` vierem vazios, a aba renderiza em branco (lê como quebrada). Mensagem "sem histórico ainda".
- **`index.vue:338`** — se `tracking.copy.stale_cta` vier vazio, sobra um "·" clicável solto. Guardar na presença da copy.
- **`index.vue:273` / `pagamento.vue:181`** — skeleton de loading é um único bloco `h-96` que não espelha o layout real (título/painel/abas). Menor.

### Segurança / boas práticas
- **`index.vue:344,380,454,465,496`** — links `target="_blank"` sem `rel="noopener noreferrer"` (WhatsApp, direções, rastreio, promise rows). `confirmado.vue:92` faz certo (`rel="noopener"`). Alinhar.

---

## N — notas / escolhas conscientes / já corretos

- **`deadline.ts:34-41` + `index.vue:110-120`** — a barra de tempo é ancorada no tempo restante do **primeiro render** (a projeção não expõe o início real do intent); ela sempre começa cheia e drena honestamente até o deadline. Quem abre a página tarde vê uma barra "cheia" que não reflete o decorrido. Aceitável dada a restrição; documentado.
- **`deadline.ts:23-31`** — `mmss` acima de 60 min mostra ex. `90:00` (sem horas). Ok para o PIX default de 60 min; ficaria estranho em janelas longas.
- **Overpromise: limpo.** Nenhum ETA fabricado no cliente — toda promise/`deadline_at`/label vem da projeção; o frescor ("Atualizado há X") é honesto.
- **Dark mode / regra de brand-bar: sem violação.** Painel de status é `bg-card` + borda colorida à esquerda com `text-foreground`/`text-muted-foreground` (tokens estáveis); o botão de direções usa o par estável `bg-brass text-brass-foreground`. Nenhum uso de `text-background`/`text-primary` como texto sobre barra de marca. O QR fica em contêiner `bg-white` incondicional (`pagamento.vue:237`) — mantém fundo claro no dark. Correto.
- **`pagamento.vue:263-274`** — copy do "Simular pagamento"/"gateway simulado" só renderiza com `payment.mock_enabled` (staging/DEBUG); não chega ao cliente de produção.
- **`error.vue:28`** — `kicker = 'Erro 404'`: techy, mas rótulo 404 convencional e tolerado.
- **`pagamento.vue:224`** — cartão abre em nova aba (mantém esta aba pollando o status) — defensável, mas no celular um popup pode ser bloqueado e não há "não abriu? toque aqui". Nota.
- **`OrderSummaryRows.vue:18-26`** — `<dl>` com só `<dd>` (sem `<dt>`): nit de HTML semântico.
- **Voz do cliente: correta.** Sem "a gente"; primeira pessoa do plural ("Nós não recebemos os dados do seu cartão", "para seguirmos com o preparo", "atualizamos"). Sem "D-1" em nenhuma string desta camada.

---

## Dimensão 9 — consistência back↔front

O BFF (`server/utils/djangoProxy.ts`) é pass-through fiel (retorna `response._data` verbatim; nenhum campo é renomeado/perdido em trânsito). **Nenhum P0:** não há valor de `promise.state`/`tone`/`status` que deixe a FE em branco ou sem saída — todo estado resolve `title`+`message` no servidor (`_promise_copy`, com catch-all em `order_tracking.py:747`), e `tone` tem default `info` nas duas telas.

**Sintomas de "a FE assume presença/valor que a BE pode não mandar" já em P1:** P1-2/P1-8 (botões de pagamento morrem com `payment_url`/`payment_gate_url` nulo), P1-7 (`progress_steps[].state === 'cancelled'` não distinguido de `completed`), P1-9 (depende de `recovery`/`action` no PIX expirado sem garantia), P1-12 (`rating_comment_aria_label` enviado e ignorado).

**Ações que o backend manda e a FE descarta silenciosamente:**
- **[P2] `pickup` (kind="instruction")** — `shop/projections/order_tracking.py:716-722` emite ação `ref="pickup"`, `kind="instruction"`, label "Retirar pedido" para `ready_pickup`. O loop de ações do painel (`index.vue:352-376`) só trata `reorder`, `kind="link"+href` e `kind="mutation"`; `instruction` não casa nenhum → botão nunca aparece. Dano baixo (sem `href`, e a message já diz "Pode retirar quando quiser"), mas é ação emitida e descartada. *Sugestão:* renderizar `instruction` como badge/label não-clicável, ou remover da projeção se é decorativa.
- **[P2] `mock_confirm_payment` no `actions[]` top-level** — `order_tracking.py:549-564` adiciona essa ação (staging/DEBUG), mas `index.vue:46-48` só extrai `cancel_order`/`rate_order`/`reorder` do top-level; o resto é ignorado. Em staging, não dá pra capturar o pagamento-mock pela tela de acompanhamento (só por `pagamento.vue`). UX de staging, não do cliente.

**Payload configurável no Admin sendo ignorado (copy morta que devia estar viva):**
- **[P2] `support_url`** — `serializers.py:282`/`order_tracking.py:340,470-478` já compõe a URL de WhatsApp com `?text=…` (copy `TRACKING_SUPPORT_WHATSAPP_MESSAGE`, configurável). Mas `index.vue:25` **ignora** e recompõe `supportUrl` do zero com string pt-BR hardcoded (`Preciso de ajuda com o pedido ${orderRef}`). A copy de suporte do Admin fica morta e a mensagem diverge. *Sugestão:* consumir `tracking.support_url`.
- **[P2] `show_payment_confirmed_notice` + `payment_confirmed_notice`** (`serializers.py:215,272`) — o aviso "Pagamento confirmado, acompanhe…" é computado no servidor e **nunca exibido** na FE. Decidir: ligar na UI ou remover.

**Payload morto (superfície de manutenção enganosa, sem bug):**
- **[P2]** `payment_pending`/`payment_expired`/`payment_confirmed` (`serializers.py:269-271`), `confirmation_countdown`/`confirmation_expires_at` (`:278-279`), `payment_expires_at` (`:275`) — a FE dirige tudo por `requires_payment_gate`, `payment_gate_url` e `promise.{tone,state,deadline_at,timer_mode}`. Quatro formas de dizer "pagamento confirmado" convivendo.
- **[P2]** `delivery_fulfillments`/`pickup_fulfillments` (`serializers.py:262-263`) — redundantes com o `fulfillments` mesclado que `tracking.py:91-103` sintetiza e a FE renderiza (`index.vue:459`). As arrays separadas nunca são tocadas.
- **[N]** `status_color` (`serializers.py:248`) — a FE deriva o acento do painel só de `promise.tone` (`orderTracking.ts:9-31`); `status_color` é morto (tunar na projeção não reflete).
- **[N]** Muitas `copy.*` de chrome mortas (`menu_label`, `progress_heading`, `live_badge`, `polling_badge`, `finished_badge`, `items_heading`, `delivery_fee_label`, `retry_label`, `not_found_*`, `rate_limit_title`, `cancel_success_*`, `cancel_failed_message`, `mock_payment_*`, `rating_success_title`, `rating_failed_message`) — supridas por toasts `useSonner` e por `orderAccessErrorView`. As de 404 são duplamente inalcançáveis: vivem no payload 200, mas a resposta 404 só carrega `{detail}` (`tracking.py:139-150`).
- **[N] `paymentHref` fallback nunca dispara** — `index.vue:45` cai para `promise.actions.find(a => a.ref.includes('payment'))?.href`, mas o ref real da ação de pagar é `pay_now` (`order_tracking.py:654`), que não contém "payment". O caminho `payment_gate_url` cobre, então sem bug visível; o guard irmão em `:62` corretamente checa `ref === 'pay_now'`.
- **[N] Página de pagamento: `intent_ready` e `reason` mortos** — `payment.py:110-130` retorna `reason` ("waiting_store_confirmation"/"no_payment_action") e `intent_ready`; `pagamento.vue` não lê nenhum (só reage a `redirect_url`). O cliente é redirecionado ao acompanhamento sem explicação de por que o pagamento não estava disponível.

**Fontes:** backend `shopman/storefront/api/serializers.py`, `tracking.py`, `presentation/order_tracking.py`, `shop/projections/order_tracking.py`, `api/payment.py`; frontend `index.vue`, `pagamento.vue`, `presentation/orderTracking.ts`, `payment.ts`, `types/shopman.ts`; BFF `server/utils/djangoProxy.ts` (pass-through verificado).

---

## Prioridade sugerida (se for corrigir depois)

1. **P1-1** (branco pós-checkout) e **P1-9** (PIX expirado sem saída) — falhas silenciosas nos dois momentos mais ansiosos.
2. **P1-6** (bug do refresh one-shot) e **P1-7** (check verde em cancelado) — um é bug de correção, o outro mostra sinal errado.
3. **P1-4** (aria-live inundando SR) e **P1-12** (aria-label da avaliação faltando) — a11y, correções baratas.
4. **P1-2 / P1-8** (botões de pagamento mortos) e **P1-3** (recompra sem "Adicionar").
5. **P1-5 / P1-10 / P1-11** (transparência de expiração, offline no tracking, jargão "Gateway").
6. Lote de copy P2 (Pix casing, travessão, "Regularizar", tu/você, "em instantes") — de baixo risco, alto retorno de tom.
</content>
</invoke>
