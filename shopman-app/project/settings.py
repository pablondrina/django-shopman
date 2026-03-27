"""
Django settings for the Shopman project (Nelson Boulangerie demo).
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if DEBUG:
    CSRF_TRUSTED_ORIGINS += ["https://*.ngrok-free.app", "https://*.ngrok.io"]

INSTALLED_APPS = [
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
    "taggit",
    "rest_framework",
    "drf_spectacular",
    "import_export",
    "unfold.contrib.import_export",
    # Shopman core apps
    "shopman.utils",
    "shopman.offering",
    "shopman.stocking",
    "shopman.crafting",
    "shopman.ordering",
    "shopman.payments",
    "shopman.customers",
    "shopman.auth",
    # Shopman core Unfold contribs
    "shopman.offering.contrib.admin_unfold",
    "shopman.stocking.contrib.admin_unfold",
    "shopman.crafting.contrib.admin_unfold",
    "shopman.stocking.contrib.alerts",
    "shopman.customers.contrib.insights",
    "shopman.customers.contrib.loyalty",
    "shopman.customers.contrib.admin_unfold",
    "shopman.auth.contrib.admin_unfold",
    # Shopman orchestrator
    "shopman",
    # Shop (identidade + regras)
    "shop",
    # Channels
    "channels",
    "channels.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "shopman.auth.middleware.AuthCustomerMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "shopman.auth.backends.PhoneOTPBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH = {
    "PRESERVE_SESSION_KEYS": ["cart_session_key"],
    "DEFAULT_DOMAIN": os.environ.get("AUTH_DEFAULT_DOMAIN", "localhost:8000"),
    "USE_HTTPS": not DEBUG,
}

ROOT_URLCONF = "project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "shop", "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "channels.web.context_processors.cart_count",
                "shop.context_processors.shop",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# ── Unfold Admin ────────────────────────────────────────────────────
# Branding, TABS and SIDEBAR moved to shop/admin.py.
# We can't import from shop.admin at settings load time (AppRegistryNotReady),
# so we use reverse_lazy here directly. The SITE_TITLE callable reads Shop.name.

from django.urls import reverse_lazy  # noqa: E402


def _unfold_site_title(request=None):
    try:
        from shop.models import Shop
        shop = Shop.load()
        return shop.name if shop else "Shopman"
    except Exception:
        return "Shopman"


UNFOLD = {
    "SITE_TITLE": _unfold_site_title,
    "SITE_HEADER": _unfold_site_title,
    "SITE_SYMBOL": "storefront",
    "DASHBOARD_CALLBACK": "shop.dashboard.dashboard_callback",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "STYLES": [
        lambda request: "/static/shop/css/admin-fix.css",
    ],
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
            "models": ["offering.product", "offering.collection", "offering.listing"],
            "items": [
                {"title": "Produtos", "link": reverse_lazy("admin:offering_product_changelist")},
                {"title": "Colecoes", "link": reverse_lazy("admin:offering_collection_changelist")},
                {"title": "Listagens", "link": reverse_lazy("admin:offering_listing_changelist")},
            ],
        },
        {
            "models": [
                "stocking.quant",
                "stocking.move",
                "stocking.hold",
                "stocking.batch",
                "stocking.position",
                "stocking.stockalert",
            ],
            "items": [
                {"title": "Saldo", "link": reverse_lazy("admin:stocking_quant_changelist")},
                {"title": "Movimentos", "link": reverse_lazy("admin:stocking_move_changelist")},
                {"title": "Reservas", "link": reverse_lazy("admin:stocking_hold_changelist")},
                {"title": "Lotes", "link": reverse_lazy("admin:stocking_batch_changelist")},
            ],
        },
        {
            "models": ["crafting.recipe", "crafting.workorder"],
            "items": [
                {"title": "Receitas", "link": reverse_lazy("admin:crafting_recipe_changelist")},
                {"title": "Ordens de Producao", "link": reverse_lazy("admin:crafting_workorder_changelist")},
            ],
        },
        {
            "models": ["ordering.order", "ordering.session", "ordering.directive"],
            "items": [
                {"title": "Pedidos", "link": reverse_lazy("admin:ordering_order_changelist")},
                {"title": "Sessoes", "link": reverse_lazy("admin:ordering_session_changelist")},
                {"title": "Diretivas", "link": reverse_lazy("admin:ordering_directive_changelist")},
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
                    {"title": "Canais", "icon": "network_node", "link": reverse_lazy("admin:ordering_channel_changelist")},
                    {"title": "Sessoes", "icon": "note_alt", "link": reverse_lazy("admin:ordering_session_changelist")},
                    {"title": "Pedidos", "icon": "assignment", "link": reverse_lazy("admin:ordering_order_changelist")},
                    {"title": "Diretivas", "icon": "conversion_path", "link": reverse_lazy("admin:ordering_directive_changelist")},
                ],
            },
            {
                "title": "Catalogo",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Produtos", "icon": "inventory_2", "link": reverse_lazy("admin:offering_product_changelist")},
                    {"title": "Colecoes", "icon": "category", "link": reverse_lazy("admin:offering_collection_changelist")},
                    {"title": "Listagens", "icon": "shoppingmode", "link": reverse_lazy("admin:offering_listing_changelist")},
                ],
            },
            {
                "title": "Estoque",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Saldo", "icon": "point_scan", "link": reverse_lazy("admin:stocking_quant_changelist")},
                    {"title": "Movimentos", "icon": "swap_horiz", "link": reverse_lazy("admin:stocking_move_changelist")},
                    {"title": "Reservas", "icon": "keep", "link": reverse_lazy("admin:stocking_hold_changelist")},
                    {"title": "Lotes", "icon": "science", "link": reverse_lazy("admin:stocking_batch_changelist")},
                    {"title": "Posicoes", "icon": "domain", "link": reverse_lazy("admin:stocking_position_changelist")},
                    {"title": "Alertas", "icon": "notification_important", "link": reverse_lazy("admin:stocking_stockalert_changelist")},
                ],
            },
            {
                "title": "Producao",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Receitas", "icon": "menu_book", "link": reverse_lazy("admin:crafting_recipe_changelist")},
                    {"title": "Ordens de Producao", "icon": "manufacturing", "link": reverse_lazy("admin:crafting_workorder_changelist")},
                ],
            },
            {
                "title": "Clientes",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Clientes", "icon": "people", "link": reverse_lazy("admin:customers_customer_changelist")},
                    {"title": "Grupos", "icon": "groups", "link": reverse_lazy("admin:customers_customergroup_changelist")},
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

# ── Crafting (micro-MRP integration) ──────────────────────────────

CRAFTING = {
    "INVENTORY_BACKEND": "shopman.crafting.adapters.stocking.StockingBackend",
    "DEMAND_BACKEND": "shopman.crafting.contrib.demand.backend.OrderingDemandBackend",
    "CATALOG_BACKEND": "shopman.offering.adapters.catalog_backend.OfferingCatalogBackend",
}

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
        "channels": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# ── Security ──────────────────────────────────────────────────────────

if not DEBUG:
    assert SECRET_KEY != "dev-secret-key-not-for-production", (
        "SECRET_KEY must be set in production (DJANGO_SECRET_KEY env var)"
    )
    assert ALLOWED_HOSTS != ["*"], (
        "ALLOWED_HOSTS must be explicit in production (DJANGO_ALLOWED_HOSTS env var)"
    )

    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
