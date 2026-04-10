from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Sequence

from django.core.management import BaseCommand
from django.db import transaction
from django.utils import timezone

from shopman.orderman import registry
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
REAP_STUCK_TIMEOUT_MINUTES = 10


def _backoff_seconds(attempts: int) -> int:
    """Exponential backoff: 2^attempts seconds."""
    return 2 ** attempts


def _reap_stuck_directives(timeout_minutes: int, max_attempts: int) -> int:
    """
    Reset directives stuck in "running" back to "queued" for retry.

    A directive is considered stuck if:
    - status == "running"
    - started_at is older than timeout_minutes ago

    This covers the case where a worker crashes (OOM, deploy, power failure)
    between marking a directive as "running" and completing processing.

    Returns:
        Number of directives reaped.
    """
    cutoff = timezone.now() - timedelta(minutes=timeout_minutes)

    with transaction.atomic():
        stuck = (
            Directive.objects.select_for_update(skip_locked=True)
            .filter(status="running", started_at__lte=cutoff)
        )
        stuck_list = list(stuck)

        reaped = 0
        for d in stuck_list:
            if d.attempts >= max_attempts:
                d.status = "failed"
                d.last_error = f"Stuck in 'running' for >{timeout_minutes}min (reaped after {d.attempts} attempts)"
            else:
                d.status = "queued"
                d.available_at = timezone.now()
                d.last_error = f"Stuck in 'running' for >{timeout_minutes}min (reaped, will retry)"
            d.save(update_fields=["status", "available_at", "last_error", "updated_at"])
            reaped += 1

    return reaped


