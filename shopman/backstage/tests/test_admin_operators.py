"""Admin de operadores (PinCredential) — reset/desbloqueio pelo gerente.

Gestão de operador é canônica no Admin/Unfold; o reset gera um PIN temporário
mostrado uma vez e força a troca (must_change). Gateado por manage_operators.
"""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from shopman.doorman.models import PinCredential

from shopman.backstage.admin.operators import PinCredentialAdmin

User = get_user_model()


def _grant(user, codename):
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="backstage", codename=codename)
    )
    return User.objects.get(pk=user.pk)


class PinCredentialAdminTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.admin = PinCredentialAdmin(PinCredential, self.site)
        self.rf = RequestFactory()
        self.manager = User.objects.create_user("gerente", password="x", is_staff=True)
        self.manager = _grant(self.manager, "manage_operators")
        self.op = User.objects.create_user("ana", password="x", is_staff=True, first_name="Ana")
        self.cred = PinCredential.set_for(self.op, "1234")

    def _request(self, user):
        req = self.rf.post("/admin/doorman/pincredential/")
        req.user = user
        # messages framework needs a storage backend on the request.
        from django.contrib.messages.storage.fallback import FallbackStorage

        req.session = self.client.session
        req._messages = FallbackStorage(req)
        return req

    def test_reset_pin_generates_temp_and_sets_must_change(self):
        req = self._request(self.manager)
        self.admin.reset_pin(req, PinCredential.objects.filter(pk=self.cred.pk))
        cred = PinCredential.objects.get(pk=self.cred.pk)
        self.assertTrue(cred.must_change)
        self.assertFalse(cred.verify("1234"))  # old PIN no longer valid

    def test_unlock_pin_clears_lockout(self):
        for _ in range(self.cred.max_attempts):
            self.cred.verify("0000")
        self.assertTrue(PinCredential.objects.get(pk=self.cred.pk).is_locked)
        req = self._request(self.manager)
        self.admin.unlock_pin(req, PinCredential.objects.filter(pk=self.cred.pk))
        self.assertFalse(PinCredential.objects.get(pk=self.cred.pk).is_locked)

    def test_gating_requires_manage_operators(self):
        plain = User.objects.create_user("bob", password="x", is_staff=True)
        self.assertFalse(self.admin.has_view_permission(self._request(plain)))
        self.assertFalse(self.admin.has_module_permission(self._request(plain)))
        self.assertTrue(self.admin.has_view_permission(self._request(self.manager)))

    def test_no_add_permission(self):
        self.assertFalse(self.admin.has_add_permission(self._request(self.manager)))
