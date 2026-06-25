"""Generic operator session API (operator/session|eligible|unlock|lock) + the
end-to-end Opção C flow: unlock by PIN/badge → gated action passes → lock → 403.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse
from shopman.doorman.models import PinCredential

from shopman.backstage.models import DayClosing

User = get_user_model()


def _grant(user, codename, app="backstage"):
    user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def device(db):
    # The shared station session: staff, but NO operator perms of its own.
    return User.objects.create_user("estacao", password="x", is_staff=True)


@pytest.fixture
def baker(db):
    user = User.objects.create_user("bia", password="x", is_staff=True, first_name="Bia")
    PinCredential.set_for(user, "4321")
    return _grant(user, "operate_production")


@pytest.fixture
def operate_production_perm(db):
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_production",
    )


# ── Session / eligible ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_session_reports_locked_then_operator(client, device, baker):
    client.force_login(device)
    body = client.get(reverse("api-backstage-operator-session")).json()
    assert body["locked"] is True and body["operator"] is None
    client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "4321", "perm": "backstage.operate_production"},
        content_type="application/json",
    )
    body = client.get(reverse("api-backstage-operator-session")).json()
    assert body["locked"] is False
    assert body["operator"]["username"] == "bia"


@pytest.mark.django_db
def test_eligible_filters_by_perm_and_validates(client, device, baker):
    client.force_login(device)
    ok = client.get(reverse("api-backstage-operator-eligible"), {"perm": "backstage.operate_production"})
    assert ok.status_code == 200
    assert any(o["username"] == "bia" for o in ok.json()["operators"])
    # an operator without operate_pos must not appear in the POS picker
    pos = client.get(reverse("api-backstage-operator-eligible"), {"perm": "backstage.operate_pos"})
    assert all(o["username"] != "bia" for o in pos.json()["operators"])
    # unknown perm rejected
    assert client.get(reverse("api-backstage-operator-eligible"), {"perm": "evil"}).status_code == 400


# ── Unlock by PIN / badge ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_unlock_wrong_pin_and_missing_perm(client, device, baker):
    client.force_login(device)
    bad = client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "0000"},
        content_type="application/json",
    )
    assert bad.status_code == 403
    # right pin but demanding a perm the operator lacks → rejected
    nope = client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "4321", "perm": "backstage.operate_pos"},
        content_type="application/json",
    )
    assert nope.status_code == 403


@pytest.mark.django_db
def test_unlock_by_badge(client, device, baker):
    token = PinCredential.issue_badge(baker)
    client.force_login(device)
    ok = client.post(
        reverse("api-backstage-operator-unlock"),
        {"badge": token, "perm": "backstage.operate_production"},
        content_type="application/json",
    )
    assert ok.status_code == 200
    assert ok.json()["operator"]["username"] == "bia"


# ── End-to-end Opção C (flag ON): unlock → action 200 → lock → 403 ───────────


@pytest.mark.django_db
@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_flag_on_unlock_enables_action_lock_blocks_it(client, device, baker, operate_production_perm):
    client.force_login(device)
    board = reverse("api-backstage-production")

    # device alone (no operator) → locked
    assert client.get(board).status_code == 403

    # unlock the baker (has operate_production) → action passes
    client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "4321", "perm": "backstage.operate_production"},
        content_type="application/json",
    )
    assert client.get(board).status_code == 200

    # lock → blocked again
    client.post(reverse("api-backstage-operator-lock"))
    assert client.get(board).status_code == 403
