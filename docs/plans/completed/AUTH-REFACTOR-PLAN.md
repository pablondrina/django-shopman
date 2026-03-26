# Plano: Refatoração Auth — Phone-First Library-Grade

## Contexto

O auth app (`shopman-core/auth/`) é um sistema passwordless phone-first que já funciona bem (OTP HMAC, device trust, bridge tokens, magic links). Mas tem gaps que impedem seu uso como biblioteca madura:

1. **Não integra com Django auth** — storefront usa session keys custom, não `request.user`
2. **Customização espalhada** — sender, resolver, storage são protocolos separados sem ponto único de customização
3. **Sem fallback de delivery** — se WhatsApp cair, OTP não chega
4. **Naming com jargão** — `MagicCode`, `IdentityLink`, `BridgeToken` violam convenções de naming do projeto
5. **Alias residual** — `VerificationService = AuthService` viola "zero backward-compat aliases"

### Visão do produto

Uma biblioteca auth Django reusável, phone-first, que:
- Funciona perfeitamente para o Shopman (padaria com WhatsApp)
- É configurável para outros cenários (IG, SMS, email, API)
- Não impõe canal — "não tirar o usuário de onde ele já estava"
- WhatsApp é passageiro de primeira classe, mas não obrigatório

### Filosofia: Identity Continuity, não Login System

Auth não é "crie conta → defina senha → confirme email." Auth é **provar que é você, pronto**, da forma mais rápida, prática e segura possível. Quanto menos o usuário percebe que fez auth, melhor.

- **Já estou no WhatsApp** → AccessLink → web logado (zero fricção)
- **Voltei na web** → Device Trust → skip OTP (zero fricção)
- **Primeira vez** → OTP 6 dígitos → device trust → nunca mais pede
- **WhatsApp caiu** → SMS → Email magic link (fallback transparente)

Nenhuma lib Django mainstream resolve este cenário. O django-allauth é fundamentalmente account management (email/password-first). Nosso auth é **identity continuity** (channel-first).

---

## WP-AUTH-0: Naming + Estrutura (pré-requisito)

**Meta**: Alinhar naming e estrutura com o restante da suite antes de adicionar features.

### Renames de Models (com migration reset)

| Atual | Novo | Razão |
|-------|------|-------|
| `MagicCode` | `VerificationCode` | "Magic" é jargão inventado. "VerificationCode" é auto-explicativo |
| `IdentityLink` | `CustomerUser` | "IdentityLink" é vago. "CustomerUser" diz exatamente o que é: liga Customer ↔ User |
| `BridgeToken` | `AccessLink` | "Bridge" é jargão interno. "AccessLink" é perspectiva do usuário: link de acesso |
| `TrustedDevice` | mantém | Excelente nome |

### Renames de Services/Funções

| Atual | Novo | Razão |
|-------|------|-------|
| `VerificationService` (alias) | **DELETAR** | Zero aliases. Só `AuthService` fica |
| `magic_code_sent` (signal) | `verification_code_sent` | Acompanha rename do model |
| `magic_code_verified` (signal) | `verification_code_verified` | Idem |
| `bridge_token_created` (signal) | `access_link_created` | Acompanha rename do model |
| `MagicLinkService` | **ABSORVER** em `AccessLinkService` | Magic link é só um AccessLink entregue por email. Unificar. |
| `services/verification.py` | mantém | O service se chama `AuthService`, o arquivo é sobre verification |
| `services/auth_bridge.py` | `services/access_link.py` | Acompanha rename |
| `services/magic_link.py` | **DELETAR** | Absorvido por `access_link.py` |

### Rename de arquivos

| Atual | Novo |
|-------|------|
| `models/magic_code.py` | `models/verification_code.py` |
| `models/identity_link.py` | `models/customer_user.py` |
| `models/bridge_token.py` | `models/access_link.py` |

### Unificação: AccessLink absorve MagicLink

O "Magic Link" (email) e o "Bridge Token" (chat) são **o mesmo mecanismo**: um link que dá acesso à web. A diferença é só o canal de entrega. Unificar:

