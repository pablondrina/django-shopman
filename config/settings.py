"""
Django settings for the Shopman project.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Make instances/ importable (e.g. nelson.customer_strategies). The instances
# directory lives at the repo root alongside config/ and shopman/, so it's
# BASE_DIR / "instances" — no .parent.
_instances_dir = str(Path(BASE_DIR) / "instances")
if _instances_dir not in sys.path:
    sys.path.insert(0, _instances_dir)

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


# ⚠️ PRODUÇÃO: Definir via DJANGO_SECRET_KEY env var. NUNCA usar o default.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")

# ⚠️ PRODUÇÃO: Definir DJANGO_DEBUG=false (default já é false)
DEBUG = _env_bool("DJANGO_DEBUG", False)

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
    # Shopman core integration contribs
    "shopman.craftsman.contrib.stockman",
    # Shopman core Unfold contribs
    "shopman.refs.contrib.admin_unfold",
    "shopman.offerman.contrib.admin_unfold",
    "shopman.stockman.contrib.admin_unfold",
    "shopman.craftsman.contrib.admin_unfold",
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
    # Optional instance/distribution apps
    *SHOPMAN_INSTANCE_APPS,
]

MIDDLEWARE = [
    "shopman.shop.middleware.AppPlatformHealthCheckHostMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "shopman.doorman.middleware.AuthCustomerMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "shopman.storefront.middleware.ChannelParamMiddleware",
    "shopman.backstage.middleware.OnboardingMiddleware",
    "shopman.shop.middleware.APIVersionHeaderMiddleware",
    "shopman.storefront.middleware.WelcomeGateMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "shopman.doorman.backends.PhoneOTPBackend",
    "django.contrib.auth.backends.ModelBackend",
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
                "shopman.storefront.context_processors.shop",
                "shopman.storefront.context_processors.omotenashi",
                "shopman.storefront.context_processors.cart_count",
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

# ── WhatsApp (Meta Cloud API + Bot F15) ─────────────────────────────
SHOPMAN_WHATSAPP = {
    "VERIFY_TOKEN": os.environ.get("WHATSAPP_VERIFY_TOKEN", ""),
    "STOREFRONT_URL": os.environ.get("WHATSAPP_STOREFRONT_URL", ""),
    # Meta Cloud API (opcional — ManyChat é o backend primário)
    # "PHONE_NUMBER_ID": os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
    # "ACCESS_TOKEN": os.environ.get("WHATSAPP_ACCESS_TOKEN", ""),
    # "MODE": "text",
}

# ── iFood (Marketplace F16) ────────────────────────────────────────
# Same rule as EFI: webhook_token is mandatory in every environment (including
# local dev). No skip flag. See shopman/shop/webhooks/efi.py for the pattern.
SHOPMAN_IFOOD = {
    "webhook_token": os.environ.get("IFOOD_WEBHOOK_TOKEN", ""),
    "merchant_id": os.environ.get("IFOOD_MERCHANT_ID", ""),
    "catalog_api_token": os.environ.get("IFOOD_CATALOG_API_TOKEN", ""),
    "catalog_api_base": os.environ.get("IFOOD_CATALOG_API_BASE", "https://merchant-api.ifood.com.br"),
}

# Catalog projection adapters — enable by uncommenting the desired backend.
# Missing key → handler not registered (silent skip).
# Present but broken path → raises at boot (configured-but-wrong).
SHOPMAN_CATALOG_PROJECTION_ADAPTERS: dict = {
    # "ifood": "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection",
}

# ── OTP Delivery Chain (depends on MANYCHAT_API_TOKEN above) ──────
if MANYCHAT_API_TOKEN:
    DOORMAN.update({
        "DELIVERY_CHAIN": ["whatsapp", "sms", "email"] if not DEBUG else ["whatsapp", "sms", "console"],
        "DELIVERY_SENDERS": {
            "whatsapp": "shopman.shop.adapters.otp_manychat.ManychatOTPSender",
            "sms": "shopman.doorman.senders.SMSSender",
            "email": "shopman.doorman.senders.EmailSender",
            "console": "shopman.doorman.senders.ConsoleSender",
        },
    })

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

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

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/minute",
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
    "PROJECTION_BACKENDS": {},
}

# ── Craftsman (micro-MRP integration) ──────────────────────────────

CRAFTSMAN = {
    "INVENTORY_BACKEND": "shopman.craftsman.adapters.stock.StockingBackend",
    "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
    "CATALOG_BACKEND": "shopman.offerman.adapters.catalog_backend.OffermanCatalogBackend",
}

STOCKMAN = {
    "SKU_VALIDATOR": os.environ.get(
        "STOCKMAN_SKU_VALIDATOR",
        "shopman.stockman.adapters.noop.NoopSkuValidator",
    ),
}

# Cooldown between repeated stock alerts for the same SKU (minutes).
STOCKMAN_ALERT_COOLDOWN_MINUTES = int(
    os.environ.get("STOCKMAN_ALERT_COOLDOWN_MINUTES", "60")
)

# ── Guestman ─────────────────────────────────────────────────────────

# Available keys: DEFAULT_REGION, EVENT_CLEANUP_DAYS, ORDER_HISTORY_BACKEND
# See packages/guestman/shopman/guestman/conf.py for defaults.
GUESTMAN = {}

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

SHOPMAN_FISCAL_ADAPTER = None   # str path or list[str] of FiscalBackend subclasses
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
    "certificate_path": os.environ.get("EFI_CERTIFICATE_PATH", ""),
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

# Ref of the Channel used for POS/counter orders.
SHOPMAN_POS_CHANNEL_REF = os.environ.get("SHOPMAN_POS_CHANNEL_REF", "pdv")

# ── Instance-specific modifiers ──────────────────────────────────────
# Dotted paths to modifier classes registered at boot.
# Example: ["instance.modifiers.D1DiscountModifier", "instance.modifiers.HappyHourModifier"]
SHOPMAN_INSTANCE_MODIFIERS = _csv_env_list("SHOPMAN_INSTANCE_MODIFIERS")

# ── Instance-specific settings (override via env or instance settings) ─
# Happy Hour — only active if the instance registers HappyHourModifier
SHOPMAN_HAPPY_HOUR_START = os.environ.get("SHOPMAN_HAPPY_HOUR_START", "17:30")
SHOPMAN_HAPPY_HOUR_END = os.environ.get("SHOPMAN_HAPPY_HOUR_END", "18:00")
SHOPMAN_HAPPY_HOUR_DISCOUNT_PERCENT = int(
    os.environ.get("SHOPMAN_HAPPY_HOUR_DISCOUNT_PERCENT", "25")
)

# Employee discount — configurable percentage
SHOPMAN_EMPLOYEE_DISCOUNT_PERCENT = int(
    os.environ.get("SHOPMAN_EMPLOYEE_DISCOUNT_PERCENT", "20")
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
