"""
Django settings for Gating tests.

Minimal settings to run pytest with shopman.gating + shopman.attending (for CustomerResolver).
"""

SECRET_KEY = "test-secret-key-for-gating-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    # Attending (dependency for CustomerResolver)
    "shopman.attending",
    # Gating
    "shopman.gating",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "gating_test_urls"

USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

# Gating settings
GATING = {
    "MESSAGE_SENDER_CLASS": "shopman.gating.senders.LogSender",
    "BRIDGE_TOKEN_API_KEY": "",
    "AUTO_CREATE_CUSTOMER": True,
    "USE_HTTPS": False,
    "DEFAULT_DOMAIN": "testserver",
}
