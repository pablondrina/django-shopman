"""
Django settings for Payments tests.

Minimal settings to run pytest with shopman.payments app.
"""

SECRET_KEY = "test-secret-key-for-payments-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "shopman.payments",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"
