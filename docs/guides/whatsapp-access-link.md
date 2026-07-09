# Login por WhatsApp via access link (ManyChat)

Guia de configuração do login por WhatsApp unificado no fluxo de **access link** do
doorman. Um fluxo só no ManyChat, um endpoint de geração, um exchange. SMS (Comtele)
segue como fallback. Substitui o antigo reverse-OTP (ver
[ACCESS-LINK-UNIFICATION-PLAN](../plans/ACCESS-LINK-UNIFICATION-PLAN.md)).

## A ideia

Não precisamos de OTP. Quem manda a palavra-chave no WhatsApp da loja já recebe, pelo
ManyChat + doorman, um **access link** seguro e entra logado. O botão do site só **traz
o cliente para esse mesmo fluxo**: ele pré-preenche a mensagem com um código `NB-XxXx`
que carrega **contexto** (a sacola anônima + o destino), não credencial. A identidade é
o **número que envia a mensagem** (zero-telefone); o código nunca autentica ninguém.

Quem não usa WhatsApp cai no **fallback SMS** (Comtele), o fluxo OTP clássico
(`RequestCodeView` + `DELIVERY_CHAIN`).

## Fluxo

```
1. Site → POST /api/v1/auth/whatsapp/start/         → { code: "NB-XxXx", deep_link, wa_number }
   (guarda {cart_session_key, next} sob o código, no cache, uso único, TTL 30min)
2. Cliente toca "Entrar pelo WhatsApp" → wa.me abre a mensagem pronta → envia
3. ManyChat (Flow) → POST /api/auth/access/create/  (S2S, API key)
   body: { customer_id/subscriber, access_code: "<a mensagem inteira>" }
   → o create extrai o NB-XxXx, resolve o contexto e dobra na metadata do token
   → responde { access_url: ".../a?t=<token>", token, expires_at }
4. ManyChat responde ao cliente com um botão apontando para access_url
5. Cliente toca → /a?t=<token> → POST /api/v1/auth/access/  (exchange)
   → loga a sessão + adota a sacola (cart_session_key) + redireciona (metadata.next)
```

Sem handshake, sem polling, sem SSE, sem bind de sessão. O contexto viaja junto
(sacola + destino); a aba original fica anônima (troca aceita — ver o plano).

## Endpoints

| Método | Rota | Auth | Uso |
|--------|------|------|-----|
| POST | `/api/v1/auth/whatsapp/start/` | pública (rate-limit 10/min) | Site: gera o código NB + deep link. Body opcional `{"next": "/checkout"}`; a sacola vem da sessão. |
| POST | `/api/auth/access/create/` | **API key S2S** | ManyChat: gera o access link. Aceita `access_code` (a mensagem inteira; o código é extraído). |
| POST | `/api/v1/auth/access/` | pública | Exchange do token → sessão logada + adoção de sacola + redirect. |

O `create` autentica com a `DOORMAN_ACCESS_LINK_API_KEY` (header `Authorization: Bearer
<chave>` ou `X-Api-Key`). Fail-closed: sem chave, rejeita fora de DEBUG.

## Variáveis de ambiente

```env
# WhatsApp da loja (E.164 só dígitos). Vazio = usa Shop.phone
SHOPMAN_WHATSAPP_VERIFY_NUMBER=554333231997
# Mensagem pré-preenchida do botão (opcional; {code} é o NB-XxXx). Default abaixo.
SHOPMAN_WA_ACCESS_MESSAGE_TEMPLATE=Meu código de acesso é {code}

# Chave server-to-server do create. OBRIGATÓRIA fora de DEBUG.
DOORMAN_ACCESS_LINK_API_KEY=<segredo forte>
# Base pública da loja Nuxt: onde o access_url aponta (.../a?t=<token>).
DOORMAN_ACCESS_LINK_ENTRY_URL=https://<loja>

# ManyChat (Flow + notificações outbound). Ver release-secrets-runbook.md
MANYCHAT_API_TOKEN=<token da API ManyChat>
MANYCHAT_WEBHOOK_SECRET=<segredo HMAC inbound>

# Fallback SMS (Comtele) — já plugado em DELIVERY_SENDERS['sms']
COMTELE_API_KEY=<api key Comtele>
COMTELE_ROUTE=<id da rota transacional>
```

