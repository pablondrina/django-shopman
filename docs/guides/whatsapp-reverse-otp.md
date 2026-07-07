# Verificação de número por WhatsApp (reverse-OTP) + fallback SMS

Guia de configuração da verificação de número do cliente pelo WhatsApp usando
ManyChat (plano pago), com SMS (Comtele) como fallback.

## Por que "reverse-OTP"

O ManyChat só expõe templates **Marketing** e **Utility** — não emite a categoria
**Authentication**, que a Meta **exige** para enviar um código OTP. Colocar o código
num template Utility viola a política e é rejeitado (o próprio código já mantinha o
`ManychatOTPSender` fora da `DELIVERY_CHAIN` por isso).

A solução inverte o fluxo: em vez de o servidor **enviar** o código, é o **cliente**
quem envia uma mensagem contendo um token para o WhatsApp da loja. O WhatsApp entrega
ao ManyChat o número **já verificado pela infraestrutura da Meta** — prova de posse
mais forte que um OTP digitado, **custo Meta zero** (conversa iniciada pelo usuário)
e sem template nenhum para ser rejeitado.

Quem não tiver/quiser WhatsApp cai no **fallback SMS** (Comtele), que usa o fluxo OTP
clássico já existente (`RequestCodeView` + `DELIVERY_CHAIN`).

## Fluxo

```
1. Storefront → POST /api/v1/auth/whatsapp/start/      → { token, deep_link }
2. Cliente toca no deep link wa.me e envia a mensagem com o token
3. ManyChat (Flow) → POST /api/v1/auth/whatsapp/confirm/ (S2S, API key)  → verifica
4. Storefront faz polling → POST /api/v1/auth/whatsapp/status/ → autentica a sessão
   (fallback) → botão "receber por SMS" → POST /api/v1/auth/request-code/ {delivery_method:"sms"}
```

O token efêmero vive **só no cache (Valkey)** com TTL — sem migração, sem tocar nos
modelos do Core.

## Endpoints

| Método | Rota | Auth | Uso |
|--------|------|------|-----|
| POST | `/api/v1/auth/whatsapp/start/` | pública (rate-limit 10/min) | Gera token + deep link. Body opcional `{"phone": "+55..."}`. |
| POST | `/api/v1/auth/whatsapp/confirm/` | **API key S2S** | Chamado pelo ManyChat. Body `{"token": "...", "phone": "55..."}`. |
| GET/POST | `/api/v1/auth/whatsapp/status/` | pública (rate-limit 30/min) | Fetch canônico `{"token": "..."}`. Ao verificar, loga a sessão. |
| GET | `/api/v1/auth/whatsapp/events/<token>/` | sessão de origem (Http404 senão) | SSE (canal `wa-verify-<token>`). Push instantâneo no confirm. |

O `confirm` autentica com a `DOORMAN_ACCESS_LINK_API_KEY` no header
`Authorization: Bearer <chave>` (ou `X-Api-Key`). Fail-closed: sem chave configurada,
rejeita fora de DEBUG.

## Variáveis de ambiente

```env
# WhatsApp reverse-OTP
SHOPMAN_WHATSAPP_VERIFY_NUMBER=554333231997   # WhatsApp da loja (E.164 só dígitos). Vazio = usa Shop.phone
SHOPMAN_WA_VERIFY_TTL_SECONDS=600             # opcional (default 10 min)
SHOPMAN_WA_VERIFY_TOKEN_PREFIX=V-             # opcional

# Chave server-to-server (mesma usada por access-link). OBRIGATÓRIA fora de DEBUG.
DOORMAN_ACCESS_LINK_API_KEY=<segredo forte>

# ManyChat (para o Flow e notificações outbound). Ver release-secrets-runbook.md
MANYCHAT_API_TOKEN=<token da API ManyChat>
MANYCHAT_WEBHOOK_SECRET=<segredo HMAC inbound>

# Fallback SMS (Comtele) — já plugado em DELIVERY_SENDERS['sms']
COMTELE_API_KEY=<api key Comtele>
COMTELE_ROUTE=<id da rota transacional>
```

## Configuração do Flow no ManyChat (feito na UI do ManyChat)

