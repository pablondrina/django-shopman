# Auth — Autenticação Passwordless

## Visão Geral

O app `shopman.auth` implementa autenticação passwordless com três fluxos de login (OTP, Access Link, Email Access Link), confiança de dispositivo e rate limiting. Não depende de senhas — a identidade é verificada via código enviado por WhatsApp/SMS/Email.

## Conceitos

### OTP (VerificationCode)
Código de verificação enviado por WhatsApp/SMS/Email. Hash HMAC-SHA256 no banco (nunca plaintext). TTL de 10 minutos, máximo 5 tentativas.

### Access Link
Token para transição chat→web (ex: Manychat → checkout web). TTL curto (5 min), uso único com janela de reuso de 60s para browser prefetch.

### Email Access Link
Link de login por email com Access Link embutido. TTL de 15 minutos.

### Dispositivo Confiável (`TrustedDevice`)
Cookie seguro que permite pular OTP em logins futuros. TTL de 30 dias.

### CustomerUser
Mapeamento Django User ↔ Customer (Customers). Desacopla autenticação de gestão de clientes.

### Gates (Validações)
Regras de segurança com códigos:
- **G7** — Validade do Access Link
- **G8** — Validade do VerificationCode
- **G9** — Rate limit por target (phone/email)
- **G10** — Rate limit por IP
- **G11** — Cooldown entre códigos
- **G12** — Rate limit de Access Links por email

## Modelos

### VerificationCode

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUIDField(pk) | UUID |
| `code_hash` | CharField(64) | HMAC-SHA256 (nunca plaintext) |
| `target_value` | CharField(255) | Phone (E.164) ou email |
| `purpose` | CharField | LOGIN ou VERIFY_CONTACT |
| `status` | CharField | PENDING, SENT, VERIFIED, EXPIRED, FAILED |
| `delivery_method` | CharField | WHATSAPP, SMS, EMAIL |
| `attempts` | PositiveSmallIntegerField | Tentativas falhas |
| `max_attempts` | PositiveSmallIntegerField | Máximo (default: 5) |
| `expires_at` | DateTimeField | Expiração (default: 10 min) |
| `ip_address` | GenericIPAddressField(null) | IP do solicitante |
| `customer_id` | UUIDField(null) | UUID do cliente (set após verificação) |

### AccessLink

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUIDField(pk) | UUID |
| `token` | CharField(64, unique) | Token seguro (secrets.token_urlsafe) |
| `customer_id` | UUIDField | UUID do cliente |
| `audience` | CharField | WEB_CHECKOUT, WEB_ACCOUNT, WEB_SUPPORT, WEB_GENERAL |
| `source` | CharField | MANYCHAT, INTERNAL, API |
| `metadata` | JSONField | {method, email, ...} |
| `expires_at` | DateTimeField | Expiração (default: 5 min) |
| `used_at` | DateTimeField(null) | Quando usado |
| `user` | FK(User, null) | User Django vinculado após exchange |

### TrustedDevice

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUIDField(pk) | UUID |
| `customer_id` | UUIDField | UUID do cliente |
| `token_hash` | CharField(64, unique) | HMAC-SHA256 do token |
| `user_agent` | CharField(512) | Browser/device |
| `label` | CharField(100) | Label legível (ex: "Chrome / iPhone") |
| `expires_at` | DateTimeField | Expiração (default: 30 dias) |
| `last_used_at` | DateTimeField(null) | Último uso |
| `is_active` | BooleanField | Ativo |

### CustomerUser

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `user` | OneToOne(User) | Django User |
| `customer_id` | UUIDField(unique) | UUID do cliente no Customers |
| `metadata` | JSONField | Info de dispositivo, login |

## Serviços

### AuthService (OTP)

```python
from shopman.auth.services.verification import AuthService

# Solicitar código
result = AuthService.request_code(
    target_value="+5511999999999",
    purpose="login",
    delivery_method="whatsapp",
    ip_address="177.100.0.1",
)
# CodeRequestResult(success=True, code_id=UUID(...), expires_at=...)

# Verificar código
result = AuthService.verify_for_login(
    target_value="+5511999999999",
    code_input="123456",
)
# VerifyResult(success=True, customer=<AuthCustomerInfo>, created_customer=False)
```

Pipeline do `request_code`:
1. Normaliza phone
2. Aplica G9 (rate limit), G11 (cooldown), G10 (IP rate limit)
3. Invalida códigos anteriores
4. Gera código + hash HMAC
5. Envia código raw via sender

Pipeline do `verify_for_login`:
1. Busca código válido (status, expiração, tentativas)
2. Compara via HMAC timing-safe
3. Resolve/cria Customer via CustomerResolver
4. Marca como VERIFIED

### AccessLinkService

```python
from shopman.auth.services.access_link import AccessLinkService

# Criar token (ex: chamado pelo Manychat)
result = AccessLinkService.create_token(
    customer=customer_info,
    audience="web_checkout",
    source="manychat",
)
# TokenResult(success=True, token="abc123...", url="https://shop.com/auth/bridge/?token=abc123...")

# Exchange (no web, quando usuário clica no link)
result = AccessLinkService.exchange(
    token_str="abc123...",
    request=http_request,
)
# AuthResult(success=True, user=<User>, customer=<AuthCustomerInfo>)
```

