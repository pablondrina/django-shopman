"""Admin two-factor (TOTP) gate — SHOPMAN_ADMIN_REQUIRE_2FA.

Verified locally end-to-end (gate off → in; gate on + device + valid token → in);
on staging the flag stays OFF until enrollment (enabling it would lock out).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from shopman.shop.models import Shop

User = get_user_model()


def _current_token(device: TOTPDevice) -> str:
    value = totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits)
    return str(value).zfill(device.digits)


@pytest.fixture
def admin_user(db):
    Shop.objects.create(name="Loja")
    return User.objects.create_superuser("admin2fa", "a@b.com", "pw")


@pytest.mark.django_db
def test_gate_off_admin_accessible_without_2fa(client, admin_user):
    client.force_login(admin_user)
    # default: SHOPMAN_ADMIN_REQUIRE_2FA off → admin index renders (no redirect to verify)
    resp = client.get(reverse("admin:index"))
    assert resp.status_code == 200


@override_settings(SHOPMAN_ADMIN_REQUIRE_2FA=True)
@pytest.mark.django_db
def test_gate_on_unverified_redirects_to_verify(client, admin_user):
    client.force_login(admin_user)
    resp = client.get(reverse("admin:index"))
    assert resp.status_code == 302
    assert reverse("admin_2fa_verify") in resp["Location"]


@override_settings(SHOPMAN_ADMIN_REQUIRE_2FA=True)
@pytest.mark.django_db
def test_gate_on_login_page_not_gated(client, admin_user):
    # the admin login itself must stay reachable (no loop)
    resp = client.get("/admin/login/")
    assert resp.status_code in {200, 302}
    assert reverse("admin_2fa_verify") not in resp.get("Location", "")


@override_settings(SHOPMAN_ADMIN_REQUIRE_2FA=True)
@pytest.mark.django_db
def test_verify_with_valid_token_then_admin_accessible(client, admin_user):
    device = TOTPDevice.objects.create(user=admin_user, name="admin", confirmed=True)
    client.force_login(admin_user)

    # blocked before verifying
    assert client.get(reverse("admin:index")).status_code == 302

    # submit a valid token → redirected to next, session now verified
    resp = client.post(
        reverse("admin_2fa_verify"),
        {"token": _current_token(device), "next": "/admin/"},
    )
    assert resp.status_code == 302
    assert resp["Location"] == "/admin/"

    # now admin is accessible
    assert client.get(reverse("admin:index")).status_code == 200


@override_settings(SHOPMAN_ADMIN_REQUIRE_2FA=True)
@pytest.mark.django_db
def test_verify_bad_token_shows_error(client, admin_user):
    TOTPDevice.objects.create(user=admin_user, name="admin", confirmed=True)
    client.force_login(admin_user)
    resp = client.post(reverse("admin_2fa_verify"), {"token": "000000", "next": "/admin/"})
    assert resp.status_code == 200
    assert "inválido" in resp.content.decode().lower()


@override_settings(SHOPMAN_ADMIN_REQUIRE_2FA=True)
@pytest.mark.django_db
def test_verify_without_device_shows_enrollment_note(client, admin_user):
    client.force_login(admin_user)
    resp = client.get(reverse("admin_2fa_verify"))
    assert resp.status_code == 200
    assert "setup_admin_totp" in resp.content.decode()


@override_settings(SHOPMAN_ADMIN_REQUIRE_2FA=True)
@pytest.mark.django_db
def test_verify_rejects_open_redirect(client, admin_user):
    device = TOTPDevice.objects.create(user=admin_user, name="admin", confirmed=True)
    client.force_login(admin_user)
    resp = client.post(
        reverse("admin_2fa_verify"),
        {"token": _current_token(device), "next": "https://evil.example.com/"},
    )
    assert resp.status_code == 302
    assert resp["Location"] == reverse("admin:index")  # non-/admin/ next → safe default


@pytest.mark.django_db
def test_setup_admin_totp_command_enrolls_and_is_idempotent(admin_user):
    call_command("setup_admin_totp", "admin2fa")
    assert TOTPDevice.objects.filter(user=admin_user, confirmed=True).count() == 1

    # without --force, refuses to duplicate
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("setup_admin_totp", "admin2fa")

    # --force replaces (still exactly one)
    call_command("setup_admin_totp", "admin2fa", "--force")
    assert TOTPDevice.objects.filter(user=admin_user, confirmed=True).count() == 1
