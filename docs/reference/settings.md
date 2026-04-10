# Referência de Configurações

> Gerado a partir dos arquivos `conf.py` e `apps.py` do código atual.

---

## Convenções

- Configurações são lidas via dicts no `settings.py` do Django (ex.: `STOCKMAN = {"HOLD_TTL_MINUTES": 30}`)
- Cada app core usa um padrão de `conf.py` com lazy proxy ou função `get_setting()`
- Settings do orquestrador (framework) usam prefixo `SHOPMAN_*` como settings flat
- Valores monetários são sempre em **centavos** (inteiro) — veja [ADR-002](../decisions/adr-002-centavos.md)

---

## Offerman (Catálogo)

**Arquivo:** `packages/offerman/shopman/offerman/conf.py`
**Dict:** `OFFERMAN = {}`

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `MAX_COLLECTION_DEPTH` | int | `10` | Profundidade máxima de aninhamento de coleções |
| `BUNDLE_MAX_DEPTH` | int | `5` | Profundidade máxima de bundles (prevenção de ciclos) |
| `COST_BACKEND` | str \| None | `None` | Dotted path do backend de custo. Carregado como singleton thread-safe |

**Guia:** [offering.md](../guides/offering.md)

---

## Stockman (Estoque)

**Arquivo:** `packages/stockman/shopman/stockman/conf.py`
**Dict:** `STOCKMAN = {}`

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `SKU_VALIDATOR` | str | `""` | Dotted path do validador de SKU externo |
| `HOLD_TTL_MINUTES` | int | `0` | TTL padrão de holds em minutos. `0` = sem expiração |
| `EXPIRED_BATCH_SIZE` | int | `200` | Tamanho do batch para `release_expired` |
| `VALIDATE_INPUT_SKUS` | bool | `True` | Valida SKUs via backend externo antes de operações |

**Guia:** [stocking.md](../guides/stocking.md)

### Stockman — Alertas

**Arquivo:** `packages/stockman/shopman/stockman/contrib/alerts/conf.py`
**Dict:** `STOCKMAN_ALERTS = {}` ou settings flat

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `STOCKMAN_ALERT_COOLDOWN_MINUTES` | int | `60` | Cooldown entre re-notificações do mesmo alerta |

---

## Craftsman (Produção)

**Arquivo:** `packages/craftsman/shopman/craftsman/conf.py`
**Dict:** `CRAFTSMAN = {}` ou settings flat `CRAFTSMAN_*`

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `INVENTORY_BACKEND` | str \| None | `None` | Dotted path do backend de inventário |
| `CATALOG_BACKEND` | str \| None | `None` | Dotted path do backend de catálogo |
| `DEMAND_BACKEND` | str \| None | `None` | Dotted path do backend de demanda |
| `SAFETY_STOCK_PERCENT` | Decimal | `0.20` | Percentual de estoque de segurança (20%) |
| `HISTORICAL_DAYS` | int | `28` | Janela de dados históricos em dias |
| `SAME_WEEKDAY_ONLY` | bool | `True` | Comparar apenas mesmo dia da semana no histórico |

**Guia:** [crafting.md](../guides/crafting.md)

---

## Omniman (Pedidos)

**Arquivo:** `packages/omniman/shopman/omniman/conf.py`
**Dict:** `OMNIMAN = {}`

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `DEFAULT_PERMISSION_CLASSES` | list | `["rest_framework.permissions.IsAuthenticated"]` | Permissões padrão das APIs REST |
| `ADMIN_PERMISSION_CLASSES` | list | `["rest_framework.permissions.IsAdminUser"]` | Permissões das APIs administrativas |

**Guia:** [ordering.md](../guides/ordering.md)

---

## Guestman (Clientes)

**Arquivo:** `packages/guestman/shopman/guestman/conf.py`
**Dict:** `GUESTMAN = {}`

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `DEFAULT_REGION` | str | `"BR"` | Região padrão para normalização de telefone |
| `EVENT_CLEANUP_DAYS` | int | `90` | Dias para manter ProcessedEvent antes de cleanup |
| `ORDER_HISTORY_BACKEND` | str | `""` | Dotted path do backend de histórico de pedidos |