Pipeline do `exchange`:
1. Busca AccessLink
2. Aplica G7 (validade, audience)
3. Resolve Customer via CustomerResolver
4. Get/create Django User + CustomerUser
5. Preserva session keys (ex: carrinho)
6. `django.contrib.auth.login()`

### AccessLinkService (email)

```python
from shopman.auth.services.access_link import AccessLinkService

result = AccessLinkService.send_access_link(
    email="maria@email.com",
    ip_address="177.100.0.1",
)
# → Envia email com link de exchange (TTL: 15 min)
```

### DeviceTrustService

```python
from shopman.auth.services.device_trust import DeviceTrustService

# Verificar confiança
confia = DeviceTrustService.check_device_trust(request, customer_id=uuid)

# Confiar dispositivo (após login bem-sucedido)
device = DeviceTrustService.trust_device(response, customer_id=uuid, request=request)
# → Seta cookie HttpOnly, Secure, SameSite=Lax

# Revogar
DeviceTrustService.revoke_device(request, response)
DeviceTrustService.revoke_all(customer_id=uuid)
```

## Protocols

### CustomerResolver

Interface para resolver clientes (desacopla do Customers).

```python
class CustomerResolver(Protocol):
    def get_by_phone(self, phone: str) -> AuthCustomerInfo | None: ...
    def get_by_email(self, email: str) -> AuthCustomerInfo | None: ...
    def get_by_uuid(self, uuid: UUID) -> AuthCustomerInfo | None: ...
    def create_for_phone(self, phone: str) -> AuthCustomerInfo: ...
```

### MessageSenderProtocol

Interface para envio de códigos.

```python
class MessageSenderProtocol(Protocol):
    def send_code(self, target: str, code: str, method: str) -> bool: ...
```

**Implementações:** `ConsoleSender` (dev), `LogSender` (teste), `WhatsAppCloudAPISender` (prod), `SMSSender`, `EmailSender`

## Configuração

Chave Django settings: `AUTH`

| Setting | Default | Descrição |
|---------|---------|-----------|
| `ACCESS_LINK_EXCHANGE_TTL_MINUTES` | 5 | TTL do Access Link |
| `ACCESS_CODE_TTL_MINUTES` | 10 | TTL do código OTP |
| `ACCESS_CODE_MAX_ATTEMPTS` | 5 | Máximo de tentativas |
| `ACCESS_CODE_RATE_LIMIT_MAX` | 5 | Máx. códigos por janela |
| `ACCESS_CODE_RATE_LIMIT_WINDOW_MINUTES` | 15 | Janela de rate limit |
| `ACCESS_CODE_COOLDOWN_SECONDS` | 60 | Cooldown entre códigos |
| `MESSAGE_SENDER_CLASS` | ConsoleSender | Classe de envio |
| `CUSTOMER_RESOLVER_CLASS` | AttendingCustomerResolver | Resolver de clientes |
| `DEVICE_TRUST_ENABLED` | True | Habilitar confiança de dispositivo |
| `DEVICE_TRUST_TTL_DAYS` | 30 | TTL do cookie |
| `ACCESS_LINK_ENABLED` | True | Habilitar Access Link por email |
| `AUTO_CREATE_CUSTOMER` | True | Criar cliente automaticamente no login |
| `USE_HTTPS` | True | Usar HTTPS nas URLs |

## Segurança

| Padrão | Implementação |
|--------|---------------|
| Hash HMAC-SHA256 | Códigos e tokens nunca armazenados em plaintext |
| Comparação timing-safe | `hmac.compare_digest()` previne timing attacks |
| Cookie seguro | HttpOnly, Secure (prod), SameSite=Lax |
| Rate limiting | G9 (target), G10 (IP), G11 (cooldown), G12 (access link) |
| Reuso de token | G7 permite 60s para browser prefetch |
| Desacoplamento | CustomerResolver desacopla do Customers |
| Preservação de sessão | Session keys preservadas no login (carrinho) |

## Exemplos

### Fluxo OTP completo

```python
from shopman.auth.services.verification import AuthService
from shopman.auth.services.device_trust import DeviceTrustService

# 1. Solicitar código
result = AuthService.request_code(
    target_value="+5511999999999",
    delivery_method="whatsapp",
)

# 2. Verificar (usuário digita o código)
verify = AuthService.verify_for_login(
    target_value="+5511999999999",
    code_input="123456",
)
if verify.success:
    # 3. Confiar dispositivo para próximos logins
    DeviceTrustService.trust_device(response, verify.customer.uuid, request)
```

### Fluxo Manychat → Web

```python
from shopman.auth.services.access_link import AccessLinkService

# No Manychat (bot cria link para checkout)
token_result = AccessLinkService.create_token(
    customer=customer_info,
    audience="web_checkout",
    source="manychat",
)
# → Envia token_result.url ao usuário no WhatsApp

# No Web (usuário clica no link)
auth_result = AccessLinkService.exchange(
    token_str=request.GET["token"],
    request=request,
)
# → Usuário logado, sessão preservada
```
