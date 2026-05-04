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
