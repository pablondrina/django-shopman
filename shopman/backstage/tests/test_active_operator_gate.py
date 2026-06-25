"""HasBackstagePermission — Opção C authorization (WP-AUTH-2b).

When SHOPMAN_REQUIRE_ACTIVE_OPERATOR is ON, backstage actions are authorized
against the ACTIVE OPERATOR (PIN/badge), not the device session user. These tests
pin the no-bypass guarantee: the device session's permissions must NOT grant access
when a different operator is active, and an operator's permission must grant access
even if the device session user lacks it.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from rest_framework.test import APIRequestFactory

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.services.operator import ACTIVE_OPERATOR_SESSION_KEY

User = get_user_model()
PERM = "backstage.operate_production"


class _View:
    required_permission = PERM


def _grant(user) -> None:
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="backstage", codename="operate_production")
    )


def _staff(username: str, *, perm: bool = False, active: bool = True, staff: bool = True):
    user = User.objects.create_user(username, password="x", is_staff=staff, is_active=active)
    if perm:
        _grant(user)
        user = User.objects.get(pk=user.pk)  # refresh perm cache
    return user


def _request(session_user, active_operator=None):
    request = APIRequestFactory().get("/")
    request.user = session_user
    request.session = {}
    if active_operator is not None:
        request.session[ACTIVE_OPERATOR_SESSION_KEY] = {"id": active_operator.pk, "username": active_operator.get_username()}
    return request


def _allowed(session_user, active_operator=None) -> bool:
    return HasBackstagePermission().has_permission(_request(session_user, active_operator), _View())


# ── Flag OFF (default): the device session decides — current behaviour ───────


@pytest.mark.django_db
@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=False)
def test_flag_off_session_user_decides():
    assert _allowed(_staff("dev-perm", perm=True)) is True
    assert _allowed(_staff("dev-noperm", perm=False)) is False


# ── Flag ON: the active operator decides ─────────────────────────────────────


@pytest.mark.django_db
@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_locked_without_active_operator():
    # Device is authenticated staff WITH the perm, but nobody unlocked → 403 (locked).
    assert _allowed(_staff("station", perm=True)) is False


@pytest.mark.django_db
@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_active_operator_with_perm_is_allowed_even_if_session_lacks_it():
    # The device/station session has NO perm; the active operator HAS it → allowed.
    station = _staff("station2", perm=False)
    operator = _staff("bia", perm=True)
    assert _allowed(station, active_operator=operator) is True


@pytest.mark.django_db
@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_session_perm_does_not_bypass_when_operator_lacks_it():
    # NO-BYPASS: device session HAS the perm, but the active operator does NOT → denied.
    station = _staff("station3", perm=True)
    operator = _staff("novato", perm=False)
    assert _allowed(station, active_operator=operator) is False


@pytest.mark.django_db
@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_inactive_or_nonstaff_active_operator_is_rejected():
    station = _staff("station4", perm=True)
    inactive = _staff("ex-func", perm=True, active=False)
    assert _allowed(station, active_operator=inactive) is False


@pytest.mark.django_db
@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_request_carries_resolved_active_operator_for_attribution():
    station = _staff("station5", perm=False)
    operator = _staff("ana", perm=True)
    request = _request(station, active_operator=operator)
    assert HasBackstagePermission().has_permission(request, _View()) is True
    assert request.active_operator_user.pk == operator.pk