class Command(BaseCommand):
    help = "Processa diretivas enfileiradas usando os handlers registrados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--topic",
            action="append",
            dest="topics",
            default=None,
            help="Topic específico para processar (pode repetir a opção). Omitido = todos os registrados.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Quantidade máxima de diretivas processadas nesta execução (default: 50).",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Mantém o comando rodando em loop (worker simples).",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=2.0,
            help="Intervalo (segundos) entre execuções quando usado com --watch (default: 2s).",
        )
        parser.add_argument(
            "--max-attempts",
            type=int,
            default=MAX_ATTEMPTS,
            help=f"Número máximo de tentativas antes de marcar como failed (default: {MAX_ATTEMPTS}).",
        )
        parser.add_argument(
            "--reap-timeout",
            type=int,
            default=REAP_STUCK_TIMEOUT_MINUTES,
            help=(
                f"Minutos após os quais uma diretiva 'running' é considerada stuck "
                f"e resetada para retry (default: {REAP_STUCK_TIMEOUT_MINUTES}). "
                f"Use 0 para desabilitar."
            ),
        )

    def handle(self, *args, **opts):
        topics: Sequence[str] | None = opts.get("topics")
        if topics:
            topics = [t for t in topics if t]
        else:
            topics = sorted(registry.get_directive_handlers().keys())

        if not topics:
            self.stdout.write(self.style.WARNING("Nenhum handler registrado. Nada a fazer."))
            return

        limit = max(int(opts.get("limit") or 1), 1)
        watch = bool(opts.get("watch"))
        interval = max(float(opts.get("interval") or 1.0), 0.5)
        max_attempts = max(int(opts.get("max_attempts") or MAX_ATTEMPTS), 1)
        reap_timeout = max(int(opts.get("reap_timeout") or 0), 0)

        def _reap():
            """Reap stuck directives before processing new ones."""
            if not reap_timeout:
                return
            reaped = _reap_stuck_directives(reap_timeout, max_attempts)
            if reaped:
                self.stdout.write(
                    self.style.WARNING(f"Reaper: {reaped} diretiva(s) stuck resetada(s).")
                )

        def _cycle():
            now = timezone.now()

            # Acquire directives with row-level lock (skip_locked prevents duplicate processing)
            with transaction.atomic():
                qs = (
                    Directive.objects.select_for_update(skip_locked=True)
                    .filter(status="queued", topic__in=topics, available_at__lte=now)
                    .order_by("available_at", "id")
                )
                directives = list(qs[:limit])

                if not directives:
                    return False

                for d in directives:
                    d.status = "running"
                    d.attempts += 1
                    d.started_at = now
                    d.save(update_fields=["status", "attempts", "started_at", "updated_at"])

            # Process outside the lock transaction
            processed = 0
            failures = 0

            for directive in directives:
                handler = registry.get_directive_handler(directive.topic)
                if not handler:
                    self.stdout.write(
                        self.style.WARNING(f"Ignorando tópico {directive.topic}: nenhum handler registrado.")
                    )
                    directive.status = "queued"
                    directive.attempts -= 1
                    directive.save(update_fields=["status", "attempts", "updated_at"])
                    continue

                try:
                    handler.handle(message=directive, ctx={"actor": "process_directives"})
                    directive.error_code = ""
                    directive.save(update_fields=["error_code", "updated_at"])
                    processed += 1
                except DirectiveTerminalError as exc:
                    logger.error(
                        "Directive %s #%s terminal failure (attempt %d): %s",
                        directive.topic, directive.pk, directive.attempts, exc,
                    )
                    directive.status = "failed"
                    directive.error_code = "terminal"
                    directive.last_error = str(exc)[:500]
                    directive.save(update_fields=["status", "error_code", "last_error", "updated_at"])
                    failures += 1
                    self.stderr.write(
                        self.style.ERROR(f"Terminal: {directive.topic} #{directive.pk}: {exc}")
                    )
                except DirectiveTransientError as exc:
                    logger.warning(
                        "Directive %s #%s transient failure (attempt %d/%d): %s",
                        directive.topic, directive.pk, directive.attempts, max_attempts, exc,
                    )
                    if directive.attempts >= max_attempts:
                        directive.status = "failed"
                        directive.error_code = "terminal"
                    else:
                        directive.status = "queued"
                        directive.error_code = "transient"
                        directive.available_at = now + timedelta(seconds=_backoff_seconds(directive.attempts))
                    directive.last_error = str(exc)[:500]
                    directive.save(update_fields=["status", "error_code", "available_at", "last_error", "updated_at"])
                    failures += 1
                    self.stderr.write(
                        self.style.WARNING(f"Transient: {directive.topic} #{directive.pk}: {exc}")
                    )
                except Exception as exc:
                    logger.exception("Directive %s #%s failed (attempt %d/%d)", directive.topic, directive.pk, directive.attempts, max_attempts)
                    if directive.attempts >= max_attempts:
                        directive.status = "failed"
                        directive.error_code = "terminal"
                    else:
                        directive.status = "queued"
                        directive.error_code = "transient"
                        directive.available_at = now + timedelta(seconds=_backoff_seconds(directive.attempts))
                    directive.last_error = str(exc)[:500]
                    directive.save(update_fields=["status", "error_code", "available_at", "last_error", "updated_at"])
                    failures += 1
                    self.stderr.write(
                        self.style.ERROR(f"Erro ao processar {directive.topic} #{directive.pk}: {exc}")
                    )

            self.stdout.write(self.style.SUCCESS(f"Diretivas concluídas: {processed}"))
            if failures:
                self.stdout.write(self.style.ERROR(f"Diretivas com erro: {failures}"))
            return True

        # Single-run mode
        if not watch:
            _reap()
            _cycle()
            return

        # Watch mode
        self.stdout.write(self.style.WARNING("Worker iniciado: Ctrl+C para sair."))
        try:
            cycle_count = 0
            while True:
                # Reap stuck directives every 5 cycles to avoid overhead
                if cycle_count % 5 == 0:
                    _reap()
                had_work = _cycle()
                cycle_count += 1
                time.sleep(interval if had_work else interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Worker encerrado."))