O prefixo do código (`NB-`) e o TTL (30 min) são do doorman
(`DOORMAN.LINK_STATE_CODE_PREFIX` / `LINK_STATE_TTL_SECONDS`).

## Configuração do Flow no ManyChat (a parte "F3")

1. **Trigger** — um *Keyword* "message contains" que case o site **e** a entrada
   orgânica. Robusto (evite casar texto comum):
   - `NB-` — o prefixo distintivo do código do site (o deep link sempre injeta).
   - opcionalmente a frase da entrada orgânica que você adotar (ex.: `menu`).

   O trigger **não é a fronteira de segurança** — o Django é o portão (código no
   cache, single-use, TTL, rate-limit; a identidade é o número da Meta). Guarde a
   resposta do create numa condição `access_url != empty` antes de responder, para um
   trigger espúrio nunca mandar um botão quebrado.
2. **External Request** (Dev Tools, plano Pro):
   - Method: `POST`
   - URL: `https://api.<seu-domínio>/api/auth/access/create/`
   - Header: `Authorization: Bearer {{DOORMAN_ACCESS_LINK_API_KEY}}`
   - Body (JSON):
     ```json
     {
       "customer_id": "{{subscriber_id ou o id do seu customer}}",
       "access_code": "{{last_input_text}}"
     }
     ```
     `access_code` = a mensagem inteira que o cliente enviou (System Field "Last Text
     Input"). **Não precisa de regex no ManyChat** — o Django extrai o `NB-XxXx` do
     texto. Se o código for inválido/expirado, o create **degrada com graça**: gera o
     link genérico (fallback `/account`) e marca `handoff_expired` (ver abaixo).
3. **Resposta ao cliente** — mapeie o `access_url` da resposta num custom field e use
   como **URL do botão** ("Entrar na loja"). Ao tocar, a loja abre em `/a?t=<token>`,
   troca o token, loga e cai no destino (checkout/conta) já com a sacola.

> Quando `access_url` volta preenchido, o login está pronto. O botão é o único passo
> do lado do cliente; sem SSE/polling.

## Degradação da sacola (handoff_expired)

Omotenashi: nunca sumir com a sacola em silêncio. Se o código veio mas **não resolveu**
(expirou/já usado), o create marca `metadata.handoff_expired = true` (distinto do login
orgânico, que não tem `access_code`). No exchange, a resposta traz `handoff_expired: true`
+ `notice`, e a loja mostra um toast gentil: *"Você entrou! Sua sacola não veio desta vez
porque o link expirou. É só montar de novo."* (copy configurável, chave
`LOGIN_HANDOFF_EXPIRED`). O login em si nunca falha por isso; o TTL de 30 min reduz a
frequência.

## Fallback SMS (Comtele)

Primário da `DELIVERY_CHAIN` em produção (`["sms", "email"]`). Para ativar em
staging/alpha, configure `COMTELE_API_KEY` e `COMTELE_ROUTE` — o `ComteleSMSSender` sai
do estado inerte. Na tela, "Usar outro número" revela o campo e usa o fluxo clássico:

```
POST /api/v1/auth/request-code/  { "phone": "+55...", "delivery_method": "sms" }
POST /api/v1/auth/verify-code/   { "phone": "+55...", "code": "123456" }
```

## Segurança

- **O código NB não autentica.** A identidade é o número de WhatsApp que envia a
  mensagem (zero-telefone). O código só anexa contexto (destino + sacola).
- Pior caso de sequestro do código: o atacante anexa a *sacola* da vítima ao próprio
  login — dado de baixo valor, sem PII, mitigado por TTL curto + single-use. **Nenhum
  estado do código carrega PII.**