**Guia:** [customers.md](../guides/customers.md)

### Guestman — Insights (RFM)

**Arquivo:** `packages/guestman/shopman/guestman/contrib/insights/conf.py`
**Dict:** `GUESTMAN_INSIGHTS = {}` ou settings flat

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `RFM_RECENCY_THRESHOLDS` | list[tuple] | `[(7,5), (30,4), (90,3), (180,2)]` | Thresholds de recência (dias, score) |
| `RFM_FREQUENCY_THRESHOLDS` | list[tuple] | `[(20,5), (10,4), (5,3), (2,2)]` | Thresholds de frequência (pedidos, score) |
| `RFM_MONETARY_THRESHOLDS` | list[tuple] | `[(1000000,5), (500000,4), (200000,3), (50000,2)]` | Thresholds monetários (centavos, score) |

### Guestman — Loyalty

**Arquivo:** `packages/guestman/shopman/guestman/contrib/loyalty/conf.py`
**Dict:** `GUESTMAN_LOYALTY = {}` ou settings flat

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `TIER_THRESHOLDS` | list[tuple] | `[(5000,"platinum"), (2000,"gold"), (500,"silver"), (0,"bronze")]` | Thresholds de nível por lifetime_points |

---

## Doorman (Autenticação)

**Arquivo:** `packages/doorman/shopman/doorman/conf.py`
**Dict:** `DOORMAN = {}`

### Access Link (chat → web)

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `ACCESS_LINK_EXCHANGE_TTL_MINUTES` | int | `5` | TTL do access link (Manychat/API) |
| `ACCESS_LINK_API_KEY` | str | `""` | **Obrigatório em produção.** Shared secret para `POST /auth/access/create/` |

### Access Link (email login)

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `ACCESS_LINK_ENABLED` | bool | `True` | Habilita login por email (one-click) |
| `ACCESS_LINK_TTL_MINUTES` | int | `15` | TTL do access link por email |
| `ACCESS_LINK_RATE_LIMIT_MAX` | int | `5` | Máx. access links por janela |
| `ACCESS_LINK_RATE_LIMIT_WINDOW_MINUTES` | int | `15` | Janela de rate limit |

### Código de Verificação (OTP)

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `ACCESS_CODE_TTL_MINUTES` | int | `10` | TTL do código OTP |
| `ACCESS_CODE_MAX_ATTEMPTS` | int | `5` | Máx. tentativas de verificação |
| `ACCESS_CODE_COOLDOWN_SECONDS` | int | `60` | Cooldown entre pedidos de código |
| `ACCESS_CODE_RATE_LIMIT_MAX` | int | `5` | Máx. códigos por janela |
| `ACCESS_CODE_RATE_LIMIT_WINDOW_MINUTES` | int | `15` | Janela de rate limit |

### Device Trust

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `DEVICE_TRUST_ENABLED` | bool | `True` | Habilita confiança de dispositivo |
| `DEVICE_TRUST_TTL_DAYS` | int | `30` | TTL do cookie (dias) |
| `DEVICE_TRUST_COOKIE_NAME` | str | `"shopman_auth_dt"` | Nome do cookie |

### Delivery (envio de códigos)

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `MESSAGE_SENDER_CLASS` | str | `"...ConsoleSender"` | Sender padrão. **Não usar em produção** (boot check impede). |
| `DELIVERY_CHAIN` | list | `[]` | Cadeia de fallback: `["whatsapp", "sms", "email"]` |
| `DELIVERY_SENDERS` | dict | `{}` | Map método → classe sender para a chain |
| `WHATSAPP_ACCESS_TOKEN` | str | `""` | Token da WhatsApp Cloud API |
| `WHATSAPP_PHONE_ID` | str | `""` | Phone ID do WhatsApp Cloud |
| `WHATSAPP_CODE_TEMPLATE` | str | `"verification_code"` | Nome do template WhatsApp |

