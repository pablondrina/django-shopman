"""Despacha posts de broadcast aprovados com hora marcada.

O gestor aprova de manhã e marca "às 7h"; ninguém precisa estar na tela na
hora. Este comando é quem abre a porta quando o relógio chega — contraparte de
``expire_broadcast_posts``, que fecha quando o prazo passa.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Despacha BroadcastPosts agendados cuja hora de publicação chegou."

    def handle(self, *args, **options):
        from shopman.shop.services import broadcast

        dispatched = broadcast.dispatch_due()
        if dispatched:
            logger.info("dispatch_scheduled_broadcasts: %d post(s) despachado(s)", dispatched)
            self.stdout.write(f"{dispatched} post(s) de broadcast despachado(s).")
        return None
