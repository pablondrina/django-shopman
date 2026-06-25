"""Enroll a TOTP device for an admin user (admin 2FA).

Creates a confirmed TOTP device and prints the otpauth:// provisioning URI plus an
ASCII QR to scan with an authenticator app. Run this for each superuser BEFORE
enabling ``SHOPMAN_ADMIN_REQUIRE_2FA`` (otherwise they'd be locked out).

    python manage.py setup_admin_totp pablo
    python manage.py setup_admin_totp pablo --force   # replace existing device
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Enroll a confirmed TOTP device for an admin user and print the provisioning URI/QR."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--name", default="admin", help="device label (default: admin)")
        parser.add_argument(
            "--force",
            action="store_true",
            help="replace any existing confirmed TOTP device for the user",
        )

    def handle(self, *args, **options):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["username"])
        except user_model.DoesNotExist as exc:
            raise CommandError(f"Usuário '{options['username']}' não encontrado.") from exc

        existing = TOTPDevice.objects.filter(user=user, confirmed=True)
        if existing.exists():
            if not options["force"]:
                raise CommandError(
                    f"{user.get_username()} já tem um TOTP device confirmado. "
                    "Use --force para substituir."
                )
            existing.delete()

        device = TOTPDevice.objects.create(user=user, name=options["name"], confirmed=True)
        uri = device.config_url

        self.stdout.write(self.style.SUCCESS(f"TOTP device criado para {user.get_username()}."))
        self.stdout.write("")
        self.stdout.write("Provisioning URI (cole no app autenticador ou escaneie o QR):")
        self.stdout.write(uri)
        self.stdout.write("")
        self._print_qr(uri)
        self.stdout.write("")
        self.stdout.write(
            "Depois que TODOS os superusers tiverem um device, ligue o gate com "
            "SHOPMAN_ADMIN_REQUIRE_2FA=true."
        )

    def _print_qr(self, uri: str) -> None:
        # qrcode é dependência fixa do projeto (pyproject) — sempre disponível.
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.make(fit=True)
        qr.print_ascii(out=self.stdout, invert=True)
