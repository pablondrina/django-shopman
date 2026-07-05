"""
Django settings for the Shopman project.
"""

import json
import os
from base64 import b64decode
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(Path(BASE_DIR) / ".env")


def _csv_env_list(name: str, default: str = "") -> list[str]:
    """Parse a comma-separated env var into a clean list."""
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("true", "1", "yes")


def _materialized_secret_file(*, content: str, filename: str) -> str:
    secret_dir = Path(os.environ.get("SHOPMAN_RUNTIME_SECRET_DIR", "/tmp/shopman-secrets"))
    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret_path = secret_dir / filename
    if not secret_path.exists() or secret_path.read_text() != content:
        secret_path.write_text(content)
        secret_path.chmod(0o600)
    return str(secret_path)


def _efi_certificate_path() -> str:
    configured_path = os.environ.get("EFI_CERTIFICATE_PATH", "").strip()
    if configured_path:
        return configured_path

    encoded = (
        os.environ.get("EFI_CERTIFICATE_PEM_BASE64", "").strip()
        or os.environ.get("EFI_CERTIFICATE_BASE64", "").strip()
    )
    if encoded:
        pem = b64decode(encoded).decode("utf-8")
        return _materialized_secret_file(content=pem, filename="efi_certificate.pem")

    pem = os.environ.get("EFI_CERTIFICATE_PEM", "").strip()
    if pem:
        return _materialized_secret_file(content=pem.replace("\\n", "\n"), filename="efi_certificate.pem")

    return ""


# ⚠️ PRODUÇÃO: Definir via DJANGO_SECRET_KEY env var. NUNCA usar o default.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")

# ⚠️ PRODUÇÃO: Definir DJANGO_DEBUG=false (default já é false)
DEBUG = _env_bool("DJANGO_DEBUG", False)


def _default_shopman_environment() -> str:
    hints = " ".join(
        os.environ.get(name, "")
        for name in (
            "SHOPMAN_DOMAIN",
            "WHATSAPP_STOREFRONT_URL",
            "DJANGO_ALLOWED_HOSTS",
            "APP_DOMAIN",
            "APP_URL",
        )
    ).lower()
    if "staging" in hints:
        return "staging"
    return "development" if DEBUG else "production"


SHOPMAN_ENVIRONMENT = os.environ.get(
    "SHOPMAN_ENVIRONMENT",
    _default_shopman_environment(),
).strip().lower()

SHOPMAN_EXPOSE_DEBUG_OTP = _env_bool(
    "SHOPMAN_EXPOSE_DEBUG_OTP",
    DEBUG or SHOPMAN_ENVIRONMENT == "staging",
)

# ⚠️ PRODUÇÃO: Restringir a domínios reais. "*" é apenas para desenvolvimento.
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

_trust_forwarded_proto = os.environ.get(
    "DJANGO_TRUST_X_FORWARDED_PROTO",
    "true" if not DEBUG else "false",
).lower() in ("true", "1", "yes")
if _trust_forwarded_proto:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

if DEBUG:
    # Permitir os domínios públicos do ngrok ao expor o dev server.
    # ALLOWED_HOSTS recebe os padrões explicitamente para funcionar mesmo quando
    # DJANGO_ALLOWED_HOSTS está restrito no .env. O prefixo "." cobre qualquer subdomínio.
    ALLOWED_HOSTS += [
        ".ngrok-free.app",
        ".ngrok-free.dev",
        ".ngrok.io",
        ".ngrok.app",
        ".trycloudflare.com",
    ]
    CSRF_TRUSTED_ORIGINS += [
        "https://*.ngrok-free.app",
        "https://*.ngrok-free.dev",
        "https://*.ngrok.io",
        "https://*.ngrok.app",
        "https://*.trycloudflare.com",
        # Nuxt dev surfaces: storefront :3000 · pos :3002 · kds :3003 · gestor :3004
        # · fournil :3005 · central :3006 (backstage legado :3001).
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3003",
        "http://localhost:3004",
        "http://127.0.0.1:3004",
        "http://localhost:3005",
        "http://127.0.0.1:3005",
        "http://localhost:3006",
        "http://127.0.0.1:3006",
    ]

SHOPMAN_INSTANCE_APPS = _csv_env_list("SHOPMAN_INSTANCE_APPS")

INSTALLED_APPS = [
    # Daphne — replaces runserver with ASGI handler so django-eventstream's
    # SSE views can stream without monopolizing a worker. MUST be at the top
    # so its `runserver` overrides the staticfiles one.
    "daphne",
    # Unfold admin theme (MUST be before django.contrib.admin)
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    # Django core
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "csp",
    "taggit",
    "rest_framework",
    "drf_spectacular",
    "import_export",
    "unfold.contrib.import_export",
    "django_ratelimit",
    "django_eventstream",
    "simple_history",
    # 2FA (django-otp) — TOTP devices for admin step-up (gated by SHOPMAN_ADMIN_REQUIRE_2FA)
    "django_otp",
    "django_otp.plugins.otp_totp",
    # Shopman core apps
    "shopman.refs",
    "shopman.utils",
    "shopman.offerman",
    "shopman.stockman",
    "shopman.craftsman",
    "shopman.orderman",
    "shopman.payman",
    "shopman.guestman",
    "shopman.doorman",
    "shopman.buyman",
    "shopman.fiscalman",
    # Shopman core integration contribs
    "shopman.craftsman.contrib.stockman",
    "shopman.craftsman.contrib.formula",
    # Shopman core Unfold contribs
    "shopman.refs.contrib.admin_unfold",
    "shopman.offerman.contrib.admin_unfold",
    "shopman.fiscalman.contrib.offerman",
    "shopman.stockman.contrib.admin_unfold",
    "shopman.craftsman.contrib.admin_unfold",
    "shopman.payman.contrib.admin_unfold",
    "shopman.buyman.contrib.admin_unfold",
    "shopman.stockman.contrib.alerts",
    "shopman.guestman.contrib.consent",
    "shopman.guestman.contrib.identifiers",
    "shopman.guestman.contrib.insights",
    "shopman.guestman.contrib.loyalty",
    "shopman.guestman.contrib.preferences",
    "shopman.guestman.contrib.timeline",
    "shopman.guestman.contrib.merge",
    "shopman.guestman.contrib.admin_unfold",
    "shopman.doorman.contrib.admin_unfold",
    # Shopman orchestrator
    "shopman.shop",
    # Shopman surfaces
    "shopman.storefront",
    "shopman.backstage",
    # Deployment app — deployment-level tooling (the `seed` command). No models.
    "config",
    # Optional instance/distribution apps
    *SHOPMAN_INSTANCE_APPS,
]

