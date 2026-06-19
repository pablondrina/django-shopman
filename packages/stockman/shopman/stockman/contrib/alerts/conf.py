"""Stockman Alerts configuration.

O cooldown entre re-notificações do mesmo alerta é resolvido em duas camadas,
por prioridade:

1. Um resolver registrado pela aplicação host (o orquestrador injeta um a partir
   da config da loja). Mantém o stockman desacoplado — ele nunca importa o host.
2. Django settings, como fallback estático::

       STOCKMAN_ALERT_COOLDOWN_MINUTES = 60
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings

_DEFAULT_COOLDOWN_MINUTES = 60

_cooldown_resolver: Callable[[], int | None] | None = None


def set_cooldown_resolver(resolver: Callable[[], int | None] | None) -> None:
    """Register (ou limpa com ``None``) um callable que retorna o cooldown em
    minutos. Permite o host dirigir o valor pela sua própria config sem o
    stockman depender dele."""
    global _cooldown_resolver
    _cooldown_resolver = resolver


def get_alert_cooldown_minutes() -> int:
    """
    Return cooldown in minutes between re-notifications for the same alert.

    Resolver do host tem prioridade; senão ``settings.STOCKMAN_ALERT_COOLDOWN_MINUTES``
    (default: 60).
    """
    if _cooldown_resolver is not None:
        resolved = _cooldown_resolver()
        if resolved is not None:
            return resolved
    return getattr(settings, "STOCKMAN_ALERT_COOLDOWN_MINUTES", _DEFAULT_COOLDOWN_MINUTES)
