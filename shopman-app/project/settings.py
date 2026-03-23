"""
Django settings for the Shopman project (Nelson Boulangerie demo).
"""

import os

from django.urls import reverse_lazy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

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
    "import_export",
    "unfold.contrib.import_export",
    # Shopman core apps
    "shopman.utils",
    "shopman.offering",
    "shopman.stocking",
    "shopman.crafting",
    "shopman.ordering",
    "shopman.attending",
    "shopman.gating",
    # Shopman core Unfold contribs
    "shopman.offering.contrib.admin_unfold",
    "shopman.stocking.contrib.admin_unfold",
    "shopman.crafting.contrib.admin_unfold",
    "shopman.attending.contrib.insights",
    "shopman.attending.contrib.admin_unfold",
    "shopman.gating.contrib.admin_unfold",
    # Shopman orchestrator
    "shopman",
    "shopman.customer",
    "shopman.stock",
    "shopman.confirmation",
    "shopman.notifications",
    "shopman.payment",
    "shopman.accounting",
    "shopman.fiscal",
    "shopman.returns",
    "shopman.webhook",
    # Channels
    "channels.web",
    # Nelson Boulangerie (demo app)
    "nelson",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "project.urls"

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
                "channels.web.context_processors.cart_count",
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

UNFOLD = {
    "SITE_TITLE": "Nelson Boulangerie",
    "SITE_HEADER": "Nelson Boulangerie",
    "SITE_SUBHEADER": "Padaria Artesanal Premium",
    "SITE_SYMBOL": "bakery_dining",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
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
                    {"title": "Clientes", "icon": "people", "link": reverse_lazy("admin:attending_customer_changelist")},
                    {"title": "Grupos", "icon": "groups", "link": reverse_lazy("admin:attending_customergroup_changelist")},
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
