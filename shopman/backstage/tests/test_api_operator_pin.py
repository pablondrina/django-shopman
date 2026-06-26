"""POS operator unlock/lock over the GENERIC operator API
(operator/unlock|lock with perm=operate_pos) — the POS surface migrated to it
(OPERATOR-AUTH-PLAN WP-AUTH-2c). The POS projection still reflects the active
operator set through the shared session.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from shopman.doorman.models import PinCredential

from shopman.shop.models import Channel, Shop

User = get_user_model()

UNLOCK = "/api/v1/backstage/operator/unlock/"
LOCK = "/api/v1/backstage/operator/lock/"
POS_PERM = "backstage.operate_pos"


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
        resp = self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["operator"]["name"], "Ana")

    def test_unlock_wrong_pin(self):
        resp = self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "0000", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 403)

    def test_unlock_rejects_operator_without_pos_perm(self):
        baker = User.objects.create_user("bia", password="x", is_staff=True)
        PinCredential.set_for(baker, "5555")
        baker = _grant(baker, "operate_production")  # not operate_pos
        resp = self.client.post(UNLOCK, {"operator_id": baker.pk, "pin": "5555", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 403)

    def test_projection_reflects_active_operator_then_lock(self):
        self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM})
        pos = self.client.get("/api/v1/backstage/pos/")
        self.assertEqual(pos.json()["operator"]["name"], "Ana")
        self.assertIn("operators", pos.json()["pos"])
        self.assertEqual(pos.json()["pos"]["auto_lock_seconds"], 60)

        lock = self.client.post(LOCK)
        self.assertEqual(lock.status_code, 200)
        pos2 = self.client.get("/api/v1/backstage/pos/")
        self.assertIsNone(pos2.json()["operator"])
