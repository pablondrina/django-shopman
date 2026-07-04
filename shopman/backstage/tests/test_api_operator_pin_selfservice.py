"""PIN self-service — operator changes their own PIN; manager resets (temp + forced).

Endpoints under test:
  POST /api/v1/backstage/operator/pin/change/  — self-service, proves current PIN
  POST /api/v1/backstage/operator/pin/reset/   — manager, temp PIN + must_change

The device session is a staff user (station trust); the operator identity is
established by PIN. Proving the current PIN is the authorization to rotate it.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from shopman.doorman.models import PinCredential

from shopman.shop.models import Channel, Shop

User = get_user_model()

CHANGE = "/api/v1/backstage/operator/pin/change/"
RESET = "/api/v1/backstage/operator/pin/reset/"
UNLOCK = "/api/v1/backstage/operator/unlock/"
SESSION = "/api/v1/backstage/operator/session/"
POS_PERM = "backstage.operate_pos"


def _grant(user, codename):
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="backstage", codename=codename)
    )
    return User.objects.get(pk=user.pk)


class PinChangeTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        self.op = User.objects.create_user("ana", password="x", is_staff=True, first_name="Ana")
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")
        self.client.force_login(self.op)

    def test_change_with_correct_current_pin(self):
        resp = self.client.post(
            CHANGE, {"current_pin": "1234", "new_pin": "5678"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        cred = PinCredential.objects.get(user=self.op)
        self.assertTrue(cred.verify("5678"))
        self.assertFalse(cred.verify("1234"))

    def test_change_wrong_current_pin_rejected(self):
        resp = self.client.post(
            CHANGE, {"current_pin": "0000", "new_pin": "5678"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "invalid_current")
        self.assertTrue(PinCredential.objects.get(user=self.op).verify("1234"))

    def test_change_new_pin_violates_policy(self):
        resp = self.client.post(
            CHANGE, {"current_pin": "1234", "new_pin": "12"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "pin_policy")
        self.assertTrue(PinCredential.objects.get(user=self.op).verify("1234"))

    def test_change_missing_fields(self):
        resp = self.client.post(CHANGE, {"current_pin": "1234"}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_change_locked_credential(self):
        cred = PinCredential.objects.get(user=self.op)
        for _ in range(cred.max_attempts):
            cred.verify("0000")
        self.assertTrue(PinCredential.objects.get(user=self.op).is_locked)
        resp = self.client.post(
            CHANGE, {"current_pin": "1234", "new_pin": "5678"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 423)
        self.assertEqual(resp.json()["error"]["code"], "locked")

    def test_change_clears_must_change_flag(self):
        cred = PinCredential.objects.get(user=self.op)
        cred.must_change = True
        cred.save(update_fields=["must_change"])
        resp = self.client.post(
            CHANGE, {"current_pin": "1234", "new_pin": "5678"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PinCredential.objects.get(user=self.op).must_change)


# Reset is gated by the ``manage_operators`` PERMISSION — isolate that here from the
# Opção C station gate (SHOPMAN_REQUIRE_ACTIVE_OPERATOR), which is exercised elsewhere.
@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=False)
class PinResetTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        self.manager = User.objects.create_user("gerente", password="x", is_staff=True)
        self.manager = _grant(self.manager, "manage_operators")
        self.op = User.objects.create_user("ana", password="x", is_staff=True, first_name="Ana")
        PinCredential.set_for(self.op, "1234")

    def test_manager_reset_generates_temp_and_forces_change(self):
        self.client.force_login(self.manager)
        resp = self.client.post(RESET, {"username": "ana"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["must_change"])
        temp = body["temp_pin"]
        cred = PinCredential.objects.get(user=self.op)
        self.assertTrue(cred.must_change)
        self.assertTrue(cred.verify(temp))
        self.assertFalse(cred.verify("1234"))

    def test_manager_reset_accepts_explicit_temp(self):
        self.client.force_login(self.manager)
        resp = self.client.post(
            RESET, {"user_id": self.op.pk, "temp_pin": "4321"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["temp_pin"], "4321")
        self.assertTrue(PinCredential.objects.get(user=self.op).verify("4321"))

    def test_reset_without_permission_forbidden(self):
        plain = User.objects.create_user("bob", password="x", is_staff=True)
        self.client.force_login(plain)
        resp = self.client.post(RESET, {"username": "ana"}, content_type="application/json")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(PinCredential.objects.get(user=self.op).verify("1234"))

    def test_reset_unknown_operator_404(self):
        self.client.force_login(self.manager)
        resp = self.client.post(RESET, {"username": "ghost"}, content_type="application/json")
        self.assertEqual(resp.status_code, 404)

    def test_reset_temp_pin_violating_policy_rejected(self):
        self.client.force_login(self.manager)
        resp = self.client.post(
            RESET, {"username": "ana", "temp_pin": "1"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "pin_policy")

    def test_reset_then_operator_forced_change_end_to_end(self):
        # Manager resets → temp + must_change.
        self.client.force_login(self.manager)
        temp = self.client.post(
            RESET, {"username": "ana"}, content_type="application/json"
        ).json()["temp_pin"]
        # Operator logs in on their device and rotates using the temp as current.
        self.client.logout()
        self.op = _grant(self.op, "operate_pos")
        self.client.force_login(self.op)
        resp = self.client.post(
            CHANGE, {"current_pin": temp, "new_pin": "9090"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        cred = PinCredential.objects.get(user=self.op)
        self.assertFalse(cred.must_change)
        self.assertTrue(cred.verify("9090"))


class PinSessionFlagTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        self.terminal = User.objects.create_user("terminal", password="x", is_staff=True)
        self.terminal = _grant(self.terminal, "operate_pos")
        self.client.force_login(self.terminal)
        self.op = User.objects.create_user("ana", password="x", is_staff=True, first_name="Ana")
        PinCredential.set_for(self.op, "1234", must_change=True)
        self.op = _grant(self.op, "operate_pos")

    def test_session_exposes_pin_must_change_for_active_operator(self):
        self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM})
        resp = self.client.get(SESSION)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["pin_must_change"])

    def test_session_pin_must_change_false_when_locked(self):
        resp = self.client.get(SESSION)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["operator"])
        self.assertFalse(resp.json()["pin_must_change"])
