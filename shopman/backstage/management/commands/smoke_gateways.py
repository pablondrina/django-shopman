from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.services.gateway_smoke import run_gateway_smoke


class Command(BaseCommand):
    help = "Executa smoke local de gateways e reporta prontidão sandbox/staging."

    def add_arguments(self, parser):
        parser.add_argument(
            "--local-only",
            action="store_true",
            help="Executa apenas fixtures locais, sem matriz de credenciais sandbox.",
        )
        parser.add_argument(
            "--sandbox-only",
            action="store_true",
            help="Executa apenas matriz de prontidão sandbox/staging, sem fixtures locais.",
        )
        parser.add_argument(
            "--require-sandbox",
            action="store_true",
            help="Falha se qualquer provedor sandbox estiver bloqueado por credencial ou implementação.",
        )
        parser.add_argument(
            "--keep-data",
            action="store_true",
            help="Não faz rollback dos dados criados pelas fixtures locais.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Imprime relatório JSON.",
        )

    def handle(self, *args, **options):
        local_only = bool(options["local_only"])
        sandbox_only = bool(options["sandbox_only"])
        if local_only and sandbox_only:
            raise CommandError("Use apenas um entre --local-only e --sandbox-only.")

        include_local = not sandbox_only
        include_sandbox = not local_only
        report = run_gateway_smoke(
            include_local=include_local,
            include_sandbox_readiness=include_sandbox,
            require_sandbox=bool(options["require_sandbox"]),
            rollback=not bool(options["keep_data"]),
        )

        if options["json"]:
            self.stdout.write(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2))
        else:
            self._write_human(report)

        if report.blocking:
            raise CommandError(f"Smoke gateways terminou com status {report.status}.")

    def _write_human(self, report) -> None:
        style = self.style.SUCCESS if not report.blocking else self.style.ERROR
        self.stdout.write(style(f"Smoke gateways: {report.status}"))
        self.stdout.write(
            "Resumo: "
            f"passed={report.counts['passed']} ready={report.counts['ready']} "
            f"blocked_credentials={report.counts['blocked_by_credentials']} "
            f"blocked_implementation={report.counts['blocked_by_implementation']} "
            f"failed={report.counts['failed']} rolled_back={str(report.rolled_back).lower()}"
        )
        for check in report.checks:
            check_style = self.style.SUCCESS
            if check.status == "failed":
                check_style = self.style.ERROR
            elif check.status.startswith("blocked_by_"):
                check_style = self.style.WARNING
            label = f"{check.provider}.{check.name}"
            self.stdout.write(check_style(f"- [{check.scope}:{check.status}] {label}: {check.message}"))
            if check.details:
                self.stdout.write(f"  details={check.details}")
