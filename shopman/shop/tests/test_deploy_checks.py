from django.test import override_settings

from shopman.shop import checks


@override_settings(
    DEBUG=True,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
)
def test_database_backend_warns_for_sqlite_in_debug():
    messages = checks.check_database_backend(None)

    assert [message.id for message in messages] == ["SHOPMAN_W001"]


@override_settings(
    DEBUG=False,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
)
def test_database_backend_blocks_sqlite_outside_debug():
    messages = checks.check_database_backend(None)

    assert [message.id for message in messages] == ["SHOPMAN_E007"]


@override_settings(
    DEBUG=False,
    DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "shopman"}},
)
def test_database_backend_accepts_postgres_outside_debug():
    assert checks.check_database_backend(None) == []


@override_settings(
    DEBUG=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
def test_shared_cache_backend_requires_redis_outside_debug():
    errors = checks.check_shared_cache_backend(None)

    assert [error.id for error in errors] == ["SHOPMAN_E006"]


@override_settings(
    DEBUG=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}},
)
def test_shared_cache_backend_accepts_redis_outside_debug():
    assert checks.check_shared_cache_backend(None) == []


@override_settings(
    DEBUG=False,
    CACHES={"default": {"BACKEND": "django_redis.cache.RedisCache"}},
)
def test_shared_cache_backend_rejects_legacy_redis_package_backend():
    errors = checks.check_shared_cache_backend(None)

    assert [error.id for error in errors] == ["SHOPMAN_E006"]


@override_settings(DEBUG=False, DOORMAN={"ACCESS_LINK_API_KEY": ""})
def test_access_link_api_key_required_outside_debug():
    errors = checks.check_doorman_access_link_api_key(None)

    assert [error.id for error in errors] == ["SHOPMAN_E008"]


@override_settings(DEBUG=False, DOORMAN={"ACCESS_LINK_API_KEY": "test-secret"})
def test_access_link_api_key_accepts_configured_secret_outside_debug():
    assert checks.check_doorman_access_link_api_key(None) == []


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
    },
    SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=False,
)
def test_payment_mock_requires_explicit_staging_allowance_outside_debug():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_E003", "SHOPMAN_E003"]


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
    },
    SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True,
)
def test_payment_mock_is_warning_when_explicitly_allowed_for_staging():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_W006", "SHOPMAN_W006"]


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
    },
    SHOPMAN_EFI={},
    SHOPMAN_STRIPE={
        "secret_key": "sk_test_123",
        "webhook_secret": "whsec_test_123",
    },
)
def test_payment_efi_adapter_requires_credentials_outside_debug():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_E009"]
    assert "EFI_CLIENT_ID" in messages[0].hint
    assert "EFI_CERTIFICATE_PATH" in messages[0].hint


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
    },
    SHOPMAN_EFI={
        "client_id": "client",
        "client_secret": "secret",
        "certificate_path": "/tmp/shopman-missing-efi-cert.pem",
        "pix_key": "pix-key",
    },
    SHOPMAN_STRIPE={
        "secret_key": "sk_test_123",
        "webhook_secret": "whsec_test_123",
    },
)
def test_payment_efi_adapter_requires_certificate_file_outside_debug():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_E009"]
    assert "arquivo existente" in messages[0].hint


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
    },
    SHOPMAN_EFI={
        "client_id": "client",
        "client_secret": "secret",
        "certificate_path": __file__,
        "pix_key": "pix-key",
    },
    SHOPMAN_STRIPE={},
)
def test_payment_stripe_adapter_requires_credentials_outside_debug():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_E009"]
    assert "STRIPE_SECRET_KEY" in messages[0].hint
    assert "STRIPE_WEBHOOK_SECRET" in messages[0].hint


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
    },
    SHOPMAN_EFI={
        "client_id": "client",
        "client_secret": "secret",
        "certificate_path": __file__,
        "pix_key": "pix-key",
    },
    SHOPMAN_STRIPE={
        "secret_key": "sk_test_123",
        "webhook_secret": "whsec_test_123",
    },
)
def test_real_payment_adapters_accept_complete_gateway_settings():
    assert checks.check_payment_adapters(None) == []
