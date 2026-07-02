"""Worker de manutenção periódica — os "crons" do deployment.

O DigitalOcean App Platform não tem cron nativo; este worker roda o ciclo de
manutenção num loop (default: a cada 5 minutos):

  release_expired_holds     — holds vencidos saem do caminho (higiene)
  cleanup_stale_sessions    — sessões abandonadas antigas
  cleanup_stale_planning    — quants planejados órfãos
  cleanup_d1                — D-1 vencido vira perda
  reconcile_payments        — PIX pago com webhook perdido é resgatado

Cada tarefa é isolada: uma falha loga e NUNCA derruba o ciclo das demais.

Uso:
    python manage.py maintenance_worker             # loop infinito (worker)
    python manage.py maintenance_worker --once      # um ciclo (debug/CI)
    python manage.py maintenance_worker --interval 60
"""

from __future__ import annotations

import logging
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

MAINTENANCE_COMMANDS = (
    "release_expired_holds",
    "cleanup_stale_sessions",
    "cleanup_stale_planning",
    "cleanup_d1",
    "reconcile_payments",
)


class Command(BaseCommand):
    help = "Roda o ciclo de manutenção periódica (crons do deployment) em loop."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=300, help="Segundos entre ciclos (default 300).")
        parser.add_argument("--once", action="store_true", help="Roda um único ciclo e sai.")

    def handle(self, *args, **options):
        interval = max(30, int(options["interval"]))
        while True:
            self._run_cycle()
            if options["once"]:
                return
            time.sleep(interval)

    def _run_cycle(self) -> None:
        for command in MAINTENANCE_COMMANDS:
            try:
                call_command(command)
            except Exception:
                logger.exception("maintenance_worker: %s falhou (ciclo continua)", command)
