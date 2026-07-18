"""Canonical backstage permission predicates.

Single source for "can this operator do X" across the whole backstage
surface: Unfold admin-console pages, the dedicated KDS/POS views, the
sidebar navigation, and the REST API gate. Every predicate takes a
``user`` — the common denominator — so admin pages (``request.user``),
views, and services share one implementation instead of copying the rules.

Grants flow through Django's permission system; doorman wires operator
PIN/role credentials onto Groups, whose permissions these checks read.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def is_staff(user) -> bool:
    return bool(getattr(user, "is_staff", False))


def is_superuser(user) -> bool:
    return bool(getattr(user, "is_superuser", False))


def can_manage_orders(user) -> bool:
    return is_superuser(user) or user.has_perm("shop.manage_orders")


def can_access_production(user) -> bool:
    if is_superuser(user) or user.has_perm("shop.manage_production"):
        return True
    try:
        from shopman.backstage.projections.production import resolve_production_access

        return resolve_production_access(user).can_access_board
    except Exception:
        logger.warning("backstage_production_access_failed", exc_info=True)
        return False


def can_view_production_reports(user) -> bool:
    return (
        is_superuser(user)
        or user.has_perm("backstage.view_production_reports")
        or user.has_perm("shop.manage_production")
    )


def can_close_day(user) -> bool:
    return is_superuser(user) or user.has_perm("backstage.perform_closing")


def can_operate_pos(user) -> bool:
    return is_superuser(user) or user.has_perm("backstage.operate_pos")


def can_operate_kds(user) -> bool:
    return is_superuser(user) or user.has_perm("backstage.operate_kds")


def can_operate_production(user) -> bool:
    """Coarse operator gate for the dedicated production app (``fournil.``).

    Sibling of ``operate_pos``/``operate_kds``: a single surface-entry grant for
    the floor + planning app, granted to the Cozinha/Gerente groups. The
    fine-grained column control (``resolve_production_access`` / the
    ``*_production_*`` perms on ``shop.shop``) keeps governing the Admin console
    and is intentionally left untouched.
    """
    return is_superuser(user) or user.has_perm("backstage.operate_production")


def can_manage_broadcast(user) -> bool:
    """Gate do app Broadcast (marketing operacional).

    Deliberadamente separado de ``can_manage_orders``: quem cuida da fila de
    pedidos não é necessariamente quem decide o que a padaria publica
    (FOMO-BROADCAST-SPECS §8).
    """
    return is_superuser(user) or user.has_perm("shop.manage_broadcast")


def can_view_operator_alerts(user) -> bool:
    return is_staff(user) and (
        is_superuser(user)
        or can_manage_orders(user)
        or can_access_production(user)
        or can_operate_pos(user)
        or can_operate_kds(user)
        or can_operate_production(user)
    )
