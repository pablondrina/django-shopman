"""Login de operador NO PRÓPRIO app (operator/login) — sem bounce pro Django admin.

Reusa a auth do Django: usuário+senha → sessão de dispositivo. Só staff entra.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from shopman.shop.models import Shop

User = get_user_model()

LOGIN = "/api/v1/backstage/operator/login/"
SESSION = "/api/v1/backstage/operator/session/"


class OperatorLoginApiTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        self.staff = User.objects.create_user("ana", password="segredo123", is_staff=True)
        self.customer = User.objects.create_user("cliente", password="segredo123", is_staff=False)

    def test_login_valid_staff_opens_session(self):
        resp = self.client.post(LOGIN, {"username": "ana", "password": "segredo123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["device_user"], "ana")
        # A sessão foi aberta: /operator/session/ agora responde autenticado.
        s = self.client.get(SESSION)
        self.assertEqual(s.status_code, 200)
        self.assertEqual(s.json()["device_user"], "ana")

    def test_login_wrong_password_403(self):
        resp = self.client.post(LOGIN, {"username": "ana", "password": "errada"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "operator_login_invalid")

    def test_login_non_staff_rejected(self):
        resp = self.client.post(LOGIN, {"username": "cliente", "password": "segredo123"})
        self.assertEqual(resp.status_code, 403)

    def test_login_unknown_user_403(self):
        resp = self.client.post(LOGIN, {"username": "fantasma", "password": "x"})
        self.assertEqual(resp.status_code, 403)

    def test_login_missing_fields_400(self):
        self.assertEqual(self.client.post(LOGIN, {"username": "ana"}).status_code, 400)
        self.assertEqual(self.client.post(LOGIN, {"password": "x"}).status_code, 400)

    def test_login_inactive_user_rejected(self):
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        resp = self.client.post(LOGIN, {"username": "ana", "password": "segredo123"})
        self.assertEqual(resp.status_code, 403)
