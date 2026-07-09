# ACCESS-LINK-UNIFICATION — um fluxo só de login via WhatsApp

Status: **aprovado, pendente de build** (decisão 2026-07-08, sessão remota).
Substitui o reverse-OTP (`feat/whatsapp-reverse-otp`) pelo fluxo de access link
já existente, com um código de estado opcional para quem chega pelo site.

## Eureka (o insight que originou isto)

Não precisamos de um OTP reverso. O fluxo "normal" de access link já resolve o
problema: quem manda a palavra-chave no WhatsApp recebe um link seguro e entra
logado. A única diferença de quem chega pelo site é a origem — então o botão do
site deve apenas **trazer o cliente para o fluxo de access link**, não criar um
handshake paralelo.

```
Direto no WhatsApp:  cliente digita  #menu           → recebe access link → entra
Vindo do site:       botão pré-preenche #menu NB-XxXx → recebe access link → entra
                                          └─ o código só carrega contexto (destino + sacola)
```

Tanto faz o caminho de chegada: **um fluxo ManyChat, um endpoint de geração, um
exchange**. O reverse-OTP inteiro (confirm, status, polling, SSE, painel de
espera, bind de sessão) é deletado.

## Por que confere (verificado no código em 2026-07-08)

1. **O access link já tem a mecânica toda**: token single-use, TTL 5 min
   (`ACCESS_LINK_EXCHANGE_TTL_MINUTES`), hash HMAC persistido, atrelado ao
   customer, exchange transacional com `select_for_update`
   (`packages/doorman/shopman/doorman/services/access_link.py:178`).
2. **A credencial é a mesma**: `DOORMAN_ACCESS_LINK_API_KEY` autentica o
   External Request do ManyChat nos dois fluxos — nada muda na infra.
3. **O retorno é MAIS seguro que o `return_url` do reverse-OTP**: o destino é
   decidido server-side e embutido na `metadata.next` do token na geração
   (com `safe_redirect_url`); o link é sempre `…/a?t=<token>` sem querystring
   de destino. A superfície de open-redirect deixa de existir.
4. **`AccessLinkCreateView` já aceita `next` e `metadata`**
   (`packages/doorman/shopman/doorman/views/access_link.py:26`) — o código de
   estado só precisa alimentar esses campos.

## O bloqueador que o plano resolve: a sacola

O carrinho anônimo é chaveado por `cart_session_key` **na sessão do browser**
(`shopman/storefront/cart.py:52`), não no customer. O access link loga o browser
que abre o link — tipicamente o in-app browser do WhatsApp, um contexto novo com
sacola vazia. **Não existe merge de carrinho por customer** no código (o hook
`on_customer_authenticated` é no-op). Era exatamente isso que o reverse-OTP
contornava ao logar a sessão original.

Solução: o código `NB-XxXx` carrega a referência da sacola. No exchange, se a
metadata do token traz `cart_session_key`, a sessão nova **adota** essa sacola.

Trade-off aceito: a continuação acontece no browser que abre o link (in-app do
WhatsApp); a aba original fica anônima. O que importa viaja junto: sacola e
destino. Sem polling, sem "volte para a aba".

## Desenho

### Caminho A — direto no WhatsApp (intocado)
Cliente manda `#menu` → flow ManyChat → `POST /api/auth/access/create/` com o
subscriber → access link genérico (fallback `/account`) → cliente entra.

### Caminho B — vindo do site (novo)
1. **Start leve** (`POST /api/v1/auth/whatsapp/start/`, reaproveitando a rota):
   gera código `NB-XxXx`, grava no cache (Valkey) um estado efêmero
   `{cart_session_key, next, created_at}` com TTL ~10 min, devolve o deep link
   `wa.me/<numero>?text=#menu NB-XxXx`. Sem SSE, sem polling, sem bind.
2. Cliente toca "Entrar pelo WhatsApp" → WhatsApp abre com a mensagem pronta →
   envia (1 toque, como no redesign de 1 clique).
3. **ManyChat**: o mesmo flow do `#menu` captura o código opcional por regex e o
   repassa no External Request como `state_code`.
4. **`AccessLinkCreateView`** (extensão): se veio `state_code`, resolve o estado
   no cache (pop single-use) e dobra na metadata do token:
   `metadata.next = <next validado>`, `metadata.cart_session_key = <ref>`.
   Código inválido/expirado → **degrada com graça**: gera o link genérico do
   caminho A (nunca falha o login por causa do estado).
5. **Exchange** (`shopman/storefront/api/auth.py:124` +
   `AccessLinkService.exchange`): após o `login()`, se a metadata traz
   `cart_session_key` e a sessão atual não tem sacola, adota
   (`request.session["cart_session_key"] = ref`). O redirect segue a lógica
   existente de `_access_link_redirect` (que já honra `metadata.next`).

