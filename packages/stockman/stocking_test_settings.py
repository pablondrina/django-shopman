"""
Django settings for Stocking tests.

Minimal settings to run pytest with shopman.stockman app.
"""

SECRET_KEY = "test-secret-key-for-stocking-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "taggit",
    "simple_history",
    "rest_framework",
    "shopman.offerman",
    "shopman.stockman",
    "shopman.stockman.contrib.alerts",
]

ROOT_URLCONF = "shopman.stockman.tests.urls"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"
