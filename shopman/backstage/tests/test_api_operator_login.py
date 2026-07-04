"""Login de operador NO PRÓPRIO app (operator/login) — sem bounce pro Django admin.

Reusa a auth do Django: usuário+senha → sessão de dispositivo. Só staff entra.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

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


@override_settings(RATELIMIT_ENABLE=True)
class OperatorLoginRateLimitTests(TestCase):
    """Login de operador é `AllowAny` — sem freio, era brute-force de senha staff.

    Controle primário é por-username (ataque a uma conta específica); o teto por-IP
    é generoso porque numa loja os dispositivos do operador compartilham o IP (NAT).
    """

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        User.objects.create_user("ana", password="segredo123", is_staff=True)
        cache.clear()
        # Fixa a janela do ratelimit para todas as tentativas caírem no mesmo bucket.
        self._win = patch("django_ratelimit.core._get_window", return_value=2_000_000_000)
        self._win.start()

    def tearDown(self):
        self._win.stop()
        cache.clear()

    def test_brute_force_same_account_is_locked_out(self):
        """A 6ª tentativa contra a MESMA conta no mesmo minuto vira 429 (não 403)."""
        for _ in range(5):
            resp = self.client.post(LOGIN, {"username": "ana", "password": "errada"})
            self.assertNotEqual(resp.status_code, 429)
        resp = self.client.post(LOGIN, {"username": "ana", "password": "errada"})
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["error"]["code"], "operator_login_rate_limited")

    def test_lockout_shields_even_correct_password(self):
        """Estourado o limite, nem a senha correta abre sessão (defesa real)."""
        for _ in range(6):
            self.client.post(LOGIN, {"username": "ana", "password": "errada"})
        resp = self.client.post(LOGIN, {"username": "ana", "password": "segredo123"})
        self.assertEqual(resp.status_code, 429)

    def test_lockout_works_over_json_body(self):
        """O caminho de produção é JSON (BFF) — a chave por-username tem de valer nele."""
        import json as _json

        for _ in range(5):
            resp = self.client.post(
                LOGIN,
                _json.dumps({"username": "ana", "password": "errada"}),
                content_type="application/json",
            )
            self.assertNotEqual(resp.status_code, 429)
        resp = self.client.post(
            LOGIN,
            _json.dumps({"username": "ana", "password": "errada"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 429)

    def test_other_account_not_locked_by_first(self):
        """Lockout é por conta-alvo: travar 'ana' não pode travar 'bia'."""
        User.objects.create_user("bia", password="segredo123", is_staff=True)
        for _ in range(6):
            self.client.post(LOGIN, {"username": "ana", "password": "errada"})
        # 'bia' ainda entra (não colapsou no mesmo bucket).
        resp = self.client.post(LOGIN, {"username": "bia", "password": "segredo123"})
        self.assertEqual(resp.status_code, 200)
