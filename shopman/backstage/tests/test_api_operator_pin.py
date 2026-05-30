"""Tests for the DRF POS operator unlock/lock API (consumed by the Nuxt surface)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from shopman.doorman.models import PinCredential

from shopman.shop.models import Channel, Shop

User = get_user_model()


def _grant(user, codename):
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="backstage", codename=codename)
    )
    return User.objects.get(pk=user.pk)


class POSOperatorApiTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        self.terminal_user = User.objects.create_user("terminal", password="x", is_staff=True)
        self.terminal_user = _grant(self.terminal_user, "operate_pos")
        self.client.force_login(self.terminal_user)
        self.op = User.objects.create_user("ana", password="x", is_staff=True, first_name="Ana")
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")

    def test_unlock_valid_pin(self):
        resp = self.client.post(
            "/api/v1/backstage/pos/operator/unlock/", {"operator_id": self.op.pk, "pin": "1234"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["operator"]["name"], "Ana")

    def test_unlock_wrong_pin(self):
        resp = self.client.post(
            "/api/v1/backstage/pos/operator/unlock/", {"operator_id": self.op.pk, "pin": "0000"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["ok"])

    def test_projection_reflects_active_operator_then_lock(self):
        self.client.post(
            "/api/v1/backstage/pos/operator/unlock/", {"operator_id": self.op.pk, "pin": "1234"}
        )
        pos = self.client.get("/api/v1/backstage/pos/")
        self.assertEqual(pos.json()["operator"]["name"], "Ana")
        self.assertIn("operators", pos.json()["pos"])
        self.assertEqual(pos.json()["pos"]["auto_lock_seconds"], 60)

        lock = self.client.post("/api/v1/backstage/pos/operator/lock/")
        self.assertEqual(lock.status_code, 200)
        pos2 = self.client.get("/api/v1/backstage/pos/")
        self.assertIsNone(pos2.json()["operator"])
