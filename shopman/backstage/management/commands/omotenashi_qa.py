from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.services.omotenashi_qa import build_omotenashi_qa_report


class Command(BaseCommand):
    help = "Lista a matriz manual QA Omotenashi com evidencias do seed."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Imprime relatório JSON.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Falha se qualquer cenario da matriz estiver sem evidencia de seed.",
        )

    def handle(self, *args, **options):
        report = build_omotenashi_qa_report()

        if options["json"]:
            self.stdout.write(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2))
        else:
            self._write_human(report)

        if options["strict"] and report.blocking:
            raise CommandError(f"QA Omotenashi incompleto: {report.missing_count} cenario(s) sem evidencia.")

    def _write_human(self, report) -> None:
        style = self.style.SUCCESS if not report.blocking else self.style.WARNING
        self.stdout.write(style(f"QA Omotenashi: {report.status}"))
        self.stdout.write(
            f"Resumo: ready={report.ready_count} missing={report.missing_count} total={len(report.checks)}"
        )
        for check in report.checks:
            check_style = self.style.SUCCESS if check.status == "ready" else self.style.WARNING
            self.stdout.write(check_style(f"- [{check.status}] {check.id}"))
            self.stdout.write(f"  surface={check.surface} viewport={check.viewport} persona={check.persona}")
            self.stdout.write(f"  abrir={check.url}")
            self.stdout.write(f"  esperar={check.expectation}")
            self.stdout.write(f"  evidencia={check.evidence}")
            if check.blocker:
                self.stdout.write(f"  blocker={check.blocker}")
