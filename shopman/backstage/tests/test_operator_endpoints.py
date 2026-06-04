"""Tests for the POS operator unlock/lock endpoints."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from shopman.doorman.models import PinCredential

from shopman.backstage.services.operator import ACTIVE_OPERATOR_SESSION_KEY

User = get_user_model()


def _grant(user, codename):
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="backstage", codename=codename)
    )
    return User.objects.get(pk=user.pk)


class OperatorEndpointTests(TestCase):
    def setUp(self):
        from shopman.shop.models import Channel, Shop

        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        # terminal is authenticated as a staff user with operate_pos
        self.terminal_user = User.objects.create_user("terminal", password="x", is_staff=True)
        self.terminal_user = _grant(self.terminal_user, "operate_pos")
        self.client.force_login(self.terminal_user)
        # an eligible operator with a PIN
        self.op = User.objects.create_user("ana", password="x", is_staff=True, first_name="Ana")
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")

    def test_unlock_with_valid_pin(self):
        resp = self.client.post(
            "/gestor/pos/operator/unlock/", {"operator_id": self.op.pk, "pin": "1234"}
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["operator"]["name"], "Ana")
        self.assertEqual(self.client.session[ACTIVE_OPERATOR_SESSION_KEY]["id"], self.op.pk)

    def test_unlock_with_wrong_pin_rejected(self):
        resp = self.client.post(
            "/gestor/pos/operator/unlock/", {"operator_id": self.op.pk, "pin": "0000"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["ok"])
        self.assertNotIn(ACTIVE_OPERATOR_SESSION_KEY, self.client.session)

    def test_lock_clears_active_operator(self):
        self.client.post("/gestor/pos/operator/unlock/", {"operator_id": self.op.pk, "pin": "1234"})
        self.assertIn(ACTIVE_OPERATOR_SESSION_KEY, self.client.session)
        resp = self.client.post("/gestor/pos/operator/lock/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(ACTIVE_OPERATOR_SESSION_KEY, self.client.session)

    def test_unlock_requires_terminal_permission(self):
        plain = User.objects.create_user("plain", password="x", is_staff=True)
        self.client.force_login(plain)
        resp = self.client.post(
            "/gestor/pos/operator/unlock/", {"operator_id": self.op.pk, "pin": "1234"}
        )
        self.assertEqual(resp.status_code, 403)
