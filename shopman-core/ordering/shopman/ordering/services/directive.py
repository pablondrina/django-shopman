"""
DirectiveService — Enfileira directives assíncronas.
"""

from __future__ import annotations

import logging

from shopman.ordering.models import Directive

logger = logging.getLogger(__name__)


class DirectiveService:
    """Serviço para enfileirar directives pós-commit."""

    @staticmethod
    def enqueue(*, topic: str, payload: dict | None = None) -> Directive:
        """Cria uma Directive com status 'queued'."""
        payload = payload or {}
        directive = Directive.objects.create(
            topic=topic,
            payload=payload,
        )
        logger.info("Directive enqueued: %s (pk=%s)", topic, directive.pk)
        return directive
