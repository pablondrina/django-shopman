from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from shopman.backstage.services.financial_reconciliation import (
    build_financial_reconciliation,
    persist_financial_reconciliation,
)


class Command(BaseCommand):
    help = "Reconcilia financeiramente um dia: pedidos, PaymentIntent, transações e DayClosing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="date",
            default="",
            help="Data local YYYY-MM-DD. Default: ontem, adequado para cron pós-fechamento.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Gera relatório sem persistir em DayClosing e sem criar OperatorAlert.",
        )
        parser.add_argument(
            "--require-closing",
            action="store_true",
            help="Trata ausência de DayClosing como erro em vez de aviso.",
        )
        parser.add_argument(
            "--no-alert",
            action="store_true",
            help="Persiste relatório, mas não cria OperatorAlert.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Imprime o relatório como JSON.",
        )

    def handle(self, *args, **options):
        reconciliation_date = _parse_target_date(options.get("date") or "")
        dry_run = bool(options["dry_run"])

        report = build_financial_reconciliation(
            reconciliation_date=reconciliation_date,
            require_closing=bool(options["require_closing"]),
        )
        if not dry_run:
            report = persist_financial_reconciliation(
                report,
                create_alert=not bool(options["no_alert"]),
            )

        if options["json"]:
            self.stdout.write(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2))
        else:
            self._write_human(report, dry_run=dry_run)

        if report.has_errors:
            raise CommandError(
                f"Reconciliação financeira de {report.date.isoformat()} encontrou divergências."
            )

    def _write_human(self, report, *, dry_run: bool) -> None:
        mode = "dry-run" if dry_run else "aplicado"
        self.stdout.write(self.style.MIGRATE_HEADING(f"Reconciliação financeira {report.date.isoformat()} ({mode})"))
        self.stdout.write(
            "Resumo: "
            f"orders={report.order_count} intents={report.intent_count} tx={report.transaction_count} "
            f"gross={report.order_gross_q}q captured={report.captured_q}q "
            f"refunded={report.refunded_q}q chargeback={report.chargeback_q}q net={report.net_q}q"
        )
        self.stdout.write(f"Métodos: {_format_counts(report.by_method)}")
        self.stdout.write(f"Gateways: {_format_counts(report.by_gateway)}")
        closing = report.day_closing_id or "-"
        self.stdout.write(
            f"DayClosing={closing} persisted={str(report.persisted).lower()} "
            f"alert_created={str(report.alert_created).lower()}"
        )
        counts = report.issue_counts
        self.stdout.write(
            f"Issues: warning={counts['warning']} error={counts['error']} critical={counts['critical']}"
        )
        for issue in report.issues:
            style = self.style.ERROR if issue.severity in {"error", "critical"} else self.style.WARNING
            refs = []
            if issue.order_ref:
                refs.append(f"order={issue.order_ref}")
            if issue.intent_ref:
                refs.append(f"intent={issue.intent_ref}")
            suffix = f" {' '.join(refs)}" if refs else ""
            context = f" context={issue.context}" if issue.context else ""
            self.stdout.write(style(f"- [{issue.severity}] {issue.code}{suffix}: {issue.message}{context}"))
        if not report.issues:
            self.stdout.write(self.style.SUCCESS("Nenhuma divergência financeira encontrada."))


def _parse_target_date(raw: str):
    if not raw:
        return timezone.localdate() - timedelta(days=1)
    parsed = parse_date(raw)
    if parsed is None:
        raise CommandError("Formato inválido para --date. Use YYYY-MM-DD.")
    return parsed


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