### Integração

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `CUSTOMER_RESOLVER_CLASS` | str | `"...CustomersResolver"` | Resolver de customer para login |
| `AUTH_ADAPTER` | str | `"...DefaultAuthAdapter"` | Adapter (ponto de customização) |
| `AUTO_CREATE_CUSTOMER` | bool | `True` | Criar customer automaticamente no primeiro login |
| `PRESERVE_SESSION_KEYS` | list \| None | `None` | Keys da sessão a preservar no login (ex: `["cart_session_key"]`) |

### URLs e Segurança

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `DEFAULT_DOMAIN` | str | `"localhost:8000"` | Domínio para URLs geradas. **Não usar localhost em produção** (boot check impede). |
| `USE_HTTPS` | bool | `True` | Usar HTTPS nas URLs geradas |
| `LOGIN_REDIRECT_URL` | str | `"/"` | Redirecionamento pós-login |
| `LOGOUT_REDIRECT_URL` | str | `"/"` | Redirecionamento pós-logout |
| `ALLOWED_REDIRECT_HOSTS` | set | `set()` | Hosts permitidos no parâmetro `next` |
| `TRUSTED_PROXY_DEPTH` | int | `1` | Profundidade de X-Forwarded-For para IP |

### Templates

| Setting | Tipo | Default |
|---------|------|---------|
| `TEMPLATE_CODE_REQUEST` | str | `"auth/code_request.html"` |
| `TEMPLATE_CODE_VERIFY` | str | `"auth/code_verify.html"` |
| `TEMPLATE_ACCESS_LINK_INVALID` | str | `"auth/access_link_invalid.html"` |
| `TEMPLATE_ACCESS_LINK_REQUEST` | str | `"auth/access_link_request.html"` |
| `TEMPLATE_ACCESS_LINK_EMAIL_TXT` | str | `"auth/email_access_link.txt"` |
| `TEMPLATE_ACCESS_LINK_EMAIL_HTML` | str | `"auth/email_access_link.html"` |

### Boot Checks (produção)

O app **recusa iniciar** com `DEBUG=False` se:
- `ACCESS_LINK_API_KEY` está vazio
- `MESSAGE_SENDER_CLASS` é `ConsoleSender`
- `DEFAULT_DOMAIN` contém "localhost"

### Exemplo de configuração para produção

```python
# settings.py
DOORMAN = {
    "ACCESS_LINK_API_KEY": os.environ["AUTH_ACCESS_LINK_API_KEY"],
    "DEFAULT_DOMAIN": os.environ.get("AUTH_DEFAULT_DOMAIN", "shop.example.com"),
    "USE_HTTPS": True,
    "PRESERVE_SESSION_KEYS": ["cart_session_key"],
    "MESSAGE_SENDER_CLASS": "shopman.doorman.senders.WhatsAppCloudAPISender",
    "WHATSAPP_ACCESS_TOKEN": os.environ["WHATSAPP_ACCESS_TOKEN"],
    "WHATSAPP_PHONE_ID": os.environ["WHATSAPP_PHONE_ID"],
}
```

**Guia:** [auth.md](../guides/auth.md)

---

## Payments (Pagamentos)

O payments core não tem `conf.py` próprio — configuração é feita via settings do orquestrador (`SHOPMAN_PAYMENT_BACKEND`) e via `ChannelConfig.payment`.