MIDDLEWARE = [
    "shopman.shop.middleware.AppPlatformHealthCheckHostMiddleware",
    # Scopes session/CSRF cookies to the operator zone's parent domain (no-op
    # unless SHOPMAN_OPERATOR_COOKIE_DOMAIN). High in the stack so its response
    # phase runs AFTER Session/CSRF middleware set their cookies.
    "shopman.shop.middleware.OperatorSessionDomainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # OTP verification state (request.user.is_verified()) — must follow auth.
    "django_otp.middleware.OTPMiddleware",
    "shopman.doorman.middleware.AuthCustomerMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "shopman.storefront.middleware.ChannelParamMiddleware",
    "shopman.backstage.middleware.OnboardingMiddleware",
    # Admin 2FA gate (no-op unless SHOPMAN_ADMIN_REQUIRE_2FA) — after OTPMiddleware.
    "shopman.backstage.middleware_2fa.AdminTwoFactorMiddleware",
    "shopman.shop.middleware.APIVersionHeaderMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "shopman.doorman.backends.PhoneOTPBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Senhas de staff/admin (clientes autenticam por OTP, sem senha). Sem estes
# validadores, `createsuperuser`/reset aceitavam qualquer coisa e o `check --deploy`
# não acusava. Os 4 defaults do Django: similaridade, comprimento mínimo, senhas
# comuns e não-100%-numérica.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

DOORMAN = {
    "PRESERVE_SESSION_KEYS": ["cart_session_key"],
    "DEFAULT_DOMAIN": os.environ.get("AUTH_DEFAULT_DOMAIN", "localhost:8000"),
    "USE_HTTPS": not DEBUG,
    "ACCESS_LINK_API_KEY": os.environ.get("DOORMAN_ACCESS_LINK_API_KEY", ""),
    "MESSAGE_SENDER_CLASS": os.environ.get(
        "DOORMAN_MESSAGE_SENDER_CLASS",
        "shopman.doorman.senders.ConsoleSender",
    ),
    "CUSTOMER_RESOLVER_CLASS": os.environ.get(
        "DOORMAN_CUSTOMER_RESOLVER_CLASS",
        "shopman.guestman.adapters.auth.CustomerResolver",
    ),
    # OTP delivery: WhatsApp (via ManyChat) → SMS → email
    # Configured dynamically below after MANYCHAT_API_TOKEN is read
}

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shopman.backstage.context_processors.operator",
            ],
        },
    },
]

# Database — Postgres quando DATABASE_URL estiver setado; SQLite como fallback leve.
# Postgres é o default documentado (`make up` + docker-compose) para exercitar
# select_for_update() e os testes de concorrência do Stockman.
import urllib.parse as _urlparse

_DB_URL = os.environ.get("DATABASE_URL", "").strip()
if _DB_URL:
    _parsed = _urlparse.urlparse(_DB_URL)
    _conn_max_age = int(os.environ.get("DATABASE_CONN_MAX_AGE", "60"))
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _parsed.path.lstrip("/"),
            "USER": _parsed.username or "",
            "PASSWORD": _parsed.password or "",
            "HOST": _parsed.hostname or "",
            "PORT": _parsed.port or 5432,
            "CONN_MAX_AGE": _conn_max_age,
            "CONN_HEALTH_CHECKS": _env_bool("DATABASE_CONN_HEALTH_CHECKS", True),
            "DISABLE_SERVER_SIDE_CURSORS": _env_bool(
                "DATABASE_DISABLE_SERVER_SIDE_CURSORS", False
            ),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
            "OPTIONS": {
                "timeout": 10,
            },
        }
    }

# Cache: django-ratelimit exige backend compartilhado (Redis/Memcached), não LocMem.
# Dev sem Redis: LocMem + checks silenciados (rate limit só no processo atual).
# Produção: defina REDIS_URL (ex.: redis://127.0.0.1:6379/1).
_redis_url = os.environ.get("REDIS_URL", "").strip()
if _redis_url:
    _redis_parsed = _urlparse.urlparse(_redis_url)
    _redis_db = int((_redis_parsed.path or "/0").lstrip("/") or "0")
    _redis_kwargs = {
        "host": _redis_parsed.hostname or "localhost",
        "port": _redis_parsed.port or 6379,
        "db": _redis_db,
    }
    if _redis_parsed.username:
        _redis_kwargs["username"] = _urlparse.unquote(_redis_parsed.username)
    if _redis_parsed.password:
        _redis_kwargs["password"] = _urlparse.unquote(_redis_parsed.password)
    if _redis_parsed.scheme == "rediss":
        _redis_kwargs["ssl"] = True

    CACHES = {
        "default": {
            # Native Django Redis backend keeps the runtime aligned with
            # Django 6. django-ratelimit 4.1 has a stale allowlist and emits
            # W001 for this backend, silenced below after our own Redis check.
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
        }
    }
    SILENCED_SYSTEM_CHECKS = [
        *globals().get("SILENCED_SYSTEM_CHECKS", []),
        "django_ratelimit.W001",
    ]
    # django-eventstream uses this setting for multiprocess fanout: send_event
    # publishes to Redis and every Daphne/ASGI worker wakes its local listeners.
    EVENTSTREAM_REDIS = _redis_kwargs
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    if DEBUG:
        SILENCED_SYSTEM_CHECKS = [
            "django_ratelimit.E003",
            "django_ratelimit.W001",
        ]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = os.environ.get("STATIC_ROOT", os.path.join(BASE_DIR, "staticfiles"))

_staticfiles_storage_backend = os.environ.get("DJANGO_STATICFILES_STORAGE") or (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if not DEBUG
    else "django.contrib.staticfiles.storage.StaticFilesStorage"
)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": _staticfiles_storage_backend,
    },
}
WHITENOISE_MANIFEST_STRICT = os.environ.get(
    "WHITENOISE_MANIFEST_STRICT",
    "true" if not DEBUG else "false",
).lower() in ("true", "1", "yes")

MEDIA_ROOT = os.path.join(BASE_DIR, "media")
MEDIA_URL = "/media/"

# ── Google Maps ──────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# ── Stripe ────────────────────────────────────────────────────────────
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")

