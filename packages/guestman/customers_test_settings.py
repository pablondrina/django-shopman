"""
Django settings for Customers tests.

Minimal settings to run pytest with shopman.customers app and all contrib modules.
"""

SECRET_KEY = "test-secret-key-for-customers-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "django_filters",
    # Customers core
    "shopman.customers",
    # Customers contribs
    "shopman.customers.contrib.identifiers",
    "shopman.customers.contrib.preferences",
    "shopman.customers.contrib.insights",
    "shopman.customers.contrib.timeline",
    "shopman.customers.contrib.consent",
    "shopman.customers.contrib.loyalty",
    "shopman.customers.contrib.merge",
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

# Customers settings
ATTENDING = {
    "DEFAULT_REGION": "BR",
    "EVENT_CLEANUP_DAYS": 90,
}

# Manychat webhook secret for tests
MANYCHAT_WEBHOOK_SECRET = ""