Veja [Shopman — Orquestrador](#shopman--orquestrador) para `SHOPMAN_PAYMENT_BACKEND`.

---

## Shopman — Orquestrador

Settings flat no `settings.py` do Django (sem dict wrapper).

### Backends

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `SHOPMAN_STOCK_BACKEND` | str | *(auto-detecção)* | Backend de estoque. Se omitido, detecta `StockingBackend` → fallback `NoopStockBackend` |
| `SHOPMAN_PAYMENT_BACKEND` | str | `"channels.backends.payment_mock.MockPaymentBackend"` | Backend de pagamento |
| `SHOPMAN_FISCAL_BACKEND` | str | *(sem default)* | Backend fiscal. Se ausente, handlers fiscais não são registrados |
| `SHOPMAN_ACCOUNTING_BACKEND` | str | *(sem default)* | Backend de contabilidade. Se ausente, handler de accounting não é registrado |
| `SHOPMAN_NOTIFICATIONS` | str | `"console"` | Backend padrão de notificações |

**Guia:** [flows.md](../guides/flows.md)

### Webhook

**Dict:** `SHOPMAN_WEBHOOK = {}`

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `AUTH_TOKEN` | str \| None | `None` | Token de autenticação para webhooks |
| `DEFAULT_CHANNEL` | str | `"whatsapp"` | Canal padrão do webhook |
| `AUTH_HEADER` | str | `"X-Webhook-Token"` | Header HTTP de autenticação |

### ManyChat

Settings flat usados pela integração ManyChat:

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `MANYCHAT_API_TOKEN` | str | — | Token da API ManyChat. Se definido, ativa ManychatBackend de notificações |
| `MANYCHAT_FLOW_MAP` | dict | — | Mapa de evento → flow ID do ManyChat |

---

## Shop (Loja)

**App:** `framework/shopman/`
**Model:** `Shop` (singleton via `Shop.load()`)

A loja é configurada via Admin — não há settings no `settings.py`. O model `Shop` armazena:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | str | Nome completo da loja |
| `legal_name` | str | Razão social |
| `document` | str | CNPJ |
| `phone` | str | Telefone principal |
| `default_ddd` | str | DDD padrão para normalização de telefones |
| `currency` | str | Moeda (default: `"BRL"`) |
| `timezone` | str | Timezone (default: `"America/Sao_Paulo"`) |
| `opening_hours` | JSON | Horários de funcionamento |
| `branding` | JSON | `brand_name`, `short_name`, `tagline`, `primary_color`, `background_color`, `logo_url` |
| `social` | JSON | `website`, `instagram`, `whatsapp` |
| `defaults` | JSON | `ChannelConfig` dict — defaults globais para canais (cascata) |

### Cascata de Configuração de Canal

**`ChannelConfig` é o mecanismo primário de configuração de canais.** Substitui o antigo `settings.CONFIRMATION_FLOW`.

```
ChannelConfig efetivo = Channel.config ← Shop.defaults ← ChannelConfig.defaults()
```

Cada campo de `ChannelConfig` é resolvido na ordem: canal específico → defaults da loja → defaults hardcoded. Veja `ChannelConfig.effective()` em `shopman/config.py`.

O módulo `shopman/confirmation.py` mantém fallback legado para `settings.CONFIRMATION_FLOW`, mas o caminho principal é via `ChannelConfig.effective()`.

**Guia:** [flows.md](../guides/flows.md)

### ChannelConfig — Estrutura

| Seção | Campos principais | Descrição |
|-------|-------------------|-----------|
| `confirmation` | `mode` (immediate\|optimistic\|manual), `timeout_minutes` | Modo de confirmação |
| `payment` | `method` (counter\|pix\|external), `timeout_minutes` | Método de pagamento |
| `stock` | `hold_ttl_minutes`, `safety_margin`, `planned_hold_ttl_hours` | Configuração de reservas |
| `pipeline` | `on_commit`, `on_confirmed`, `on_payment_confirmed`, `on_ready`, `on_dispatched`, `on_delivered`, `on_completed`, `on_cancelled`, `on_returned` | Handlers por evento do ciclo de vida |
| `notifications` | `backend`, `fallback`, `routing` | Roteamento de notificações |
| `rules` | `validators`, `modifiers`, `checks` | Regras de negócio do canal |
| `flow` | `transitions`, `terminal_statuses`, `auto_transitions`, `auto_sync_fulfillment` | Máquina de estados |

### Promoções e Cupons

Configurados via Admin no model `Promotion` e `Coupon` (app `shop`):

| Model | Campos | Descrição |
|-------|--------|-----------|
| `Promotion` | `type` (percent\|fixed), `value`, `valid_from`, `valid_until`, `skus`, `collections`, `min_order_q` | Promoção automática ou por cupom |
| `Coupon` | `code`, `promotion` (FK), `max_uses`, `uses_count` | Cupom que ativa uma promoção |