```
AccessLink (model único)
  ├── entregue via WhatsApp (Manychat manda no chat)
  ├── entregue via Email (era "Magic Link")
  ├── entregue via SMS (link no SMS)
  └── gerado por API (backend entrega como quiser)

VerificationCode (model separado)
  └── OTP 6 dígitos digitado pelo usuário
```

Princípio: **"o canal é a verificação."** Se o link chegou no seu WhatsApp, você é dono desse WhatsApp. Se chegou no seu email, você é dono desse email. O mecanismo é idêntico.

`MagicLinkService` é absorvido por `AccessLinkService`, que ganha um método `create_and_send(customer, channel="email"|"whatsapp"|"sms"|"api")`. Internamente: cria AccessLink + monta URL + chama `adapter.send_access_link(channel, customer, url)`. O adapter abstrai o "como enviar" (Manychat, WhatsApp Cloud API, Twilio, SMTP, etc.) — o service cuida do "o quê" (criar token, montar URL, registrar).

### Estrutura: `conf.py` NÃO muda para `app_settings.py`

Análise dos 8 core apps: **todos usam `conf.py`** com dataclass + LazySettings. O allauth usa `app_settings.py`, mas nosso padrão interno é `conf.py`. Manter consistência da suite > convenção do allauth.

O que MELHORA no `conf.py`:
- Adicionar validação de settings críticos no boot (ex: `ACCESS_LINK_TTL_MINUTES > 0`)
- Adicionar `get_adapter()` singleton (similar ao existente `get_customer_resolver()`)

### Regra zero-residuals

Todos os renames seguem a convenção do CLAUDE.md: zerar TUDO — variáveis, strings, comments, docstrings, nomes de teste, fixtures. Migrations serão resetadas. Nada de `# formerly MagicCode`.

**Arquivos afetados**: Todos os arquivos do auth app que referenciam os nomes antigos (~30 arquivos).

**Testes**: `make test` deve passar 100%. Grep por nomes antigos deve retornar zero.

**Risco**: BAIXO — é rename mecânico. Migrations resetadas.

---

## WP-AUTH-1: AuthenticationBackend + login() + logout

**Meta**: `request.user` e `@login_required` funcionam para customers OTP-verified.

**Mudanças**:
- **NOVO** `backends.py` — `PhoneOTPBackend(BaseBackend)`:
  - `authenticate(request, customer_id=...)` → resolve User via CustomerUser
  - `get_user(user_id)` → standard Django lookup
- **NOVO** `services/_user_bridge.py` — extrair `_get_or_create_user` do `AccessLinkService` para `get_or_create_user_for_customer()`. Reutilizado por access link e backend.
- **NOVO** `views/logout.py` — `LogoutView` (POST): chama `django.contrib.auth.logout()`, limpa cookie device trust, redireciona.
- **MOD** `services/access_link.py` — delegar para `_user_bridge`.
- **MOD** `services/verification.py` — após verify_for_login, chamar `login()` se `request` fornecido.
- **MOD** `urls.py` — `/auth/logout/`.
- **MOD** `conf.py` — `LOGOUT_REDIRECT_URL`.

**Risco**: BAIXO. Puramente aditivo.

---

## WP-AUTH-2: Unified Adapter Pattern

**Meta**: Ponto único de customização inspirado no `DefaultAccountAdapter` do allauth.

**Mudanças**:
- **NOVO** `adapter.py` — `DefaultAuthAdapter`:

  ```python
  class DefaultAuthAdapter:
      # Resolução de customer (delega para CustomerResolver existente)
      def resolve_customer_by_phone(self, phone) -> AuthCustomerInfo | None
      def resolve_customer_by_email(self, email) -> AuthCustomerInfo | None
      def resolve_customer_by_uuid(self, uuid) -> AuthCustomerInfo | None
      def create_customer_for_phone(self, phone) -> AuthCustomerInfo

      # Delivery (delega para MessageSender existente; AUTH-3 adiciona fallback)
      def send_code(self, target, code, method) -> bool
      def get_delivery_chain(self, target) -> list[str]

      # Hooks (substituem signals para quem prefere adapter)
      def on_customer_authenticated(self, request, customer, user, method)
      def on_device_trusted(self, request, customer, device)
      def on_login_failed(self, request, target, reason)

      # Configuração
      def should_auto_create_customer(self) -> bool
      def normalize_phone(self, raw) -> str
      def is_login_allowed(self, target, method) -> bool

      # Redirects
      def get_login_redirect_url(self, request, customer) -> str
      def get_logout_redirect_url(self, request) -> str
  ```

