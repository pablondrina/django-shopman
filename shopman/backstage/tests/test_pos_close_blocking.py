"""Endpoint de fechar o turno bloqueante do terminal (destrava o beco do PDV).

Gerente (perform_closing) ou o dono do turno fecham; operador comum → 403.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from shopman.backstage.models import CashShift
from shopman.backstage.services import pos as pos_service
from shopman.shop.models import Shop

User = get_user_model()
URL = "/api/v1/backstage/pos/cash/close-blocking/"


def _grant(user, model, codename):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(model)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return User.objects.get(pk=user.pk)  # refresca cache de permissão


@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=False)
class POSCloseBlockingApiTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test", brand_name="Test")
        self.owner = _grant(
            User.objects.create_user("dono", password="x", is_staff=True), CashShift, "operate_pos"
        )
        self.shift = pos_service.open_cash_shift(operator=self.owner, opening_amount_raw="50,00")

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_owner_closes_blocking_shift(self):
        resp = self._client(self.owner).post(
            URL, {"shift_id": self.shift.pk, "closing_amount": "50,00"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, CashShift.Status.CLOSED)

    def test_manager_closes_others_shift(self):
        from shopman.backstage.models import DayClosing

        manager = _grant(
            _grant(User.objects.create_user("ger", password="x", is_staff=True), CashShift, "operate_pos"),
            DayClosing, "perform_closing",
        )
        resp = self._client(manager).post(
            URL, {"shift_id": self.shift.pk, "closing_amount": "50,00"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)

    def test_regular_operator_forbidden(self):
        stranger = _grant(
            User.objects.create_user("comum", password="x", is_staff=True), CashShift, "operate_pos"
        )
        resp = self._client(stranger).post(
            URL, {"shift_id": self.shift.pk, "closing_amount": "50,00"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, CashShift.Status.OPEN)

    def test_missing_shift_id_400(self):
        resp = self._client(self.owner).post(URL, {"closing_amount": "0"}, format="json")
        self.assertEqual(resp.status_code, 400)
