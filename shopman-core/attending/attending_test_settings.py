"""
Django settings for Attending tests.

Minimal settings to run pytest with shopman.attending app and all contrib modules.
"""

SECRET_KEY = "test-secret-key-for-attending-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "django_filters",
    # Attending core
    "shopman.attending",
    # Attending contribs
    "shopman.attending.contrib.identifiers",
    "shopman.attending.contrib.preferences",
    "shopman.attending.contrib.insights",
    "shopman.attending.contrib.timeline",
    "shopman.attending.contrib.consent",
    "shopman.attending.contrib.loyalty",
    "shopman.attending.contrib.merge",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "attending_test_urls"

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

# Attending settings
ATTENDING = {
    "DEFAULT_REGION": "BR",
    "EVENT_CLEANUP_DAYS": 90,
}

# Manychat webhook secret for tests
MANYCHAT_WEBHOOK_SECRET = ""
