from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@pytest.mark.django_db
def test_bootstrap_admin_creates_named_superuser(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", "strong-staging-owner-password")

    call_command(
        "bootstrap_admin",
        username="pablo",
        email="pablo@example.com",
        stdout=StringIO(),
    )

    user = get_user_model().objects.get(username="pablo")
    assert user.email == "pablo@example.com"
    assert user.is_active is True
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("strong-staging-owner-password")


@pytest.mark.django_db
def test_bootstrap_admin_is_idempotent(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", "strong-staging-owner-password")

    for email in ["old@example.com", "new@example.com"]:
        call_command(
            "bootstrap_admin",
            username="pablo",
            email=email,
            stdout=StringIO(),
        )

    users = get_user_model().objects.filter(username="pablo")
    assert users.count() == 1
    assert users.get().email == "new@example.com"


@pytest.mark.django_db
def test_bootstrap_admin_can_deactivate_seed_admin(monkeypatch):
    User = get_user_model()
    User.objects.create_superuser("admin", "admin@example.com", "seed-pass")
    monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", "strong-staging-owner-password")

    call_command(
        "bootstrap_admin",
        username="pablo",
        email="pablo@example.com",
        deactivate_seed_admin=True,
        stdout=StringIO(),
    )

    assert User.objects.get(username="admin").is_active is False
    assert User.objects.get(username="pablo").is_active is True


@pytest.mark.django_db
def test_bootstrap_admin_rejects_weak_password_when_not_debug(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", "admin")

    with override_settings(DEBUG=False):
        with pytest.raises(CommandError):
            call_command(
                "bootstrap_admin",
                username="pablo",
                email="pablo@example.com",
                stdout=StringIO(),
            )
