"""Minimal Django settings for testing shopman.refs."""

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "shopman.refs",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SECRET_KEY = "test-secret-key-not-for-production"
USE_TZ = True
