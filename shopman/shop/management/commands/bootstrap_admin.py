"""Create or update the nominal owner admin user."""

from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create/update a named superuser from environment variables, idempotently."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Admin username. Defaults to SHOPMAN_ADMIN_USERNAME.")
        parser.add_argument("--email", help="Admin email. Defaults to SHOPMAN_ADMIN_EMAIL.")
        parser.add_argument(
            "--password-env",
            default="SHOPMAN_ADMIN_PASSWORD",
            help="Environment variable containing the admin password.",
        )
        parser.add_argument(
            "--deactivate-seed-admin",
            action="store_true",
            help="Deactivate the seed user named 'admin' after creating/updating the named admin.",
        )

    def handle(self, *args, **options):
        username = (options["username"] or os.environ.get("SHOPMAN_ADMIN_USERNAME") or "").strip()
        email = (options["email"] or os.environ.get("SHOPMAN_ADMIN_EMAIL") or "").strip()
        password_env = options["password_env"]
        password = os.environ.get(password_env, "")

        if not username:
            raise CommandError("Informe --username ou SHOPMAN_ADMIN_USERNAME.")
        if not email:
            raise CommandError("Informe --email ou SHOPMAN_ADMIN_EMAIL.")
        if not password:
            raise CommandError(f"{password_env} precisa estar definido.")
        self._validate_password(password, username=username)

        User = get_user_model()
        with transaction.atomic():
            user, created = User.objects.get_or_create(username=username, defaults={"email": email})
            user.email = email
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.set_password(password)
            user.save()

            deactivated_seed_admin = False
            if options["deactivate_seed_admin"] and username != "admin":
                deactivated_seed_admin = (
                    User.objects.filter(username="admin", is_active=True)
                    .exclude(pk=user.pk)
                    .update(is_active=False)
                    > 0
                )

        action = "criado" if created else "atualizado"
        self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: superuser '{username}' {action}."))
        if deactivated_seed_admin:
            self.stdout.write("bootstrap_admin: seed user 'admin' desativado.")

    def _validate_password(self, password: str, *, username: str) -> None:
        if settings.DEBUG:
            return

        normalized = password.strip().lower()
        weak_values = {
            "admin",
            "password",
            "shopman",
            "changeme",
            "change-me",
            username.lower(),
        }
        if len(password) < 12 or normalized in weak_values:
            raise CommandError(
                "Senha insegura para superuser fora de DEBUG; use SHOPMAN_ADMIN_PASSWORD forte."
            )
