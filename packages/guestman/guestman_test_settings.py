"""
Django settings for Guestman tests.

Minimal settings to run pytest with shopman.guestman app and all contrib modules.
"""

SECRET_KEY = "test-secret-key-for-customers-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "django_filters",
    # Guestman core
    "shopman.guestman",
    # Guestman contribs
    "shopman.guestman.contrib.identifiers",
    "shopman.guestman.contrib.preferences",
    "shopman.guestman.contrib.insights",
    "shopman.guestman.contrib.timeline",
    "shopman.guestman.contrib.consent",
    "shopman.guestman.contrib.loyalty",
    "shopman.guestman.contrib.merge",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "customers_test_urls"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"

# Guestman settings
GUESTMAN = {
    "DEFAULT_REGION": "BR",
    "EVENT_CLEANUP_DAYS": 90,
}

# Manychat webhook secret for tests
MANYCHAT_WEBHOOK_SECRET = ""