# ── Manychat (WhatsApp via ManyChat) ────────────────────────────────
MANYCHAT_API_TOKEN = os.environ.get("MANYCHAT_API_TOKEN", "")
MANYCHAT_WEBHOOK_SECRET = os.environ.get("MANYCHAT_WEBHOOK_SECRET", "")
MANYCHAT_FLOW_MAP = {
    # Mapeia eventos de notificação → ManyChat flow namespace.
    # Se vazio, ManychatBackend envia mensagem texto direta (sem flow).
    # Para usar flows, configure no ManyChat e mapeie aqui:
    # "order_confirmed": "content20250401120000_123456",
    # "payment_confirmed": "content20250401120000_234567",
}
try:
    MANYCHAT_API_TIMEOUT = int(os.environ.get("MANYCHAT_API_TIMEOUT", "15"))
except ValueError:
    MANYCHAT_API_TIMEOUT = 15
SHOPMAN_MANYCHAT = {
    "api_token": MANYCHAT_API_TOKEN,
    "base_url": os.environ.get("MANYCHAT_API_BASE", "https://api.manychat.com/fb"),
    "timeout": MANYCHAT_API_TIMEOUT,
    "resolver": os.environ.get(
        "MANYCHAT_SUBSCRIBER_RESOLVER",
        "shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.resolve",
    ),
    "flow_map": MANYCHAT_FLOW_MAP,
}

# ── WhatsApp (Meta Cloud API direto — spike/avaliação) ──────────────
# Seam para o adapter notification_whatsapp (Meta Cloud API direto, sem ManyChat).
# Inerte enquanto PHONE_NUMBER_ID/ACCESS_TOKEN vazios. Decisão ManyChat-vs-direto:
# docs/plans/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md.
SHOPMAN_WHATSAPP = {
    "VERIFY_TOKEN": os.environ.get("WHATSAPP_VERIFY_TOKEN", ""),
    "STOREFRONT_URL": os.environ.get("WHATSAPP_STOREFRONT_URL", ""),
    "PHONE_NUMBER_ID": os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
    "ACCESS_TOKEN": os.environ.get("WHATSAPP_ACCESS_TOKEN", ""),
    "GRAPH_VERSION": os.environ.get("WHATSAPP_GRAPH_VERSION", "v21.0"),
    "DEFAULT_LANG": os.environ.get("WHATSAPP_TEMPLATE_LANG", "pt_BR"),
    "timeout": MANYCHAT_API_TIMEOUT,
    # event → Meta template config. Vazio = manda texto (só dentro da janela 24h).
    # Preencher com os templates Utility/Auth aprovados na Meta:
    #   "order_confirmed": {"name": "pedido_confirmado", "body": ["order_ref", "total"]},
    "templates": {},
}

# ── iFood (Marketplace F16) ────────────────────────────────────────
# Same rule as EFI: webhook_token is mandatory in every environment (including
# local dev). No skip flag. See shopman/shop/webhooks/efi.py for the pattern.
SHOPMAN_IFOOD = {
    "webhook_token": os.environ.get("IFOOD_WEBHOOK_TOKEN", ""),
    "merchant_id": os.environ.get("IFOOD_MERCHANT_ID", ""),
    # API direta (OAuth client_credentials) — app no Portal do Desenvolvedor iFood.
    "client_id": os.environ.get("IFOOD_CLIENT_ID", "").strip(),
    "client_secret": os.environ.get("IFOOD_CLIENT_SECRET", "").strip(),
    "api_base": os.environ.get("IFOOD_API_BASE", "https://merchant-api.ifood.com.br"),
    "timeout": int(os.environ.get("IFOOD_TIMEOUT", "30")),
    # Catalog projection (v2.0): maps internal collection refs → iFood category
    # UUIDs. Items whose collection is unmapped fall back to the default; with
    # neither, the projection fails loudly (an item needs a target category).
    "catalog_category_map": json.loads(os.environ.get("IFOOD_CATALOG_CATEGORY_MAP", "{}")),
    "catalog_default_category": os.environ.get("IFOOD_CATALOG_DEFAULT_CATEGORY", ""),
    # Order cancellation (WP-4): iFood requires a cancellationCode from its fixed
    # list. Discover valid codes per order via ifood_callbacks.fetch_cancellation_reasons.
    # Empty → a cancellation callback fails loudly (must be set post-homologação).
    "cancellation_default_code": os.environ.get("IFOOD_CANCELLATION_CODE", ""),
    # iFood requires a non-empty `reason` alongside the code (400 otherwise).
    "cancellation_default_reason": os.environ.get(
        "IFOOD_CANCELLATION_REASON", "Problemas de sistema na loja"
    ),
    # Webhook push (WP-5, optional): HMAC-SHA256 secret for X-IFood-Signature.
    # Defaults to client_secret (per plan). Set from the portal's webhook section
    # if iFood provisions a distinct signing secret.
    "webhook_hmac_secret": os.environ.get(
        "IFOOD_WEBHOOK_HMAC_SECRET", os.environ.get("IFOOD_CLIENT_SECRET", "")
    ).strip(),
}

# Catalog projection backends — project catalog changes (create/update/price/
# availability) to external channels. This is the *canonical* registry, owned by
# Offerman (OFFERMAN["PROJECTION_BACKENDS"], resolved by get_projection_backend()).
# Both the signal-driven auto-trigger (CatalogProjectHandler, per-SKU delta) and
# the manual sync_catalog_ifood command (CatalogService.project_listing, per-listing
# reconciliation) resolve their backend through this single registry.
# Missing key → handler + signals no-op. Present but broken path → raises at boot.
# Enabled per-environment via env flag so no deployment pushes to iFood until
# explicitly turned on (requires the iFood OAuth config to be present).
_CATALOG_PROJECTION_BACKENDS: dict[str, str] = {}
if os.environ.get("IFOOD_CATALOG_PROJECTION", "").strip().lower() in ("1", "true", "yes"):
    _CATALOG_PROJECTION_BACKENDS["ifood"] = (
        "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection"
    )

