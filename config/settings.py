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

# ⚠️ PRODUÇÃO: Definir via DJANGO_SECRET_KEY env var. NUNCA usar o default.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")

# ⚠️ PRODUÇÃO: Definir DJANGO_DEBUG=false (default já é false)
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("true", "1", "yes")

# ⚠️ PRODUÇÃO: Restringir a domínios reais. "*" é apenas para desenvolvimento.
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if DEBUG:
    # Permitir os domínios públicos do ngrok ao expor o dev server.
    # ALLOWED_HOSTS recebe os padrões explicitamente para funcionar mesmo quando
    # DJANGO_ALLOWED_HOSTS está restrito no .env. O prefixo "." cobre qualquer subdomínio.
    ALLOWED_HOSTS += [
        ".ngrok-free.app",
        ".ngrok-free.dev",
        ".ngrok.io",
        ".ngrok.app",
    ]
    CSRF_TRUSTED_ORIGINS += [
        "https://*.ngrok-free.app",
        "https://*.ngrok-free.dev",
        "https://*.ngrok.io",
        "https://*.ngrok.app",
    ]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

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
    # Shopman core apps
    "shopman.utils",
    "shopman.offerman",
    "shopman.stockman",
    "shopman.craftsman",
    "shopman.orderman",
    "shopman.payman",
    "shopman.guestman",
    "shopman.doorman",
    # Shopman core Unfold contribs
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
    # Optional instance/distribution apps
    *SHOPMAN_INSTANCE_APPS,
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "shopman.doorman.middleware.AuthCustomerMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "shopman.shop.middleware.ChannelParamMiddleware",
    "shopman.shop.middleware.OnboardingMiddleware",
    "shopman.shop.middleware.WelcomeGateMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "shopman.doorman.backends.PhoneOTPBackend",
    "django.contrib.auth.backends.ModelBackend",
]

DOORMAN = {
    "PRESERVE_SESSION_KEYS": ["cart_session_key"],
    "DEFAULT_DOMAIN": os.environ.get("AUTH_DEFAULT_DOMAIN", "localhost:8000"),
    "USE_HTTPS": not DEBUG,
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
                "shopman.shop.context_processors.shop",
                "shopman.shop.context_processors.omotenashi",
                "shopman.shop.context_processors.cart_count",
            ],
        },
    },
]

# ⚠️ PRODUÇÃO: Usar PostgreSQL. SQLite não suporta concorrência.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}

