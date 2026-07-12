# ACCESS-LINK-UNIFICATION — um fluxo só de login via WhatsApp

Status (2026-07-11): **F1/F2/F4 construídas e mergeadas no `main` (PR #45,
`2c8d58a5`)** — reverse-OTP deletado, código de estado `NB-XxXx` + exchange vivos.
**Resta F3 (fluxo ManyChat, lado do Pablo)** + apontar URLs de staging.
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
4. **F4 — Deleção** ✅ (2026-07-09): serviço reescrito enxuto (só o start leve); views
   confirm/status/SSE + URLs + canal `wa-verify-` (eventstream) removidos; front sem SSE
   route nem transforms de polling; config morto do settings limpo; guia novo
   (`docs/guides/whatsapp-access-link.md`). Endpoints mortos → 404; ruff/Django-check ok;
   27 backend + 324 vitest verdes.

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

## Degradação da sacola (handoff_expired) ✅ FEITO (2026-07-09)

Comunicar a **degradação da sacola** (omotenashi — não sumir com a sacola em silêncio).
Quando `access_code` vem mas NÃO resolve (expirou/já usado), sabemos que um handoff foi
tentado e falhou (distinto do login orgânico). Implementado:
1. **Backend `create`** (`views/access_link.py`): `access_code` presente mas `pop_state`=None
   → `metadata["handoff_expired"] = True` (else do `isinstance(state, dict)`). Login nunca falha.
2. **Backend `exchange`** (`storefront/api/auth.py`): se `metadata.handoff_expired`, resposta
   inclui `handoff_expired: true` + `notice` (copy resolvida de `LOGIN_HANDOFF_EXPIRED`, registro).
3. **Front** (`app/pages/a.vue`): `if (response.handoff_expired && response.notice) useSonner(notice)`
   antes do `navigateTo` — toast sobrevive à navegação (Sonner no layout). Entra logado normal.
4. **TTL** 10→30min (`DOORMAN.LINK_STATE_TTL_SECONDS = 1800`), reduz a frequência.
Copy default: "Você entrou! Sua sacola não veio desta vez porque o link expirou. É só montar de novo."
Testes: `test_security.py` (marca handoff / login orgânico não marca), `test_auth_access_api.py`
(exchange propaga flag+notice / metadata limpa não polui). 27 verdes + guardrails de copy.