- `DefaultAuthAdapter.__init__` instancia `CustomerResolver` e `MessageSender` dos settings existentes → backward compat total.
- **MOD** `conf.py` — `AUTH_ADAPTER` setting + `get_adapter()` singleton.
- **MOD** `services/verification.py`, `access_link.py` — usar `get_adapter()`.
- **DEL** `services/magic_link.py` — absorvido por `access_link.py`. O `AccessLinkService` ganha `create_and_send(customer, channel)` que cobre WhatsApp, Email, SMS, API.

**Decisão**: Os signals existentes (`customer_authenticated`, etc.) continuam funcionando. O adapter oferece hooks **adicionais**, não substitui signals. Quem configura adapter pode usar hooks; quem conecta signals pode usar signals.

**Risco**: MÉDIO. Mitigação: adapter delega para mesmos resolver/sender — comportamento idêntico.

---

## WP-AUTH-3: Delivery Fallback Chain

**Meta**: WhatsApp → SMS → Email. Configurável.

**Mudanças**:
- **MOD** `conf.py`:
  ```python
  DELIVERY_CHAIN = ["whatsapp", "sms", "email"]
  DELIVERY_SENDERS = {
      "whatsapp": "shopman.auth.senders.WhatsAppCloudAPISender",
      "sms": "shopman.auth.senders.SMSSender",
      "email": "shopman.auth.senders.EmailSender",
  }
  ```
- **MOD** `adapter.py` — `send_code_with_fallback()` itera pela chain com logging.
- **MOD** `services/verification.py` — `request_code()` usa fallback. Grava `delivery_method` real no VerificationCode.

**Risco**: BAIXO. Aditivo. Sem chain configurada, usa sender único como hoje.

---

## WP-AUTH-4: Error Codes + Settings Validation

**Meta**: Erros estruturados, settings validados.

**Mudanças**:
- **NOVO** `error_codes.py` — enum `ErrorCode` (RATE_LIMIT, CODE_EXPIRED, CODE_INVALID, CODE_MAX_ATTEMPTS, TOKEN_INVALID, TOKEN_EXPIRED, TOKEN_USED, ACCOUNT_NOT_FOUND, ACCOUNT_INACTIVE, COOLDOWN, SEND_FAILED).
- **MOD** Todos os Result dataclasses — `error_code: ErrorCode | None` adicionado.
- **MOD** `conf.py` — validação no boot de settings críticos.

**Risco**: BAIXO. Puramente aditivo.

---

## WP-AUTH-5: Middleware + request.customer

**Meta**: `request.customer` disponível em toda request.

**Mudanças**:
- **NOVO** `middleware.py` — `AuthCustomerMiddleware`:
  - Se `request.user.is_authenticated`: resolve customer via CustomerUser → adapter
  - `request.customer = AuthCustomerInfo | None`
  - Cache no user (1 query/request)
- **NOVO** `context_processors.py` — `customer` no template context.

**Risco**: BAIXO. Puramente aditivo.

---

## WP-AUTH-6: Storefront Migration (2 fases)

**Meta**: Migrar storefront de session keys para `request.user` / `request.customer`.

### Phase A — Dual Write
- `VerifyCodeView`, `DeviceCheckLoginView`: após `_set_auth_session()`, TAMBÉM chamar `login()`.
- Leituras continuam com session keys. Zero mudança de comportamento.

### Phase B — Cutover
- `get_authenticated_customer()`: ler de `request.customer` (middleware).
- `AccountView`, `CheckoutView`, `OrderHistoryView`: usar `request.customer`.
- Testes adaptados.
- Remover session keys, `_set_auth_session()`, constantes `SESSION_*`.

**Risco**: ALTO. Mitigações: dual-write primeiro, fallback na transição, cada fase independente.

---

## WP-AUTH-7: Device Management + Admin

**Meta**: Endpoints de gerenciamento + admin melhorado.