# Cache: django-ratelimit exige backend compartilhado (Redis/Memcached), não LocMem.
# Dev sem Redis: LocMem + checks silenciados (rate limit só no processo atual).
# Produção: defina REDIS_URL (ex.: redis://127.0.0.1:6379/1).
_redis_url = os.environ.get("REDIS_URL", "").strip()
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": _redis_url,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
    }
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
MANYCHAT_OTP_FLOW_NS = os.environ.get("MANYCHAT_OTP_FLOW_NS", "")
MANYCHAT_FLOW_MAP = {
    # Mapeia eventos de notificação → ManyChat flow namespace.
    # Se vazio, ManychatBackend envia mensagem texto direta (sem flow).
    # Para usar flows, configure no ManyChat e mapeie aqui:
    # "order_confirmed": "content20250401120000_123456",
    # "payment_confirmed": "content20250401120000_234567",
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
    "DASHBOARD_CALLBACK": "shopman.shop.admin.dashboard.dashboard_callback",
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
                {"title": "Receitas", "link": reverse_lazy("admin:craftsman_recipe_changelist")},
                {"title": "Ordens de Producao", "link": reverse_lazy("admin:craftsman_workorder_changelist")},
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
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Painel",
                "separator": True,
                "items": [
                    {"title": "Dashboard", "icon": "dashboard", "link": reverse_lazy("admin:index")},
                ],
            },
            {
                "title": "Loja",
                "separator": True,
                "items": [
                    {"title": "Configuração", "icon": "storefront", "link": reverse_lazy("admin:shop_shop_changelist")},
                ],
            },
            {
                "title": "Central Omnicanal",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Canais", "icon": "network_node", "link": reverse_lazy("admin:shop_channel_changelist")},
                    {"title": "Sessoes", "icon": "note_alt", "link": reverse_lazy("admin:orderman_session_changelist")},
                    {"title": "Pedidos", "icon": "assignment", "link": reverse_lazy("admin:orderman_order_changelist")},
                ],
            },
            {
                "title": "Catalogo",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Produtos", "icon": "inventory_2", "link": reverse_lazy("admin:offerman_product_changelist")},
                    {"title": "Colecoes", "icon": "category", "link": reverse_lazy("admin:offerman_collection_changelist")},
                    {"title": "Listagens", "icon": "shoppingmode", "link": reverse_lazy("admin:offerman_listing_changelist")},
                ],
            },
            {
                "title": "Estoque",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Saldo", "icon": "point_scan", "link": reverse_lazy("admin:stockman_quant_changelist")},
                    {"title": "Movimentos", "icon": "swap_horiz", "link": reverse_lazy("admin:stockman_move_changelist")},
                    {"title": "Reservas", "icon": "keep", "link": reverse_lazy("admin:stockman_hold_changelist")},
                    {"title": "Lotes", "icon": "science", "link": reverse_lazy("admin:stockman_batch_changelist")},
                    {"title": "Posicoes", "icon": "domain", "link": reverse_lazy("admin:stockman_position_changelist")},
                    {"title": "Alertas", "icon": "notification_important", "link": reverse_lazy("admin:stockman_stockalert_changelist")},
                ],
            },
            {
                "title": "Regras",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Regras", "icon": "tune", "link": reverse_lazy("admin:shop_ruleconfig_changelist")},
                    {"title": "Promoções", "icon": "sell", "link": reverse_lazy("admin:shop_promotion_changelist")},
                    {"title": "Cupons", "icon": "confirmation_number", "link": reverse_lazy("admin:shop_coupon_changelist")},
                ],
            },
            {
                "title": "Operacao",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Registro Rápido", "icon": "add_circle", "link": reverse_lazy("admin:shop_production")},
                    {"title": "Fechamento", "icon": "point_of_sale", "link": reverse_lazy("admin:shop_closing")},
                    {"title": "Receitas", "icon": "menu_book", "link": reverse_lazy("admin:craftsman_recipe_changelist")},
                    {"title": "Ordens de Producao", "icon": "manufacturing", "link": reverse_lazy("admin:craftsman_workorder_changelist")},
                    {"title": "Alertas", "icon": "warning", "link": reverse_lazy("admin:shop_operatoralert_changelist")},
                    {"title": "KDS", "icon": "kitchen", "link": reverse_lazy("admin:shop_kdsinstance_changelist")},
                    {"title": "Diretivas", "icon": "conversion_path", "link": reverse_lazy("admin:orderman_directive_changelist")},
                    {"title": "Fechamento Diário", "icon": "event_available", "link": reverse_lazy("admin:shop_dayclosing_changelist")},
                ],
            },
            {
                "title": "Clientes",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Clientes", "icon": "people", "link": reverse_lazy("admin:guestman_customer_changelist")},
                    {"title": "Grupos", "icon": "groups", "link": reverse_lazy("admin:guestman_customergroup_changelist")},
                ],
            },
            {
                "title": "Acesso",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Usuarios", "icon": "person", "link": reverse_lazy("admin:auth_user_changelist")},
                    {"title": "Grupos", "icon": "admin_panel_settings", "link": reverse_lazy("admin:auth_group_changelist")},
                ],
            },
        ],
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

SHOPMAN_NOTIFICATION_ADAPTERS = {
    "manychat": "shopman.shop.adapters.notification_manychat",
    "email": "shopman.shop.adapters.notification_email",
    "console": "shopman.shop.adapters.notification_console",
}

SHOPMAN_STOCK_ADAPTER = "shopman.shop.adapters.stock"

SHOPMAN_FISCAL_ADAPTER = None
SHOPMAN_FISCAL_BACKEND = None
SHOPMAN_ACCOUNTING_BACKEND = None

# List of dotted paths to FiscalBackend implementations.
# Example: ["myinstance.adapters.fiscal_focus.FocusNFCeBackend"]
SHOPMAN_FISCAL_BACKENDS: list[str] = []

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
# Persistence backend for SSE events. The ORM backend is sufficient for a
# single-process deployment (daphne running standalone). When scaling out to
# multiple workers, additionally set ``EVENTSTREAM_REDIS = {"host": ..., ...}``
# so ``send_event`` from any worker reaches every active SSE listener.
EVENTSTREAM_STORAGE_CLASS = "django_eventstream.storage.DjangoModelStorage"

ASGI_APPLICATION = "config.asgi.application"

# ── Storefront channel ────────────────────────────────────────────────
# Ref of the Channel that powers the web storefront. Override in instance settings
# if this instance uses a different ref (e.g. "site", "loja").
SHOPMAN_STOREFRONT_CHANNEL_REF = "web"

# Ref of the Channel used for POS/counter orders.
SHOPMAN_POS_CHANNEL_REF = os.environ.get("SHOPMAN_POS_CHANNEL_REF", "balcao")

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

# ── Logging ────────────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
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