# ── SMS (Comtele — OTP por SMS) ─────────────────────────────────────
# WhatsApp OTP não é viável (ManyChat não tem categoria Authentication; o número único da marca
# não fica em ManyChat + Cloud API ao mesmo tempo). O código de login vai por SMS — canal padrão
# de OTP. Inerte até api_key + route. Ver docs/plans/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md.
# API NOVA (portal.comtele.com.br): header `x-api-key` no endpoint api.comtele.com.br/messages/sms/send.
# A chave vem do portal (Configurações → Chaves de API). route = ID da rota de envio da conta
# (GET api.comtele.com.br/routes lista; use a transacional/Premium p/ OTP, não a Marketing).
SHOPMAN_SMS = {
    # Comtele (provedor BR — sender ativo). .strip() evita 401 por '\n'/espaço colado na env.
    "api_key": os.environ.get("COMTELE_API_KEY", "").strip(),
    "route": os.environ.get("COMTELE_ROUTE", "").strip(),
    "tag": os.environ.get("COMTELE_TAG", "shopman-otp"),
    # Twilio (fallback pronto — trocar o sender em DELIVERY_SENDERS['sms'] p/ usar).
    "account_sid": os.environ.get("TWILIO_ACCOUNT_SID", ""),
    "auth_token": os.environ.get("TWILIO_AUTH_TOKEN", ""),
    "from_number": os.environ.get("TWILIO_FROM_NUMBER", ""),
    "messaging_service_sid": os.environ.get("TWILIO_MESSAGING_SERVICE_SID", ""),
    "code_message": os.environ.get("SHOPMAN_SMS_CODE_MESSAGE", ""),
    "timeout": MANYCHAT_API_TIMEOUT,
}

# ── Dev-safety: adapters externos inertes em DEBUG ──────────────────
# Em DEBUG as credenciais reais ficam no .env, então SMS/WhatsApp/OTP disparariam
# mensagens de verdade num `seed`, num shell ou no dev server. A trava
# (shopman.shop.adapters._external.inert_in_debug) mantém esses adapters inertes
# em DEBUG salvo opt-in explícito. Fora de DEBUG nada disto tem efeito.
SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG = _env_bool("SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG", False)
SHOPMAN_SMS_ALLOW_IN_DEBUG = _env_bool("SHOPMAN_SMS_ALLOW_IN_DEBUG", False)
SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG = _env_bool("SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG", False)
SHOPMAN_WHATSAPP_ALLOW_IN_DEBUG = _env_bool("SHOPMAN_WHATSAPP_ALLOW_IN_DEBUG", False)

# ── OTP Delivery Chain ───────────────────────────────────────────────
# SMS primário (Twilio), email como fallback. WhatsApp fica mapeado mas FORA da cadeia
# (ManyChat não emite template de Authentication). Debug usa console para ver o código.
DOORMAN["DELIVERY_SENDERS"] = {
    "sms": "shopman.shop.adapters.otp_sms_comtele.ComteleSMSSender",
    "email": "shopman.doorman.senders.EmailSender",
    "whatsapp": "shopman.shop.adapters.otp_manychat.ManychatOTPSender",
    "console": "shopman.doorman.senders.ConsoleSender",
}
if SHOPMAN_EXPOSE_DEBUG_OTP and SHOPMAN_ENVIRONMENT == "staging":
    DOORMAN.update({
        "MESSAGE_SENDER_CLASS": "shopman.doorman.senders.LogSender",
        "DELIVERY_CHAIN": [],
    })
else:
    DOORMAN["DELIVERY_CHAIN"] = ["sms", "email"] if not DEBUG else ["sms", "console"]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# Catálogo de tradução do projeto. O django-unfold não embarca traduções, então
# suas strings próprias ("Add new item", filtros, etc.) caem para o inglês — aqui
# fornecemos o pt-BR. Tem precedência sobre os catálogos dos apps.
LOCALE_PATHS = [os.path.join(BASE_DIR, "locale")]

# ── Unfold Admin ────────────────────────────────────────────────────
# SITE_TITLE callable reads Shop.name via model import (lazy).

from django.urls import reverse_lazy  # noqa: E402


def _unfold_site_title(request=None):
    try:
        from shopman.shop.models import Shop
        shop = Shop.load()
        return shop.name if shop else "Shopman"
    except Exception:
        return "Shopman"


UNFOLD = {
    "SITE_TITLE": _unfold_site_title,
    "SITE_HEADER": _unfold_site_title,
    "SITE_SYMBOL": "store",
    "DASHBOARD_CALLBACK": "shopman.backstage.admin.dashboard.dashboard_callback",
    "COMMAND": {
        "search_models": True,
        "show_history": True,
    },
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "STYLES": [],
    "COLORS": {
        "primary": {
            "50": "rgb(245, 240, 235)",
            "100": "rgb(237, 229, 220)",
            "200": "rgb(213, 196, 170)",
            "300": "rgb(197, 165, 90)",
            "400": "rgb(178, 148, 75)",
            "500": "rgb(158, 131, 62)",
            "600": "rgb(130, 107, 48)",
            "700": "rgb(97, 80, 36)",
            "800": "rgb(61, 43, 31)",
            "900": "rgb(41, 29, 21)",
            "950": "rgb(25, 17, 12)",
        },
    },
    "TABS": [
        {
            "models": ["offerman.product", "offerman.collection", "offerman.listing"],
            "items": [
                {"title": "Produtos", "link": reverse_lazy("admin:offerman_product_changelist")},
                {"title": "Colecoes", "link": reverse_lazy("admin:offerman_collection_changelist")},
                {"title": "Listagens", "link": reverse_lazy("admin:offerman_listing_changelist")},
            ],
        },
        {
            "models": [
                "stockman.quant",
                "stockman.move",
                "stockman.hold",
                "stockman.batch",
                "stockman.position",
                "stockman.stockalert",
            ],
            "items": [
                {"title": "Saldo", "link": reverse_lazy("admin:stockman_quant_changelist")},
                {"title": "Movimentos", "link": reverse_lazy("admin:stockman_move_changelist")},
                {"title": "Reservas", "link": reverse_lazy("admin:stockman_hold_changelist")},
                {"title": "Lotes", "link": reverse_lazy("admin:stockman_batch_changelist")},
            ],
        },
        {
            "models": ["craftsman.recipe", "craftsman.workorder"],
            "items": [
                {"title": "Painel", "link": reverse_lazy("admin_console_production_dashboard")},
                {"title": "Planejamento", "link": reverse_lazy("admin_console_production_planning")},
                {"title": "Produção", "link": reverse_lazy("admin_console_production")},
                {"title": "Fichas técnicas", "link": reverse_lazy("admin:craftsman_recipe_changelist")},
                {"title": "Relatórios", "link": reverse_lazy("admin_console_production_reports")},
            ],
        },
        {
            "models": ["orderman.order", "orderman.session", "orderman.directive"],
            "items": [
                {"title": "Pedidos", "link": reverse_lazy("admin:orderman_order_changelist")},
                {"title": "Sessoes", "link": reverse_lazy("admin:orderman_session_changelist")},
                {"title": "Diretivas", "link": reverse_lazy("admin:orderman_directive_changelist")},
            ],
        },
    ],
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "command_search": True,
        "navigation": "shopman.backstage.admin.navigation.get_sidebar_navigation",
    },
}