### Propriedades de segurança
- **O código NB não autentica ninguém.** A identidade é o número de WhatsApp que
  envia a mensagem (princípio zero-telefone já adotado). O código só anexa
  contexto (destino + sacola).
- Pior caso de sequestro do código: o atacante anexa a *sacola* da vítima ao
  próprio login — dado de baixo valor, sem PII, mitigado por TTL curto e
  single-use. Nenhum estado do código pode conter dados pessoais.
- `next` passa por `safe_redirect_url` na geração (padrão já existente) e pela
  re-checagem defensiva no consumo.

## Inventário de remoção (após cutover)

**Backend:**
- `shopman/storefront/api/whatsapp_verify.py` — `ConfirmView`, `StatusView`,
  `whatsapp_events_view` (SSE). A `StartView` é **substituída** pela versão leve
  (sem handshake). URLs correspondentes em `shopman/storefront/api/urls.py:83-86`.
- `shopman/shop/services/whatsapp_verify.py` — `confirm_verification`,
  `verification_status`, `_login_phone`, helpers de SSE/return-url/bind.
  Sobrevive só o que o start leve reusar (geração de código, deep link).
- `shopman/storefront/tests/test_whatsapp_verify.py` — reescrever para o start leve.

**Storefront (Nuxt):**
- `app/composables/useWhatsappVerify.ts` — some o polling/SSE inteiro; resta um
  `start()` que devolve o deep link.
- `app/pages/entrar.vue` — sai o painel de espera ("volte aqui…"), o corte de
  spinner de 8s, o modo resume `?wa=` e o fallback de copiar código. O botão vira
  deep link direto.
- `server/routes/sse/whatsapp/[token].ts` — deletar.
- Constantes de poll em `~/presentation/auth` (`WHATSAPP_POLL_FALLBACK_MS`, etc.).

**Docs:** `docs/guides/whatsapp-reverse-otp.md` → substituir por guia do fluxo
unificado (config ManyChat: um flow, keyword + regex do código).

**O que fica intocado:** toda a pilha de access link (modelo, service, create,
exchange, página `/a`), upsert de subscriber ManyChat, `access_urls.py` das
notificações, `DOORMAN_ACCESS_LINK_API_KEY`.

> Nota: a deleção é por commits novos na branch (forward), não revert — a branch
> `feat/whatsapp-reverse-otp` carrega muito trabalho não relacionado (copy,
> confirmação pós-pedido, tracking) que permanece.

## Sequência (uma fase por PR, com verificação)

1. **F1 — Estado no create/exchange**: extensão do `AccessLinkCreateView`
   (`state_code` → metadata) + adoção de sacola no exchange + testes de unidade
   e do caminho degradado.
2. **F2 — Start leve + botão**: novo start (código + cache + deep link), botão
   do site vira deep link pré-aquecido, simplificação da `/entrar`.
3. **F3 — ManyChat**: regex do código no flow do `#menu`, External Request com
   `state_code`; teste ponta-a-ponta via túneis (Django + storefront).
4. **F4 — Deleção**: inventário acima, guardrails/vitest/ruff verdes, guia novo.

## Decisões em aberto (para a retomada local)

- **Formato da mensagem**: `#menu NB-XxXx` (um flow só, recomendado) vs manter a
  frase acentuada do trigger atual. Verificar se o trigger `#menu` do ManyChat
  aceita texto adicional na mesma mensagem.
- **Política de adoção da sacola** quando o browser que abre o link JÁ tem
  sacola própria (raro: in-app browser com estado). Proposta: adotar só se
  vazio; caso contrário manter a local e logar telemetria.
- **Prefixo do código**: o default do serviço atual é `V-`; `NB-` era config.
  Manter `NB-` via settings ao reaproveitar o gerador.
- A `/entrar?wa=` (resume) perde a razão de ser — confirmar que nada mais a
  referencia antes de deletar.

## TODO pós-happy-path (aprovado, fazer após validar o ciclo no ManyChat)

Comunicar a **degradação da sacola** (omotenashi — não sumir com a sacola em silêncio).
Quando `access_code` vem mas NÃO resolve (expirou/já usado), sabemos que um handoff foi
tentado e falhou (distinto do login orgânico). Então:
1. **Backend:** no `create`, quando `access_code` presente mas `pop_state` = None, marcar
   `metadata.handoff_expired = true`. No `exchange` (storefront), propagar o flag na resposta.
2. **Front:** no login, mensagem gentil ("Você entrou! Sua sacola não veio desta vez porque
   o link expirou.") + caminho (refazer / ela ficou na aba anterior). Copy a lapidar.
3. **Barato, reduz a frequência:** subir o TTL do código de 10 → 30min
   (`DOORMAN.LINK_STATE_TTL_SECONDS`).
Decidido 2026-07-09; Pablo vai validar o happy-path primeiro e então fazemos isto.
