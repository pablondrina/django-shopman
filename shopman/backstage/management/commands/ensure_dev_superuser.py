"""Create or reset a superuser with a KNOWN password — DEV/STAGING ONLY.

Bypasses the password validators on purpose (so weak dev passwords like "admin"
work), which is exactly why it must NEVER be wired into a production deploy. The
staging bootstrap job calls it for convenience; production uses ``bootstrap_admin``
(env-driven password + validation).

Usage:
    python manage.py ensure_dev_superuser admin --password admin
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria/reseta um superuser com senha conhecida (DEV/STAGING — sem validação)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        user, created = User.objects.update_or_create(
            username=username,
            defaults={"email": options["email"] or f"{username}@example.com"},
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(options["password"])  # no validation — dev only
        user.save()
        verb = "criado" if created else "resetado"
        self.stdout.write(self.style.SUCCESS(f"ensure_dev_superuser: '{username}' {verb} (superuser, ativo)."))