# ── Email ──────────────────────────────────────────────────────────

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in ("true", "1")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@shopman.local")

# ── REST Framework ─────────────────────────────────────────────────

# Anonymous API throttle is a per-IP guardrail (120/min by default). It can be
# tuned — or disabled (empty string → no rate) — via env. Disable it ONLY for
# synthetic single-IP load testing, where one client IP would otherwise trip the
# shared limit and you'd be measuring the throttle instead of the backend.
_ANON_THROTTLE_RATE = os.environ.get("SHOPMAN_API_ANON_THROTTLE_RATE", "120/minute").strip()

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Só sessão — NUNCA BasicAuth: o default do DRF habilitaria user:senha em
    # toda a API, abrindo brute-force de senha staff sem lockout e contornando
    # o 2FA do Admin e o CSRF nos endpoints de operador.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": _ANON_THROTTLE_RATE or None,
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Shopman API",
    "DESCRIPTION": "API do Django Shopman — commerce suite modular.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "GuestmanCustomerTypeEnum": [
            ("individual", "Pessoa Física"),
            ("business", "Pessoa Jurídica"),
        ],
        "CraftsmanWorkOrderStatusEnum": [
            ("planned", "Planejada"),
            ("started", "Iniciada"),
            ("finished", "Concluída"),
            ("void", "Cancelada"),
        ],
        "PaymanPaymentIntentStatusEnum": [
            ("pending", "Pendente"),
            ("authorized", "Autorizado"),
            ("captured", "Capturado"),
            ("failed", "Falhou"),
            ("cancelled", "Cancelado"),
            ("refunded", "Reembolsado"),
        ],
    },
}

# ── Logging ────────────────────────────────────────────────────────────

# ── Offerman ──────────────────────────────────────────────────────

OFFERMAN = {
    # TODO WP-R2: restore cost backend adapter
    "COST_BACKEND": None,
    "PRICING_BACKEND": "shopman.shop.adapters.pricing.StorefrontPricingBackend",
    # Canonical catalog projection registry (env-gated above).
    "PROJECTION_BACKENDS": _CATALOG_PROJECTION_BACKENDS,
}

# ── Craftsman (micro-MRP integration) ──────────────────────────────

CRAFTSMAN = {
    # Stock ledger writes (consume ingredients + receive output) flow through the
    # `production_changed` signal handlers in craftsman.contrib.stockman — the
    # single canonical write path. INVENTORY_BACKEND is intentionally unset: it is
    # a read-only seam for ingredient-availability validation, to be implemented
    # by Buyman/Material (see docs/plans/BUYMAN-PROCUREMENT-PLAN.md).
    "INVENTORY_BACKEND": "shopman.shop.adapters.inventory.InventoryAvailabilityBackend",
    "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
    # Composed: Offerman (vendáveis) + Buyman (insumos/Material). Resolução-only
    # (unidade do insumo p/ cross-check de RecipeItem) — não toca disponibilidade.
    "CATALOG_BACKEND": "shopman.shop.adapters.catalog_backend.ComposedCatalogBackend",
    # Campo estruturado Recipe.meta["production_lifecycle"] no admin de receitas:
    # as variantes vivem no dispatch do orquestrador (ADR-007); o pacote só
    # renderiza o que o provider entrega (sem provider = sem campo).
    "PRODUCTION_LIFECYCLE_PROVIDER": "shopman.shop.production_lifecycle.production_lifecycle_choices",
}

STOCKMAN = {
    # Shelf-life LIGADO (Buyman WP-B5): validator composto resolve vendáveis pelo
    # Offerman (is_sellable/shelf_life/pause reais) e insumos pelo Buyman (Material).
    # Disponibilidade de VENDA filtra vencidos/pausados; holds de PRODUÇÃO
    # (purpose="workorder") reservam estoque físico e ignoram o gate de venda
    # (insumo é não-vendável por natureza) — ver StockHolds.hold + test_production_stock.
    # A lot-consistency (Batch.clean) ativa com validator real configurado.
    "SKU_VALIDATOR": os.environ.get(
        "STOCKMAN_SKU_VALIDATOR",
        "shopman.shop.adapters.sku_validator.ComposedSkuValidator",
    ),
    # When on, a lot whose expiry exceeds the product's shelf_life window is
    # rejected at save; off (default) surfaces it as a non-blocking admin warning.
    "STRICT_SHELF_LIFE_WINDOW": _env_bool("STOCKMAN_STRICT_SHELF_LIFE_WINDOW", False),
}

# Cooldown between repeated stock alerts for the same SKU (minutes).
STOCKMAN_ALERT_COOLDOWN_MINUTES = int(
    os.environ.get("STOCKMAN_ALERT_COOLDOWN_MINUTES", "60")
)

# ── Guestman ─────────────────────────────────────────────────────────

# Available keys: DEFAULT_REGION, EVENT_CLEANUP_DAYS, ORDER_HISTORY_BACKEND
# See packages/guestman/shopman/guestman/conf.py for defaults.
_GUESTMAN_ORDER_HISTORY_BACKEND = os.environ.get(
    "GUESTMAN_ORDER_HISTORY_BACKEND",
    "shopman.guestman.adapters.orderman.OrdermanOrderHistoryBackend",
)
GUESTMAN = (
    {"ORDER_HISTORY_BACKEND": _GUESTMAN_ORDER_HISTORY_BACKEND}
    if _GUESTMAN_ORDER_HISTORY_BACKEND
    else {}
)

# RFM thresholds. Empty dict uses built-in defaults from conf.py.
# Keys: RFM_RECENCY_THRESHOLDS, RFM_FREQUENCY_THRESHOLDS, RFM_MONETARY_THRESHOLDS
GUESTMAN_INSIGHTS = {}

# Loyalty tier thresholds. Empty dict uses built-in defaults from conf.py.
# Keys: TIER_THRESHOLDS
GUESTMAN_LOYALTY = {}

# ── Orderman ─────────────────────────────────────────────────────────

# Available keys: DEFAULT_PERMISSION_CLASSES, ADMIN_PERMISSION_CLASSES
# See packages/orderman/shopman/orderman/conf.py for defaults.
ORDERMAN = {}

