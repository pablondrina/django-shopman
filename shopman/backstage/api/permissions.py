"""Backstage API auth gate.

All backstage endpoints require an authenticated staff user. We rely on
Django's session auth (DRF SessionAuthentication or middleware-set
``request.user``).
"""

from __future__ import annotations

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
    """

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and user.is_staff):
            return False
        perm = getattr(view, "required_permission", None)
        if perm is None:
            return True
        return user.has_perm(perm)


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
