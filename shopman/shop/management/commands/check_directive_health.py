"""Saúde da fila de directives — a observabilidade mínima exigida pela ADR-003.

Sem dead-letter queue, uma directive `failed` silencia; sob carga, backlog
`queued` cresce invisível; um worker morto ninguém percebe. Este check roda no
ciclo do maintenance_worker e vira OperatorAlert (debounce 15min) quando:

  * failed spike   — N+ directives falharam na janela recente;
  * backlog        — N+ directives `queued` vencidas há mais de X min
                     (nem o dispatch por signal nem o worker processaram);
  * worker parado  — heartbeat do process_directives sem ciclo há X min
                     (só alerta com batimento CONHECIDO envelhecido; ausência
                     de chave é "desconhecido" — em dev/CI o cache locmem é
                     por processo e o batimento de outro processo é invisível).

Thresholds via settings (defaults na ADR): SHOPMAN_DIRECTIVE_FAILED_ALERT_THRESHOLD,
SHOPMAN_DIRECTIVE_FAILED_WINDOW_MINUTES, SHOPMAN_DIRECTIVE_BACKLOG_ALERT_THRESHOLD,
SHOPMAN_DIRECTIVE_BACKLOG_AGE_MINUTES, SHOPMAN_WORKER_HEARTBEAT_STALE_MINUTES.

Uso:
    python manage.py check_directive_health
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Checa saúde da fila de directives (failed, backlog, heartbeat) e alerta o operador."

    def handle(self, *args, **options):
        from shopman.orderman.models import Directive

        from shopman.shop.services.observability import operational_event

        now = timezone.now()

        failed_threshold = int(getattr(settings, "SHOPMAN_DIRECTIVE_FAILED_ALERT_THRESHOLD", 5))
        failed_window = int(getattr(settings, "SHOPMAN_DIRECTIVE_FAILED_WINDOW_MINUTES", 60))
        backlog_threshold = int(getattr(settings, "SHOPMAN_DIRECTIVE_BACKLOG_ALERT_THRESHOLD", 5))
        backlog_age = int(getattr(settings, "SHOPMAN_DIRECTIVE_BACKLOG_AGE_MINUTES", 10))
        heartbeat_stale = int(getattr(settings, "SHOPMAN_WORKER_HEARTBEAT_STALE_MINUTES", 15))

        failed_recent = Directive.objects.filter(
            status="failed",
            updated_at__gte=now - timedelta(minutes=max(1, failed_window)),
        ).count()

        backlog_overdue = Directive.objects.filter(
            status="queued",
            available_at__lt=now - timedelta(minutes=max(1, backlog_age)),
        ).count()

        operational_event(
            "directive_health.checked",
            failed_recent=failed_recent,
            backlog_overdue=backlog_overdue,
        )

        if failed_recent >= max(1, failed_threshold):
            self._alert_failed_spike(failed_recent, failed_window)

        if backlog_overdue >= max(1, backlog_threshold):
            self._alert_backlog(backlog_overdue, backlog_age)

        self._check_worker_heartbeat(now, heartbeat_stale)

        self.stdout.write(
            f"directive_health: failed_recent={failed_recent} backlog_overdue={backlog_overdue}"
        )

    def _alert_failed_spike(self, count: int, window_minutes: int) -> None:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="directive_failed_spike",
            severity="error",
            message=(
                f"{count} directive(s) falharam em definitivo nos últimos "
                f"{window_minutes} min. Tarefas de fundo (notificação, fiscal, "
                "estoque) podem ter sido perdidas — conferir no Admin (Diretivas, "
                "status 'falhou')."
            ),
            dedupe_key="directive_failed_spike",
        )

    def _alert_backlog(self, count: int, age_minutes: int) -> None:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="directive_backlog",
            severity="error",
            message=(
                f"{count} directive(s) na fila vencidas há mais de {age_minutes} min "
                "sem processamento. O pipeline de tarefas de fundo pode estar "
                "parado ou sobrecarregado — conferir o worker de directives."
            ),
            dedupe_key="directive_backlog",
        )

    def _check_worker_heartbeat(self, now, stale_minutes: int) -> None:
        from shopman.orderman import worker_heartbeat

        from shopman.shop.services.observability import create_operator_alert

        last = worker_heartbeat.last_beat(worker_heartbeat.PROCESS_DIRECTIVES_WORKER)
        if last is None:
            logger.info(
                "directive_health: heartbeat do process_directives desconhecido "
                "(worker nunca visto por este cache) — sem alerta."
            )
            return

        age = now - last
        if age < timedelta(minutes=max(1, stale_minutes)):
            return

        create_operator_alert(
            type="directive_worker_stale",
            severity="critical",
            message=(
                "O worker de directives (process_directives) não completa um ciclo "
                f"há {int(age.total_seconds() // 60)} min. Notificações, fiscal e "
                "demais tarefas de fundo dependem dele — verificar o processo."
            ),
            dedupe_key="directive_worker_stale:process_directives",
        )