# ── Shopman Instance Hooks (optional) ────────────────────────────────

# Customer strategy modules to load on startup.
# Each module must register its strategies on import.
# Default is empty: the framework base must stay instance-agnostic.
SHOPMAN_CUSTOMER_STRATEGY_MODULES = _csv_env_list(
    "SHOPMAN_CUSTOMER_STRATEGY_MODULES"
)

# ── Shopman Adapters ──────────────────────────────────────────────────

SHOPMAN_PAYMENT_ADAPTERS = {
    "pix": os.environ.get("SHOPMAN_PIX_ADAPTER", "shopman.shop.adapters.payment_mock"),
    "card": os.environ.get("SHOPMAN_CARD_ADAPTER", "shopman.shop.adapters.payment_mock"),
    "cash": None,
    "external": None,
}
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS = _env_bool("SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", False)
SHOPMAN_MOCK_PIX_AUTO_CONFIRM = _env_bool("SHOPMAN_MOCK_PIX_AUTO_CONFIRM", False)
SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS = int(
    os.environ.get("SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS", "10")
)

SHOPMAN_NOTIFICATION_ADAPTERS = {
    "manychat": "shopman.shop.adapters.notification_manychat",
    "email": "shopman.shop.adapters.notification_email",
}
if DEBUG or os.environ.get("SHOPMAN_ENABLE_CONSOLE_NOTIFICATION_ADAPTER", "").lower() in ("true", "1", "yes"):
    SHOPMAN_NOTIFICATION_ADAPTERS["console"] = "shopman.shop.adapters.notification_console"

SHOPMAN_STOCK_ADAPTER = "shopman.shop.adapters.stock"

SHOPMAN_FISCAL_ADAPTER = os.environ.get("SHOPMAN_FISCAL_ADAPTER") or None

# Resolver(es) plugáveis que decidem SE a NFC-e é emitida por pedido: caminho pontilhado
# para um callable(order) -> bool. VÁRIOS separados por vírgula = OR. Motor em
# fiscal.emission_resolver; exemplos + combinadores (any_of/all_of/not_) em
# shopman.shop.fiscal_resolvers.
# PADRÃO PRÁTICO (Nelson): on_request_or_tax_id — emite se o operador pediu OU o cliente
# informou CPF/CNPJ ("CPF na nota"). Pablo redefine no go-live via env.
SHOPMAN_FISCAL_EMISSION_RESOLVER = (
    os.environ.get("SHOPMAN_FISCAL_EMISSION_RESOLVER")
    or "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
)
SHOPMAN_FOCUS_NFE = {
    "environment": os.environ.get("FOCUS_NFE_ENVIRONMENT", "homologacao").strip().lower() or "homologacao",
    "token": os.environ.get("FOCUS_NFE_TOKEN", ""),
    "cnpj_emitente": os.environ.get("FOCUS_NFE_CNPJ_EMITENTE", ""),
    "serie_nfce": os.environ.get("FOCUS_NFE_NFCE_SERIE", ""),
    "completa_nfce": os.environ.get("FOCUS_NFE_NFCE_COMPLETA", "1"),
    "local_destino_nfce": os.environ.get("FOCUS_NFE_NFCE_LOCAL_DESTINO", "1"),
    "presenca_comprador_nfce": os.environ.get("FOCUS_NFE_NFCE_PRESENCA_COMPRADOR", "1"),
    "modalidade_frete_nfce": os.environ.get("FOCUS_NFE_NFCE_MODALIDADE_FRETE", "9"),
    "natureza_operacao": os.environ.get("FOCUS_NFE_NATUREZA_OPERACAO", "VENDA AO CONSUMIDOR"),
    "default_cfop_nfce": os.environ.get("FOCUS_NFE_NFCE_DEFAULT_CFOP", "5102"),
    "timeout": int(os.environ.get("FOCUS_NFE_TIMEOUT", "30")),
    "base_url": os.environ.get("FOCUS_NFE_BASE_URL", ""),
}
SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q = int(
    os.environ.get("SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q", "0")
)
SHOPMAN_ACCOUNTING_BACKEND = None

# SMS adapter for OTP delivery. None = fallback to notification_sms if available.
SHOPMAN_SMS_ADAPTER = None

# Operator email for backend notifications (order alerts, etc.).
# Falls back to DEFAULT_FROM_EMAIL if None.
SHOPMAN_OPERATOR_EMAIL = None

# PIX payment expiry in seconds (default: 1 hour).
SHOPMAN_PIX_EXPIRY_SECONDS = int(
    os.environ.get("SHOPMAN_PIX_EXPIRY_SECONDS", "3600")
)

SHOPMAN_STRIPE = {
    "publishable_key": STRIPE_PUBLISHABLE_KEY,
    "secret_key": STRIPE_SECRET_KEY,
    "webhook_secret": os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
    "capture_method": os.environ.get("STRIPE_CAPTURE_METHOD", "manual"),
    # Public origin used to build absolute success_url / cancel_url passed to
    # Stripe Checkout. Must include scheme (http://localhost:8000 in dev).
    "domain": os.environ.get("SHOPMAN_DOMAIN", "http://localhost:8000"),
}

SHOPMAN_EFI = {
    "sandbox": os.environ.get("EFI_SANDBOX", "true").lower() in ("true", "1", "yes"),
    "client_id": os.environ.get("EFI_CLIENT_ID", ""),
    "client_secret": os.environ.get("EFI_CLIENT_SECRET", ""),
    "certificate_path": _efi_certificate_path(),
    "pix_key": os.environ.get("EFI_PIX_KEY", ""),
}

SHOPMAN_EFI_WEBHOOK = {
    # Shared secret between EFI dashboard and this service. MUST be set in
    # every environment — including local dev — because webhook authentication
    # uses the exact same code path in dev and prod. No bypass flag.
    #
    # Local dev: set EFI_WEBHOOK_TOKEN in `.env` to any non-empty value and
    # use `make shopman-efi-test-webhook` (or the equivalent test fixture) to
    # POST test payloads signed with the same token. See
    # shopman/shop/webhooks/efi.py for the verification contract.
    "webhook_token": os.environ.get("EFI_WEBHOOK_TOKEN", ""),
    # Optional: header name that a fronting proxy (nginx, traefik) sets to
    # "SUCCESS" after validating EFI's mTLS client certificate. When present
    # and equal to "SUCCESS", the request is treated as pre-authenticated by
    # the proxy. The shared token is still verified as defense-in-depth.
    "mtls_header": os.environ.get("EFI_MTLS_HEADER", "HTTP_X_SSL_CLIENT_VERIFY"),
}

