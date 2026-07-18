"""Caduca posts de broadcast que ninguém aprovou a tempo.

Frescor é efêmero: "saiu do forno" aprovado duas horas depois vira mentira.
A regra define o prazo (``BroadcastRule.expires_after_minutes``); este comando
é quem fecha a porta quando ele passa, sem depender de alguém abrir a tela.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Expira BroadcastPosts pendentes cujo prazo de aprovação passou."

    def handle(self, *args, **options):
        from shopman.shop.services import broadcast

        expired = broadcast.expire_stale_posts()
        if expired:
            logger.info("expire_broadcast_posts: %d post(s) expirado(s)", expired)
            self.stdout.write(f"{expired} post(s) de broadcast expirado(s).")
        return None