1. **Trigger** — crie um *Keyword* robusto (evite casar só `V-`, que colide com
   texto comum). Duas keywords em **OR**, ambas "message contains":
   - `código de verificação` — a frase que o deep link sempre injeta (o caminho
     normal). Multi-palavra ⇒ quase zero falso-positivo.
   - `NB-` — o prefixo distintivo do token (configure `SHOPMAN_WA_VERIFY_TOKEN_PREFIX=NB-`),
     que cobre a digitação manual se o deep link falhar.

   O trigger **não é a fronteira de segurança** — o Django é o portão (token no
   Valkey, single-use, TTL, rate-limit + bind de sessão). Guarde a resposta do Flow
   numa condição `ok == true` antes de responder, para um trigger espúrio (que caia
   num `404`) nunca mandar mensagem de sucesso.
2. **External Request** (Dev Tools, plano Pro):
   - Method: `POST`
   - URL: `https://api.<seu-domínio>/api/v1/auth/whatsapp/confirm/`
   - Header: `Authorization: Bearer {{DOORMAN_ACCESS_LINK_API_KEY}}`
   - Body (JSON):
     ```json
     {
       "token": "{{last_input_text}}",
       "phone": "{{phone}}",
       "name": "{{first_name}} {{last_name}}"
     }
     ```
     (`phone` = system field do contato; `last_input_text` = a mensagem que o
     cliente enviou — o serviço extrai o token do texto; `first_name`/`last_name`
     = nome do perfil do WhatsApp, trazido como **sugestão** para o cliente
     confirmar no "Como quer ser chamado?". Aceita também um único campo `name`.)
3. **Resposta ao cliente** — se o External Request retornar `ok: true`, responda
   "✅ Número confirmado!" com um **botão/link de volta para a loja**. O `confirm`
   devolve `return_url` no corpo (ex.: `https://<loja>/entrar?wa=NB-XXXX`) — mapeie
   esse campo num custom field do ManyChat e use como URL do botão. Ao tocar, a loja
   reabre **na mesma sessão** (cookie) e conclui a entrada; o `?wa=<token>` deixa o
   `/entrar` retomar o handshake mesmo se a aba foi reciclada.

> O `return_url` só vem preenchido se `SHOPMAN_STOREFRONT_BASE_URL` (a base pública da
> loja Nuxt) estiver configurada. No fluxo desktop+QR o botão é dispensável — o
> desktop confirma sozinho via push SSE; o retorno importa no fluxo tudo-no-celular.

