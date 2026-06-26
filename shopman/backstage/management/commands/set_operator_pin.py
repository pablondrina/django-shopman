"""Provision/rotate an operator's PIN (and, optionally, badge).

CLI path for setting operator credentials (initial provisioning / reset / staging
bootstrap). The credential is shared across every operator surface (POS/KDS/orders/
production) — the per-surface permission decides what the operator can do once
unlocked. The richer Admin/Unfold management UI is the canonical operator-facing
path.

Usage:
    python manage.py set_operator_pin <username> --pin 1234
    python manage.py set_operator_pin <username> --pin 1234 --badge <token>
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from shopman.doorman.models import PinCredential, PinCredentialError


class Command(BaseCommand):
    help = "Define ou rotaciona o PIN (e opcionalmente o crachá) de um operador (staff)."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username do operador (User Django).")
        parser.add_argument("--pin", required=True, help="PIN numérico (política em DOORMAN.PIN_*).")
        parser.add_argument(
            "--badge",
            default="",
            help="Token do crachá (código de barras) — alternativa de posse ao PIN. Vazio = não mexe.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        pin = options["pin"]
        badge = (options.get("badge") or "").strip()

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"Operador '{username}' não encontrado.") from exc

        if not user.is_staff:
            raise CommandError(f"'{username}' não é staff — não pode operar.")

        try:
            cred = PinCredential.set_for(user, pin)
        except PinCredentialError as exc:
            raise CommandError(f"PIN inválido: {exc}") from exc

        if badge:
            cred.set_badge(badge)
            self.stdout.write(self.style.SUCCESS(f"PIN + crachá definidos para operador '{username}'."))
        else:
            self.stdout.write(self.style.SUCCESS(f"PIN definido para operador '{username}'."))
