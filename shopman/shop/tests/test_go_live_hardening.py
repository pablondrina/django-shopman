"""Guardrails de hardening de go-live (Onda 0 da auditoria de excelência).

- Senhas de staff/admin passam por validadores (antes: ausentes).
- `seed --flush` recusa apagar dados em produção sem --force.
"""

from django.conf import settings
from django.core.management import CommandError, call_command
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.test import override_settings
import pytest


class TestPasswordValidators:
    def test_validators_are_configured(self):
        names = {v["NAME"].rsplit(".", 1)[-1] for v in settings.AUTH_PASSWORD_VALIDATORS}
        assert {
            "UserAttributeSimilarityValidator",
            "MinimumLengthValidator",
            "CommonPasswordValidator",
            "NumericPasswordValidator",
        } <= names

    def test_common_and_short_passwords_rejected(self):
        for weak in ("admin", "password", "12345678", "senha"):
            with pytest.raises(ValidationError):
                validate_password(weak)

    def test_strong_password_accepted(self):
        # Não levanta.
        validate_password("Trça-9fk!vLmz2")


class _PastGuard(Exception):
    """Sentinel: chegamos ao _flush (ou seja, passamos do guard) sem rodar o seed."""


def _stub_flush(self):
    raise _PastGuard()


class TestSeedFlushGuard:
    """Testa o guard em isolamento: `_flush` é substituído por um sentinel, então
    o seed pesado nunca roda — só observamos se o guard barrou ou deixou passar."""

    @override_settings(SHOPMAN_ENVIRONMENT="production")
    def test_flush_refused_in_production_without_force(self, monkeypatch):
        monkeypatch.setattr(
            "config.management.commands.seed.Command._flush", _stub_flush, raising=True
        )
        with pytest.raises(CommandError, match="produção"):
            call_command("seed", "--flush")

    @override_settings(SHOPMAN_ENVIRONMENT="production")
    def test_force_bypasses_guard_in_production(self, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "temp-strong-pass-9931")
        monkeypatch.setattr(
            "config.management.commands.seed.Command._flush", _stub_flush, raising=True
        )
        # Com --force o guard não barra: chegamos ao _flush (sentinel), não ao CommandError.
        with pytest.raises(_PastGuard):
            call_command("seed", "--flush", "--force")

    @override_settings(SHOPMAN_ENVIRONMENT="staging")
    def test_flush_allowed_outside_production(self, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "temp-strong-pass-9931")
        monkeypatch.setattr(
            "config.management.commands.seed.Command._flush", _stub_flush, raising=True
        )
        with pytest.raises(_PastGuard):
            call_command("seed", "--flush")
