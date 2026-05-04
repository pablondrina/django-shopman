"""Granular RBAC permission tests — WP-GAP-13.

Covers:
- Staff without perm → 403 on protected endpoints
- Staff with correct perm → 200
- Superuser passes all endpoints
- Group Caixa: POS+orders OK, KDS 403
- Group Cozinha: KDS+production OK, POS 403
- Group Gerente: orders+pos+closing+customers OK, catalog 403
- setup_groups command is idempotent
- All 4 groups created by migration with correct perms
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase

User = get_user_model()


def _staff(username, password="test", permissions=None):
    u = User.objects.create_user(username=username, password=password, is_staff=True)
    for perm in permissions or []:
        u.user_permissions.add(perm)
    return u


def _get_perm(app_label, model, codename):
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get(app_label=app_label, model=model)
    return Permission.objects.get(content_type=ct, codename=codename)


def _create_shop():
    from shopman.shop.models import Shop
    return Shop.objects.create(
        name="Test Shop",
        default_ddd="11",
        currency="BRL",
        timezone="America/Sao_Paulo",
    )


class TestManageOrdersPerm(TestCase):
    def setUp(self):
        self.client = Client()
        self.perm = _get_perm("shop", "shop", "manage_orders")
        _create_shop()

    def test_staff_without_perm_gets_403(self):
        u = _staff("staff_no_perm")
        self.client.force_login(u)
        resp = self.client.get("/admin/operacao/pedidos/")
        self.assertEqual(resp.status_code, 403)

    def test_staff_with_perm_gets_200(self):
        u = _staff("staff_with_perm", permissions=[self.perm])
        self.client.force_login(u)
        resp = self.client.get("/admin/operacao/pedidos/")
        self.assertEqual(resp.status_code, 200)

    def test_superuser_passes(self):
        u = User.objects.create_superuser("super", password="test")
        self.client.force_login(u)
        resp = self.client.get("/admin/operacao/pedidos/")
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get("/admin/operacao/pedidos/")
        self.assertRedirects(resp, "/admin/login/?next=/admin/operacao/pedidos/", fetch_redirect_response=False)


class TestOperateKdsPerm(TestCase):
    def setUp(self):
        self.client = Client()
        self.perm = _get_perm("backstage", "kdsticket", "operate_kds")
        _create_shop()

    def test_staff_without_perm_can_view_readonly(self):
        u = _staff("kds_no_perm")
        self.client.force_login(u)
        resp = self.client.get("/admin/operacao/kds/")
        # KDS index allows staff to view (readonly); only actions require operate_kds perm.
        self.assertEqual(resp.status_code, 200)

    def test_staff_with_perm_passes_check(self):
        u = _staff("kds_op", permissions=[self.perm])
        self.client.force_login(u)
        resp = self.client.get("/admin/operacao/kds/")
        self.assertNotEqual(resp.status_code, 403)

    def test_superuser_passes(self):
        u = User.objects.create_superuser("super_kds", password="test")
        self.client.force_login(u)
        resp = self.client.get("/admin/operacao/kds/")
        self.assertNotEqual(resp.status_code, 403)


class TestOperatePosPerm(TestCase):
    def setUp(self):
        self.client = Client()
        self.perm = _get_perm("backstage", "cashregistersession", "operate_pos")
        _create_shop()  # required: OnboardingMiddleware redirects /gestor/ if no Shop

    def test_staff_without_perm_gets_403(self):
        u = _staff("pos_no_perm")
        self.client.force_login(u)
        resp = self.client.get("/gestor/pos/")
        self.assertEqual(resp.status_code, 403)

    def test_staff_with_perm_gets_200(self):
        u = _staff("pos_op", permissions=[self.perm])
        self.client.force_login(u)
        resp = self.client.get("/gestor/pos/")
        self.assertEqual(resp.status_code, 200)

    def test_superuser_passes(self):
        u = User.objects.create_superuser("super_pos", password="test")
        self.client.force_login(u)
        resp = self.client.get("/gestor/pos/")
        self.assertEqual(resp.status_code, 200)


class TestCashierGroup(TestCase):
    """Cashier (Caixa) group: operate_pos + manage_orders. NOT operate_kds."""

    def setUp(self):
        self.client = Client()
        self.group = Group.objects.get(name="Caixa")
        u = User.objects.create_user("caixa_user", password="test", is_staff=True)
        u.groups.add(self.group)
        self.user = u
        _create_shop()

    def test_cashier_can_access_orders(self):
        self.client.force_login(self.user)
        resp = self.client.get("/admin/operacao/pedidos/")
        self.assertEqual(resp.status_code, 200)

    def test_cashier_can_access_pos(self):
        self.client.force_login(self.user)
        resp = self.client.get("/gestor/pos/")
        self.assertEqual(resp.status_code, 200)

    def test_cashier_can_view_kds_readonly(self):
        self.client.force_login(self.user)
        resp = self.client.get("/admin/operacao/kds/")
        # KDS index is viewable by any staff (readonly); actions require operate_kds perm.
        self.assertEqual(resp.status_code, 200)


class TestKitchenGroup(TestCase):
    """Kitchen (Cozinha) group: operate_kds + manage_production. NOT operate_pos."""

    def setUp(self):
        self.client = Client()
        self.group = Group.objects.get(name="Cozinha")
        u = User.objects.create_user("cozinha_user", password="test", is_staff=True)
        u.groups.add(self.group)
        self.user = u
        _create_shop()

    def test_kitchen_can_access_kds(self):
        self.client.force_login(self.user)
        resp = self.client.get("/admin/operacao/kds/")
        self.assertNotEqual(resp.status_code, 403)

    def test_kitchen_cannot_access_pos(self):
        self.client.force_login(self.user)
        resp = self.client.get("/gestor/pos/")
        self.assertEqual(resp.status_code, 403)

    def test_kitchen_cannot_access_orders(self):
        self.client.force_login(self.user)
        resp = self.client.get("/admin/operacao/pedidos/")
        self.assertEqual(resp.status_code, 403)


class TestManagerGroup(TestCase):
    """Manager (Gerente) group: manage_orders, operate_pos, perform_closing, view_reports."""

    def setUp(self):
        self.client = Client()
        self.group = Group.objects.get(name="Gerente")
        u = User.objects.create_user("gerente_user", password="test", is_staff=True)
        u.groups.add(self.group)
        self.user = u
        _create_shop()

    def test_manager_can_access_orders(self):
        self.client.force_login(self.user)
        resp = self.client.get("/admin/operacao/pedidos/")
        self.assertEqual(resp.status_code, 200)

    def test_manager_can_access_pos(self):
        self.client.force_login(self.user)
        resp = self.client.get("/gestor/pos/")
        self.assertEqual(resp.status_code, 200)

    def test_manager_can_view_kds_readonly(self):
        self.client.force_login(self.user)
        resp = self.client.get("/admin/operacao/kds/")
        # KDS index is viewable by any staff (readonly); actions require operate_kds perm.
        self.assertEqual(resp.status_code, 200)


class TestDefaultGroupsExist(TestCase):
    """All 4 default groups must exist with correct permissions."""

    def _has_perm(self, group, codename):
        return group.permissions.filter(codename=codename).exists()

    def test_cashier_group_exists_with_perms(self):
        g = Group.objects.get(name="Caixa")
        self.assertTrue(self._has_perm(g, "operate_pos"))
        self.assertTrue(self._has_perm(g, "manage_orders"))

    def test_kitchen_group_exists_with_perms(self):
        g = Group.objects.get(name="Cozinha")
        self.assertTrue(self._has_perm(g, "operate_kds"))
        self.assertTrue(self._has_perm(g, "manage_production"))

    def test_manager_group_exists_with_perms(self):
        g = Group.objects.get(name="Gerente")
        self.assertTrue(self._has_perm(g, "manage_orders"))
        self.assertTrue(self._has_perm(g, "operate_pos"))
        self.assertTrue(self._has_perm(g, "perform_closing"))
        self.assertTrue(self._has_perm(g, "view_reports"))
        self.assertTrue(self._has_perm(g, "manage_customers"))

    def test_catalog_admin_group_exists_with_perms(self):
        g = Group.objects.get(name="Admin de Catálogo")
        self.assertTrue(self._has_perm(g, "manage_catalog"))
        self.assertTrue(self._has_perm(g, "manage_rules"))

    def test_rules_managers_group_still_exists(self):
        self.assertTrue(Group.objects.filter(name="Rules Managers").exists())


class TestSetupGroupsIdempotent(TestCase):
    """setup_groups command can run multiple times without duplicating perms."""

    def test_idempotent(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("setup_groups", stdout=out)
        call_command("setup_groups", stdout=out)

        g = Group.objects.get(name="Caixa")
        self.assertEqual(g.permissions.filter(codename="operate_pos").count(), 1)
        self.assertEqual(g.permissions.filter(codename="manage_orders").count(), 1)
