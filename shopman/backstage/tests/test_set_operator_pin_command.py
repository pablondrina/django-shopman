"""Tests for the set_operator_pin management command."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from shopman.backstage.services.operator import verify_operator_pin
from shopman.doorman.models import PinCredential

User = get_user_model()


class SetOperatorPinCommandTests(TestCase):
    def test_sets_pin_for_staff(self):
        op = User.objects.create_user("ana", password="x", is_staff=True)
        call_command("set_operator_pin", "ana", "--pin", "1234")
        self.assertTrue(PinCredential.objects.get(user=op).verify("1234"))

    def test_rotates_existing_pin(self):
        op = User.objects.create_user("ana", password="x", is_staff=True)
        call_command("set_operator_pin", "ana", "--pin", "1234")
        call_command("set_operator_pin", "ana", "--pin", "5678")
        cred = PinCredential.objects.get(user=op)
        self.assertTrue(cred.verify("5678"))
        self.assertEqual(PinCredential.objects.filter(user=op).count(), 1)

    def test_rejects_unknown_user(self):
        with self.assertRaises(CommandError):
            call_command("set_operator_pin", "ghost", "--pin", "1234")

    def test_rejects_non_staff(self):
        User.objects.create_user("cliente", password="x", is_staff=False)
        with self.assertRaises(CommandError):
            call_command("set_operator_pin", "cliente", "--pin", "1234")

    def test_rejects_invalid_pin(self):
        User.objects.create_user("ana", password="x", is_staff=True)
        with self.assertRaises(CommandError):
            call_command("set_operator_pin", "ana", "--pin", "12")  # too short

    def test_pin_works_for_verify_when_operator_permitted(self):
        from django.contrib.auth.models import Permission

        op = User.objects.create_user("ana", password="x", is_staff=True)
        op.user_permissions.add(
            Permission.objects.get(content_type__app_label="backstage", codename="operate_pos")
        )
        call_command("set_operator_pin", "ana", "--pin", "4321")
        op = User.objects.get(pk=op.pk)
        self.assertTrue(verify_operator_pin(op, "4321"))
