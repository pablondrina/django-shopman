"""Management command: ifood_poll (WP-2).

Polls the iFood Order Module event stream and ingests new orders.

    python manage.py ifood_poll              # one tick
    python manage.py ifood_poll --watch      # loop every 30s (iFood cadence)
    python manage.py ifood_poll --watch --interval 30

Run one instance per merchant. Idempotency is durable (webhook_idempotency), so
a crash-restart never double-ingests. Meant to run alongside the directive
worker (``process_directives --watch``) which delivers the status callbacks.
"""

from __future__ import annotations

import signal
import time

from django.core.management.base import BaseCommand

from shopman.shop.services import ifood_events


class Command(BaseCommand):
    help = "Poll the iFood event stream and ingest orders. Use --watch for a 30s loop."

    def add_arguments(self, parser):
        parser.add_argument(
            "--watch",
            action="store_true",
            default=False,
            help="Loop continuously instead of polling once.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=30,
            help="Seconds between polls when --watch (iFood recommends 30s).",
        )

    def handle(self, *args, **opts):
        watch = bool(opts["watch"])
        interval = max(int(opts["interval"]), 1)

        if not watch:
            self._tick()
            return

        self._stop = False

        def _graceful(signum, frame):
            self._stop = True
            self.stdout.write(self.style.WARNING("\nifood_poll: stopping…"))

        signal.signal(signal.SIGINT, _graceful)
        signal.signal(signal.SIGTERM, _graceful)

        self.stdout.write(f"ifood_poll: watching (every {interval}s). Ctrl-C to stop.")
        while not self._stop:
            self._tick()
            for _ in range(interval):
                if self._stop:
                    break
                time.sleep(1)

    def _tick(self) -> None:
        summary = ifood_events.run_once()
        if summary["polled"] or summary["failed"]:
            style = self.style.SUCCESS if not summary["failed"] else self.style.WARNING
            self.stdout.write(style(
                f"polled={summary['polled']} ingested={summary['ingested']} "
                f"deduped={summary['deduped']} ignored={summary['ignored']} "
                f"failed={summary['failed']} acked={summary['acked']}"
            ))