# ── Server-Sent Events (django-eventstream) ──────────────────────────
# Persistence backend for SSE events. The ORM backend stores reliable event ids.
# When REDIS_URL is set, EVENTSTREAM_REDIS is derived above so send_event from
# any process reaches every active SSE listener across Daphne/ASGI workers.
EVENTSTREAM_STORAGE_CLASS = "django_eventstream.storage.DjangoModelStorage"
EVENTSTREAM_CHANNELMANAGER_CLASS = "shopman.shop.eventstream.ShopmanChannelManager"

ASGI_APPLICATION = "config.asgi.application"

# ── Storefront channel ────────────────────────────────────────────────
# Ref of the Channel that powers the web storefront. Override in instance settings
# if this instance uses a different ref (e.g. "site", "loja").
SHOPMAN_STOREFRONT_CHANNEL_REF = "web"

# Base URL pública da LOJA (superfície Nuxt) — FONTE ÚNICA dos links de cliente que o
# Django gera (notificações de pagamento/acompanhamento, magic links, "ver site").
# O Django é headless: não serve páginas de cliente, só aponta para a loja Nuxt.
# Na arquitetura desacoplada, em produção isto vira o apex (ex.: https://nelson.com);
# em staging path-routed, a base da loja (ex.: https://…/thing). Sem trailing slash.
SHOPMAN_STOREFRONT_BASE_URL = (
    os.environ.get("SHOPMAN_STOREFRONT_BASE_URL")
    or os.environ.get("WHATSAPP_STOREFRONT_URL")
    or os.environ.get("SHOPMAN_DOMAIN")
    or ""
).strip().rstrip("/")

# Magic links (doorman AccessLink) land on the Nuxt store, so the session cookie
# is set on the store host — same single source as every other customer link.
DOORMAN["ACCESS_LINK_ENTRY_URL"] = SHOPMAN_STOREFRONT_BASE_URL

# Ref of the Channel used for POS/counter orders.
SHOPMAN_POS_CHANNEL_REF = os.environ.get("SHOPMAN_POS_CHANNEL_REF", "pdv")

# Base URL pública da superfície POS (operador) — a mesma ideia de
# SHOPMAN_STOREFRONT_BASE_URL, mas para o PDV, que migrou para o seu próprio
# app Nuxt (surfaces/pos-nuxt). Vazio ⇒ o POS não está conectado neste
# contexto (ex.: o gate Omotenashi storefront+operador não sobe o POS), e os
# links/checks de POS são pulados em vez de apontarem para uma rota morta.
SHOPMAN_POS_BASE_URL = (
    os.environ.get("SHOPMAN_POS_BASE_URL") or ""
).strip().rstrip("/")

# Base URL pública do Gestor de Pedidos (operador) — app Nuxt dedicado
# (surfaces/orders-nuxt). Vazio ⇒ o item "Pedidos" some do nav do Admin
# (sem link morto), e o operador acessa direto pelo subdomínio (gestor.).
SHOPMAN_ORDERS_BASE_URL = (
    os.environ.get("SHOPMAN_ORDERS_BASE_URL") or ""
).strip().rstrip("/")

# Base URL pública do KDS (operador) — app Nuxt dedicado (surfaces/kds-nuxt).
# Vazio ⇒ o item "KDS" some do nav do Admin (sem link morto).
SHOPMAN_KDS_BASE_URL = (
    os.environ.get("SHOPMAN_KDS_BASE_URL") or ""
).strip().rstrip("/")

# Base URL pública da Produção (operador) — app Nuxt dedicado
# (surfaces/production-nuxt). Vazio ⇒ o item "Produção ao vivo" some do nav
# do Admin (sem link morto), e o operador acessa direto pelo subdomínio (prod.).
SHOPMAN_PRODUCTION_BASE_URL = (
    os.environ.get("SHOPMAN_PRODUCTION_BASE_URL") or ""
).strip().rstrip("/")

# Zona de operador (OPERATOR-AUTH-PLAN, Opção A) — login único + sessão Django
# escopada a um domínio-pai SEPARADO da loja pública. Os apps de operador
# (gestor./kds./pdv./prod.) moram nesse domínio e proxeiam para o alias de API
# abaixo; o `OperatorSessionDomainMiddleware` escopa o cookie de sessão/CSRF para
# `SHOPMAN_OPERATOR_COOKIE_DOMAIN` SÓ quando o host servido é o de operador — assim
# o login do cliente (host-only na loja) fica intocado.
#   · SHOPMAN_OPERATOR_COOKIE_DOMAIN: ex. ".boulangerie.com.br" (com ponto). Vazio ⇒
#     middleware é no-op (comportamento atual host-only para todos).
#   · SHOPMAN_OPERATOR_API_HOST: host da API que os apps de operador proxeiam, ex.
#     "api.boulangerie.com.br" (o proxy Nuxt reescreve o Host para esse alias).
SHOPMAN_OPERATOR_COOKIE_DOMAIN = (os.environ.get("SHOPMAN_OPERATOR_COOKIE_DOMAIN") or "").strip()
SHOPMAN_OPERATOR_API_HOST = (os.environ.get("SHOPMAN_OPERATOR_API_HOST") or "").strip()

# URLs das superfícies para a Central de Apps (surfaces/hub-nuxt). Em prod, aponte cada
# tile ao subdomínio (`https://pdv.…`, `https://gestor.…`); vazio ⇒ o launcher usa os
# defaults de dev (127.0.0.1:PORT) de `projections/hub.py`. A Loja deep-linka pro Unfold.
SHOPMAN_SURFACE_URLS = {
    key: url
    for key, url in {
        "pos": (os.environ.get("SHOPMAN_SURFACE_POS_URL") or "").strip(),
        "kds": (os.environ.get("SHOPMAN_SURFACE_KDS_URL") or "").strip(),
        "gestor": (os.environ.get("SHOPMAN_SURFACE_GESTOR_URL") or "").strip(),
        "production": (os.environ.get("SHOPMAN_SURFACE_PRODUCTION_URL") or "").strip(),
        "loja": (os.environ.get("SHOPMAN_SURFACE_LOJA_URL") or "").strip(),
    }.items()
    if url
}