> O endpoint tolera a mensagem inteira em `token` (ex.: "Meu código de verificação é
> NB-AC3F9K") — ele extrai o padrão do token automaticamente, com ou sem acento.

## Fallback SMS (Comtele)

Já está construído e é o primário da `DELIVERY_CHAIN` em produção (`["sms", "email"]`).
Para ativar no staging/alpha, basta configurar `COMTELE_API_KEY` e `COMTELE_ROUTE` — o
`ComteleSMSSender` sai do estado inerte. O storefront chama o fluxo clássico:

```
POST /api/v1/auth/request-code/  { "phone": "+55...", "delivery_method": "sms" }
POST /api/v1/auth/verify-code/   { "phone": "+55...", "code": "123456" }
```

## Nome trazido do WhatsApp

Quando o cliente envia a mensagem, o ManyChat conhece o nome do perfil dele. O Flow
manda esse nome no `confirm`; o storefront o devolve como `welcome_suggested_name`
(com `requires_welcome: true`) para o cliente **apenas confirmar** — não é gravado como
definitivo até ele confirmar. Some fricção sem abrir mão do consentimento.

## Durabilidade (handshake efêmero + fato durável)

- O **token/handshake** vive só no cache (Valkey) com TTL — sem migração, sem tocar
  nos modelos do Core.
- No sucesso, o **fato durável** ("número verificado via WhatsApp") é persistido em
  Guestman como `ContactPoint(type=WHATSAPP, is_verified=True)` + `Identifier`,
  reusando os mesmos serviços que o doorman usa no login por código.

## Segurança

- **Bind de sessão**: o `status` só autentica a **mesma sessão** que chamou o `start`
  (comparação por `session_key`). Um token confirmado por terceiros não autentica
  outro navegador — fecha o vetor de fixação de sessão.
- A verificação usa o número que a **Meta reporta** como fonte da verdade (prova de
  posse). Divergência com o número digitado no cadastro volta como `phone_mismatch`
  (sinalizado, não silenciado).
- `confirm` é fail-closed sem `DOORMAN_ACCESS_LINK_API_KEY` fora de DEBUG, e tem
  **rate-limit por telefone** (10/hora) além da API key S2S.
- Token de uso único (consumido no primeiro `status` verificado), TTL curto, alfabeto
  sem caracteres ambíguos.
- Rate-limit por IP em `start` (10/min) e `status` (30/min).

## Frontend (storefront-nuxt)

A tela de entrada (`app/pages/entrar.vue`) tem o WhatsApp como caminho primário:

- **`app/components/WhatsappVerifyPanel.vue`** — botão deep link (`wa.me`) como CTA
  principal (mobile-first), **QR code no desktop** (escaneia com o celular),
  contagem regressiva, "gerar novo código" ao expirar e "prefiro por SMS" como
  fallback. Feedback ao vivo ("aguardando confirmação…" → "número confirmado!").
- **`app/composables/useWhatsappVerify.ts`** — start + **push por SSE** (canal
  `wa-verify-<token>`, same-origin via BFF `/sse/whatsapp/<token>`); no evento
  refaz o fetch canônico de `/status` (fonte da verdade, que autentica a sessão).
  Poll fica como fallback calmo (8s). Ver [ADR-016](../decisions/adr-016-sse-first-realtime.md).
- **`app/presentation/auth.ts`** — transforms puros (contagem, fase, cadência),
  cobertos por vitest.
- O passo "Como quer ser chamado?" é o mesmo de antes; o nome do WhatsApp chega
  pré-preenchido em `welcome_suggested_name` para a pessoa só confirmar.

O QR usa a dependência `qrcode` (adicionada ao `package.json`). Rode `npm ci` no
`surfaces/storefront-nuxt` antes do build. Sem a lib, o desktop degrada limpo para
botão + link copiável.

## Testar localmente com Cloudflare Tunnel

O único serviço que **precisa ser público** é o Django — para o External Request do
ManyChat alcançar o `confirm`. O navegador de teste (desktop) e o celular (que envia
a mensagem) fazem o resto. O `settings.py` já libera `*.trycloudflare.com` em
`ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` no modo dev — o túnel funciona sem ajustar host.

1. **`.env` (dev)** — mínimo para o fluxo:
   ```env
   SHOPMAN_WHATSAPP_VERIFY_NUMBER=554333231997   # o WhatsApp ligado ao ManyChat
   DOORMAN_ACCESS_LINK_API_KEY=<segredo forte>   # em DEBUG o confirm aceita sem, mas configure p/ testar de verdade
   # (opcional) fallback SMS:
   COMTELE_API_KEY=...
   COMTELE_ROUTE=...
   ```

2. **Django + túnel** (alvo já existente):
   ```bash
   make run
   ```
   Ele sobe o servidor em `0.0.0.0:8000`, o directive worker e um **quick tunnel**
   Cloudflare; a URL pública aparece no console e em `.tunnel.log`
   (ex.: `https://algo-aleatorio.trycloudflare.com`).

3. **Storefront (Nuxt)** em outro terminal:
   ```bash
   cd surfaces/storefront-nuxt
   NUXT_DJANGO_BASE_URL=http://localhost:8000 npm run dev
   ```
   Abra `http://localhost:3000/entrar` no **desktop**.

4. **ManyChat** — no External Request do Flow, aponte para a URL do túnel:
   ```
   POST https://<tunnel>.trycloudflare.com/api/v1/auth/whatsapp/confirm/
   Authorization: Bearer <DOORMAN_ACCESS_LINK_API_KEY>
   Body: { "token": "{{last_input_text}}", "phone": "{{phone}}", "name": "{{first_name}} {{last_name}}" }
   ```

5. **Fluxo de teste**: no desktop, "Entrar pelo WhatsApp" → escaneie o QR com o
   celular → o WhatsApp abre com o token → envie → o Flow do ManyChat chama o
   `confirm` → o desktop recebe o **push SSE** e confirma na hora.

> Quick tunnels trocam de URL a cada `make run` (é preciso reapontar o ManyChat). Para
> uma URL fixa, use um **named tunnel** do Cloudflare — requer um (sub)domínio com DNS
> na Cloudflare (o domínio de vocês está na DigitalOcean, então seria mover um
> subdomínio de teste, ex.: `dev.` para a Cloudflare).

## Testes

Backend — `shopman/storefront/tests/test_whatsapp_verify.py` cobre start, confirm
(com/sem/errada API key, token desconhecido, idempotência, extração de token,
nome sugerido, bind de sessão, phone_mismatch) e o fluxo completo com autenticação:

```bash
make test-framework
```

Frontend — transforms puros em `tests/authPresentation.test.ts`:

```bash
cd surfaces/storefront-nuxt && npm run test:unit
```