- `next` passa por `safe_redirect_url` na geração e re-checagem no consumo (sem
  open-redirect; o link é sempre `.../a?t=<token>`, sem querystring de destino).
- `create` fail-closed sem `DOORMAN_ACCESS_LINK_API_KEY` fora de DEBUG. `start` tem
  rate-limit por IP (10/min).
- Token do access link: single-use, TTL 5 min, hash HMAC, exchange transacional
  (`select_for_update`). Ver `packages/doorman/.../services/access_link.py`.

## Frontend (storefront-nuxt)

Uma tela só (`app/pages/entrar.vue`), WhatsApp como caminho primário:

- **`app/components/WhatsappVerifyPanel.vue`** — Bloco 1: lampejo do que vai acontecer +
  botão deep link (`wa.me`, `<a href>` pré-aquecido). Divisor "ou". Bloco 2: envio manual
  (código + copiar + abrir chat cru). "Usar outro número" (SMS) abaixo. Copy vem por
  props, configurável no Admin (`LOGIN_WA_*`).
- **`app/composables/useWhatsappVerify.ts`** — `start(next)` leve: devolve
  `{code, deepLink, waNumber, status}`. Sem polling/SSE/resume.
- **`app/pages/a.vue`** — landing do access link: troca o token via BFF `/api/auth/access/`,
  adota a sacola, redireciona. Mostra o toast de `handoff_expired` quando aplicável.

## Testar localmente com Cloudflare Tunnel

O único serviço que **precisa ser público** é o Django — para o External Request do
ManyChat alcançar o `create`, e para o cliente abrir o `access_url` (a base do link é
`DOORMAN_ACCESS_LINK_ENTRY_URL`, que deve apontar para o túnel do storefront). O
`settings.py` já libera `*.trycloudflare.com` em `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`
no modo dev.

1. **`.env` (dev)** — mínimo:
   ```env
   SHOPMAN_WHATSAPP_VERIFY_NUMBER=554333231997     # o WhatsApp ligado ao ManyChat
   DOORMAN_ACCESS_LINK_API_KEY=<segredo forte>     # em DEBUG o create aceita sem, mas configure p/ testar de verdade
   DOORMAN_ACCESS_LINK_ENTRY_URL=https://<tunnel-storefront>.trycloudflare.com
   ```
2. **Django + túnel** — `make run` sobe `0.0.0.0:8000` + directive worker + um quick
   tunnel Cloudflare (URL em `.tunnel.log`). Levante também um túnel para o storefront
   (`:3000`) e use essa URL em `DOORMAN_ACCESS_LINK_ENTRY_URL`.
3. **Storefront (Nuxt)** — `NUXT_DJANGO_BASE_URL=http://127.0.0.1:8000 npm run dev` (ou
   `node .output/server/index.mjs` num build). Abra `/entrar` no celular via o túnel.
4. **ManyChat** — no External Request, aponte para `https://<tunnel-django>/api/auth/access/create/`
   com `access_code: {{last_input_text}}`.
5. **Fluxo de teste**: no celular, adicione um item em estoque → checkout → "Entrar pelo
   WhatsApp" → o WhatsApp abre com `Meu código de acesso é NB-XXXX` → envie → o Flow chama
   o `create` → toque no botão que ele devolve → você volta logado, com a sacola, no checkout.

> Quick tunnels trocam de URL a cada `make run` (reaponte o ManyChat **e**
> `DOORMAN_ACCESS_LINK_ENTRY_URL`). Para URL fixa, use um named tunnel do Cloudflare.

## Testes

```bash
make test-framework   # backend: start leve, create (code/handoff), exchange (sacola/notice)
cd surfaces/storefront-nuxt && npm run test:unit   # front: transforms + guardrails de surface
```

Backend: `shopman/storefront/tests/test_whatsapp_verify.py` (start leve),
`packages/doorman/.../tests/test_security.py` (create: dobra sacola/next, extrai da
mensagem, degrada, marca handoff), `shopman/storefront/tests/web/test_auth_access_api.py`
(exchange: adoção de sacola, handoff notice).
