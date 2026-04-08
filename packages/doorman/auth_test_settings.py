"""
Django settings for Auth tests.

Minimal settings to run pytest with shopman.doorman + shopman.guestman (for CustomerResolver).
"""

SECRET_KEY = "test-secret-key-for-auth-tests"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    # Customers (dependency for CustomerResolver)
    "shopman.guestman",
    # Auth
    "shopman.doorman",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "auth_test_urls"

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

# Auth settings
AUTH = {
    "MESSAGE_SENDER_CLASS": "shopman.doorman.senders.LogSender",
    "ACCESS_LINK_API_KEY": "",
    "AUTO_CREATE_CUSTOMER": True,
    "USE_HTTPS": False,
    "DEFAULT_DOMAIN": "testserver",
}