- **NOVO** `GET /auth/devices/`, `DELETE /auth/devices/<id>/`, `DELETE /auth/devices/`.
- **MOD** `admin.py` — actions: expirar codes, revogar devices, filtros.

**Risco**: BAIXO.

---

## Decisão: Flows e Stages — Por que adiar?

### O que são Flows (django-allauth)?

Camada de orchestration entre views e services. Em vez de a view chamar `AuthService.verify_for_login()` diretamente, ela chama `flows.login.perform_login()` que orquestra múltiplos passos.

### O que são Stages?

Multi-step auth como classes composáveis (`EmailVerificationStage`, `PhoneVerificationStage`). Um `LoginStageController` executa sequencialmente, cada stage retorna "continue" ou "block + response". Estado persiste na session entre requests.

### Impacto de NÃO ter

| Cenário | Sem flows/stages | Com flows/stages |
|---------|-----------------|-----------------|
| Login simples (OTP) | ✅ Funciona — service handle | ✅ Funciona — flow orquestra |
| MFA (phone + email) | ❌ Teria que inventar | ✅ Compõe stages |
| Login social + verificação | ❌ Teria que inventar | ✅ SocialLoginStage + VerifyStage |
| Reauthentication | ❌ Código ad-hoc | ✅ Stage reutilizável |
| Resumir flow interrompido | ❌ Perde estado | ✅ Session-based, resumable |

### Por que adiar (e quando fazer)

**Hoje**: O Shopman tem UM fluxo (OTP phone → verificar → logado). Services cobrem isso perfeitamente. Adicionar flows/stages para um fluxo só é over-engineering.

**Quando fazer**: Quando surgir o SEGUNDO fluxo que compartilha lógica com o primeiro:
- MFA (phone + email) → precisa compor stages
- Social login (Instagram → verificar phone) → precisa orquestrar
- Reauthentication para operações sensíveis → precisa de stage

**Preparação agora**: O adapter pattern (AUTH-2) já prepara o terreno. O `on_customer_authenticated()` hook é onde um flow controller se conectaria. Quando for hora, os services viram "step implementations" e o flow controller vira o orchestrator.

---

## Ordem de execução

```
AUTH-0  (Naming)            ✅ DONE
AUTH-1  (Backend)           ✅ DONE
AUTH-2  (Adapter)           ✅ DONE
AUTH-4  (Error Codes)       ✅ DONE
AUTH-3  (Delivery Chain)    ✅ DONE
AUTH-5  (Middleware)         ✅ DONE
AUTH-6A (Dual Write)        ✅ DONE
AUTH-6B (Cutover)           ✅ DONE
AUTH-7  (Device Mgmt)       ✅ DONE
```

## Verificação (por WP)

1. `make test` — 0 failures
2. `make lint` — 0 warnings
3. Testes novos do WP
4. Manual: fluxo OTP completo funciona
5. Grep por nomes antigos → zero (AUTH-0)

## Arquivos críticos

| Arquivo | WPs |
|---------|-----|
| `shopman/auth/conf.py` | 0, 1, 2, 3, 4, 5 |
| `shopman/auth/services/verification.py` | 0, 1, 2, 3, 4 |
| `shopman/auth/services/access_link.py` (rename) | 0, 1, 2 |
| `shopman/auth/models/verification_code.py` (rename) | 0 |
| `shopman/auth/models/customer_user.py` (rename) | 0 |
| `shopman/auth/models/access_link.py` (rename) | 0 |
| `shopman/auth/adapter.py` (NOVO) | 2, 3 |
| `shopman/auth/backends.py` (NOVO) | 1 |
| `shopman/auth/middleware.py` (NOVO) | 5 |
| `channels/web/views/auth.py` | 6A, 6B |

## O que NÃO está neste plano

| Item | Quando |
|------|--------|
| MFA / 2FA | Quando surgir segundo fluxo de auth |
| Flows / Stages | Quando surgir segundo fluxo de auth |
| Passkeys / WebAuthn | Anotado no ROADMAP.md |
| OAuth2 provider | Só com integrações terceiras |
| Audit log model | Sem breaking changes, qualquer momento |
| Contact verification | Follow-up natural após AUTH-6 |
