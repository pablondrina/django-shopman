"""
Django settings for Orderman tests.

Minimal settings to run pytest with shopman.orderman app.
"""

SECRET_KEY = "test-secret-key-for-orderman-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "shopman.utils",
    "shopman.refs",
    "shopman.orderman",
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

ROOT_URLCONF = "orderman_test_urls"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/minute",
        "user": "1000/minute",
        "orderman_modify": "1000/minute",
        "orderman_commit": "1000/minute",
    },
}
