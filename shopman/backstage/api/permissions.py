"""Backstage API auth gate.

All backstage endpoints require an authenticated staff user. We rely on
Django's session auth (DRF SessionAuthentication or middleware-set
``request.user``).
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission


class IsBackstageOperator(BasePermission):
    """Allow any authenticated staff user."""

    message = "Acesso restrito a operadores."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)


class HasBackstagePermission(BasePermission):
    """Check a specific Django permission code declared on the view.

    The view must define ``required_permission = "backstage.operate_kds"``
    (or similar). Falls back to staff-only when no permission is declared.

    **Opção C (gated by ``SHOPMAN_REQUIRE_ACTIVE_OPERATOR``):** when ON, the device
    session only provides station trust — the permission is checked against the
    ACTIVE OPERATOR (established by PIN/badge), and the action is attributed to
    them (``request.active_operator_user``). No active operator → 403 (locked);
    active operator without the permission → 403 (forbidden). When OFF (default),
    the device session user decides — today's behaviour, unchanged.
    """

    message = "Acesso restrito a operadores."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and user.is_staff):
            return False
        perm = getattr(view, "required_permission", None)

        if not getattr(settings, "SHOPMAN_REQUIRE_ACTIVE_OPERATOR", False):
            # Default / legacy: the authenticated device session decides.
            return perm is None or user.has_perm(perm)

        # Opção C: authorize against the operator who unlocked the terminal.
        from shopman.backstage.services.operator import resolve_active_operator_user

        operator = resolve_active_operator_user(request)
        if operator is None:
            self.message = "Estação travada. Identifique-se com PIN ou crachá."
            return False
        request.active_operator_user = operator
        if perm is not None and not operator.has_perm(perm):
            self.message = "Operador sem permissão para esta ação."
            return False
        return True


class CanViewOperatorAlerts(BasePermission):
    """Any operator persona that may see operator alerts.

    Wraps the canonical ``can_view_operator_alerts`` predicate (staff + any
    operator capability) so alert endpoints share the same rule as the sidebar
    badge and the legacy HTMX panel.
    """

    message = "Acesso restrito a operadores."

    def has_permission(self, request, view) -> bool:
        from shopman.backstage.permissions import can_view_operator_alerts

        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and can_view_operator_alerts(user))
