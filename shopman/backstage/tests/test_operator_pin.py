"""Tests for backstage operator PIN identification."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from shopman.backstage.services.operator import (
    eligible_operators,
    verify_manager_pin,
    verify_operator_pin,
)
from shopman.doorman.models import PinCredential

User = get_user_model()


def _grant(user, codename):
    perm = Permission.objects.get(content_type__app_label="backstage", codename=codename)
    user.user_permissions.add(perm)
    return User.objects.get(pk=user.pk)  # refresh perm cache


class OperatorPinTests(TestCase):
    def setUp(self):
        self.op = User.objects.create_user("caixa", password="x", is_staff=True, first_name="Ana")
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")

    def test_valid_operator_pin(self):
        self.assertTrue(verify_operator_pin(self.op, "1234"))

    def test_wrong_pin(self):
        self.assertFalse(verify_operator_pin(self.op, "0000"))

    def test_no_pos_permission_blocks(self):
        other = User.objects.create_user("semperm", password="x", is_staff=True)
        PinCredential.set_for(other, "1234")
        self.assertFalse(verify_operator_pin(other, "1234"))

    def test_non_staff_blocks(self):
        cust = User.objects.create_user("cliente", password="x", is_staff=False)
        PinCredential.set_for(cust, "1234")
        cust = _grant(cust, "operate_pos")
        self.assertFalse(verify_operator_pin(cust, "1234"))

    def test_operator_without_pin_blocks(self):
        nopin = User.objects.create_user("novato", password="x", is_staff=True)
        nopin = _grant(nopin, "operate_pos")
        self.assertFalse(verify_operator_pin(nopin, "1234"))

    def test_inactive_blocks(self):
        self.op.is_active = False
        self.op.save(update_fields=["is_active"])
        self.assertFalse(verify_operator_pin(User.objects.get(pk=self.op.pk), "1234"))

    def test_manager_pin_requires_adjust_perm(self):
        mgr = User.objects.create_user("gerente", password="x", is_staff=True)
        PinCredential.set_for(mgr, "9999")
        # only operate_pos → cannot authorize overrides
        mgr = _grant(mgr, "operate_pos")
        self.assertFalse(verify_manager_pin(mgr, "9999"))
        # grant adjust_cashshift → can
        mgr = _grant(mgr, "adjust_cashshift")
        self.assertTrue(verify_manager_pin(mgr, "9999"))

    def test_eligible_operators_lists_only_pinned_permitted_staff(self):
        # op qualifies; others miss a requirement
        User.objects.create_user("sem_pin", password="x", is_staff=True)  # no pin
        usernames = set(eligible_operators().values_list("username", flat=True))
        self.assertIn("caixa", usernames)
        self.assertNotIn("sem_pin", usernames)
