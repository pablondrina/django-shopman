"""Console notification adapter for development and testing."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """
    Log notification to console.

    Args:
        recipient: Recipient identifier (phone, email, etc.).
        template: Event template name (e.g. "order_confirmed").
        context: Template variables.

    Returns:
        Always True.
    """
    logger.info(
        "\n%s\nNOTIFICATION: %s\nTo: %s\nContext: %s\n%s",
        "=" * 50,
        template,
        recipient,
        json.dumps(context or {}, indent=2, default=str),
        "=" * 50,
    )
    return True


def is_available(recipient: str | None = None, **config) -> bool:
    """Console adapter is always available."""
    return True
