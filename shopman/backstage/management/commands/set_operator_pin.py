"""Provision/rotate an operator's POS PIN.

CLI path for setting operator PINs (initial provisioning / reset). The richer
Admin/Unfold management UI is the canonical operator-facing path and is added
separately under the Unfold canonical gate.

Usage:
    python manage.py set_operator_pin <username> --pin 1234
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.services.operator import OPERATE_POS
from shopman.doorman.models import PinCredential
from shopman.doorman.models.pin_credential import PinCredentialError


class Command(BaseCommand):
    help = "Define ou rotaciona o PIN de POS de um operador (staff)."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username do operador (User Django).")
        parser.add_argument("--pin", required=True, help="PIN numérico (política em DOORMAN.PIN_*).")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        pin = options["pin"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"Operador '{username}' não encontrado.") from exc

        if not user.is_staff:
            raise CommandError(f"'{username}' não é staff — não pode operar o PDV.")
        if not user.has_perm(OPERATE_POS):
            self.stdout.write(
                self.style.WARNING(
                    f"Aviso: '{username}' ainda não tem a permissão {OPERATE_POS} "
                    "(adicione via grupo/Admin para ele operar o PDV)."
                )
            )

        try:
            PinCredential.set_for(user, pin)
        except PinCredentialError as exc:
            raise CommandError(f"PIN inválido: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"PIN definido para operador '{username}'."))
