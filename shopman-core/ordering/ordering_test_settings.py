"""
Django settings for Ordering tests.

Minimal settings to run pytest with shopman.ordering app.
"""

SECRET_KEY = "test-secret-key-for-ordering-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "shopman.utils",
    "shopman.ordering",
    "shopman.ordering.contrib.refs",
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

ROOT_URLCONF = "ordering_test_urls"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/minute",
        "user": "1000/minute",
        "ordering_modify": "1000/minute",
        "ordering_commit": "1000/minute",
    },
}