# Autorização Opção C: quando ON, as ações de backstage são autorizadas contra o
# OPERADOR ATIVO (estabelecido por PIN/crachá), não o usuário da sessão do device.
# Default OFF (a sessão do device decide — comportamento atual). Liga-se junto com a
# tela de trava/destrava nos apps (WP-AUTH-2c) + a zona de operador no ar.
SHOPMAN_REQUIRE_ACTIVE_OPERATOR = (
    os.environ.get("SHOPMAN_REQUIRE_ACTIVE_OPERATOR", "false").strip().lower() == "true"
)

# 2FA obrigatório no Admin (django-otp/TOTP) — gated por env. Default OFF para não
# trancar fora antes do enrollment; ligar (env="true") só depois de cada superuser
# ter um TOTPDevice confirmado (management command `setup_admin_totp`). Em PROD,
# combinar com IP allowlist no ingress do admin. (OPERATOR-APPS-PLAN Fase 3 · WP-A1.)
SHOPMAN_ADMIN_REQUIRE_2FA = (os.environ.get("SHOPMAN_ADMIN_REQUIRE_2FA", "") or "").strip().lower() in {
    "1", "true", "yes", "on",
}

# Employee discount — configurable percentage
SHOPMAN_EMPLOYEE_DISCOUNT_PERCENT = int(
    os.environ.get("SHOPMAN_EMPLOYEE_DISCOUNT_PERCENT", "20")
)

SHOPMAN_CART_MUTATION_PERF_LOG_MS = float(
    os.environ.get("SHOPMAN_CART_MUTATION_PERF_LOG_MS", "0")
)

# ── Rules security — allowed module prefixes for RuleConfig.rule_path ──
# Any rule_path not starting with one of these prefixes is rejected at clean()
# and at load time (defense-in-depth). Extend with care — adding a prefix
# effectively grants staff the ability to instantiate arbitrary classes from
# that module, which is a security surface.
SHOPMAN_RULES_ALLOWED_MODULE_PREFIXES = [
    "shopman.shop.rules.",
    "shopman.shop.modifiers.",
]

# ── Logging ────────────────────────────────────────────────────────────

SHOPMAN_JSON_LOGS = os.environ.get(
    "SHOPMAN_JSON_LOGS",
    "true" if not DEBUG else "false",
).lower() in ("true", "1", "yes")
_SHOPMAN_LOG_FORMATTER = "json" if SHOPMAN_JSON_LOGS else "verbose"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
        "json": {
            "()": "shopman.shop.logging.JsonLogFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": _SHOPMAN_LOG_FORMATTER,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "shopman": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# ── Storefront: acompanhamento do pedido ─────────────────────────────
# Cadência do polling do tracking (segundos). Default 30 (referência iFood).
# Configurável por deployment enquanto o push por SSE não é o principal; o campo
# no Admin (Shop) é follow-up coordenado com a migração do backstage.
STOREFRONT_TRACKING_POLL_SECONDS = int(
    os.environ.get("STOREFRONT_TRACKING_POLL_SECONDS", "30") or "30"
)

# ── Error tracking (Sentry) ───────────────────────────────────────────
#
# Opt-in e à prova de ausência: só ativa quando SENTRY_DSN está setado E o
# sentry-sdk está instalado. Sem isso, um 500 no checkout só aparecia se alguém
# estivesse lendo o log do DO. send_default_pii=False por privacidade (LGPD) —
# não mandar dados do cliente para o serviço externo.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        _sentry_traces = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0") or "0")
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=SHOPMAN_ENVIRONMENT,
            integrations=[DjangoIntegration()],
            traces_sample_rate=_sentry_traces,
            send_default_pii=False,
        )
    except Exception:  # pragma: no cover - inerte sem a dependência
        import logging as _logging

        _logging.getLogger("shopman.settings").warning(
            "SENTRY_DSN setado mas sentry-sdk não pôde inicializar — error tracking OFF.",
            exc_info=True,
        )

# ── Security ──────────────────────────────────────────────────────────

# Headers always active (safe in dev too)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_SSL_REDIRECT = os.environ.get(
    "DJANGO_SECURE_SSL_REDIRECT",
    "true" if not DEBUG else "false",
).lower() in ("true", "1", "yes")
SECURE_REDIRECT_EXEMPT = [
    r"^health/$",
    r"^ready/$",
]

# Content Security Policy (django-csp v4 format)
# CDN audit:
#   HTMX        → unpkg.com
#   Alpine.js   → cdn.jsdelivr.net
#   Fonts/Icons → fonts.googleapis.com, fonts.gstatic.com
#   Maps        → maps.googleapis.com
#   Stripe      → js.stripe.com, api.stripe.com
#   ViaCEP      → viacep.com.br
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": [
            "'self'",
            "'unsafe-eval'",  # Alpine.js requires eval
            "https://unpkg.com",
            "https://cdn.jsdelivr.net",
            "https://maps.googleapis.com",
            "https://js.stripe.com",
        ],
        "style-src": [
            "'self'",
            "'unsafe-inline'",  # Tailwind + design tokens inline
            "https://fonts.googleapis.com",
        ],
        "img-src": ["'self'", "data:", "https:", "blob:"],
        "font-src": ["'self'", "https://fonts.gstatic.com"],
        "connect-src": [
            "'self'",
            "https://maps.googleapis.com",
            "https://api.stripe.com",
            "https://viacep.com.br",
        ],
        "frame-src": ["https://js.stripe.com"],
    },
}

if DEBUG:
    # Relax CSP in development: allow inline scripts (HTMX config snippets, debug toolbar)
    # and local WebSocket for hot reload / ngrok tunnels.
    _csp_directives = CONTENT_SECURITY_POLICY["DIRECTIVES"]
    _csp_directives["script-src"] = list(_csp_directives["script-src"]) + ["'unsafe-inline'"]
    _csp_directives["connect-src"] = list(_csp_directives["connect-src"]) + ["ws://localhost:*"]

# PERMISSIONS_POLICY requires the separate django-permissions-policy package.
# Not configured here to avoid a broken/ignored setting.
# Install django-permissions-policy and add PermissionsPolicyMiddleware to enable it.

if not DEBUG:
    assert SECRET_KEY != "dev-secret-key-not-for-production", (
        "SECRET_KEY must be set in production (DJANGO_SECRET_KEY env var)"
    )
    assert ALLOWED_HOSTS != ["*"], (
        "ALLOWED_HOSTS must be explicit in production (DJANGO_ALLOWED_HOSTS env var)"
    )

    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
