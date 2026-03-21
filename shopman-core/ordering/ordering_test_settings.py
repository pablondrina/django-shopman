"""
Django settings for Ordering tests.

Minimal settings to run pytest with shopman.ordering app.
"""

SECRET_KEY = "test-secret-key-for-ordering-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "shopman.utils",
    "shopman.ordering",
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
