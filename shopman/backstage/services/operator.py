"""Operator identification via PIN or badge for backstage surfaces.

Thin policy layer over doorman's generic ``PinCredential``: which staff users may
operate, and resolving/verifying a credential (PIN typed, or badge scanned) for a
given permission. No credential storage lives here — credentials belong to
doorman. Shared across every operational surface (POS/KDS/orders/production).

Authorization model (OPERATOR-AUTH-PLAN, Opção C): the device holds a Django staff
session (station trust); the *active operator* — established here by PIN or badge —
is the identity the API authorization layer checks permissions against and
attributes actions to. ``perm`` defaults preserve the POS behaviour; the generic
operator unlock passes the surface's own permission (or ``None`` for identity-only).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.doorman.models import PinCredential

User = get_user_model()

OPERATE_POS = "backstage.operate_pos"
ADJUST_CASHSHIFT = "backstage.adjust_cashshift"

# Server-session key holding the active operator on a (shared) terminal. The
# device holds a Django staff session (station trust); the *active operator* is
# the identity established by PIN or badge that the authorization layer (Opção C)
# checks permissions against. Cleared by auto-lock. Decouples "which device is
# authenticated" from "who is operating right now".
ACTIVE_OPERATOR_SESSION_KEY = "active_operator"


def operator_card(user) -> dict:
    """Public projection of an operator (for the lock-screen picker / chip)."""
    return {
        "id": user.pk,
        "username": user.get_username(),
        "name": user.get_full_name().strip() or user.get_username(),
    }


def set_active_operator(request, user) -> dict:
    """Bind the active operator to the current terminal session."""
    card = operator_card(user)
    request.session[ACTIVE_OPERATOR_SESSION_KEY] = {**card, "since": timezone.now().isoformat()}
    return card


def clear_active_operator(request) -> None:
    """Lock the terminal: drop the active operator from the session."""
    request.session.pop(ACTIVE_OPERATOR_SESSION_KEY, None)


def active_operator(request) -> dict | None:
    """The active operator bound to this terminal session, if any."""
    return request.session.get(ACTIVE_OPERATOR_SESSION_KEY)


def eligible_operators(*, perm: str = OPERATE_POS):
    """Active staff users with a credential who may operate the given surface.

    ``perm`` filters to the surface's permission (default POS). Pass ``None`` for
    every credentialed staff operator (the per-action gate enforces the rest).
    """
    qs = User.objects.filter(is_staff=True, is_active=True, pin_credential__isnull=False)
    if perm:
        qs = qs.filter(
            pk__in=User.objects.with_perm(
                perm,
                is_active=True,
                backend="django.contrib.auth.backends.ModelBackend",
            ).values("pk")
        )
    return qs.order_by("first_name", "username").distinct()


def _eligible(user, perm: str | None) -> bool:
    if user is None or not user.is_active or not user.is_staff:
        return False
    if perm and not user.has_perm(perm):
        return False
    return True


def _verify_with_perm(user, raw_pin: str, perm: str | None) -> bool:
    if not _eligible(user, perm):
        return False
    try:
        cred = user.pin_credential
    except PinCredential.DoesNotExist:
        return False
    return cred.verify(raw_pin)


def verify_operator_pin(user, raw_pin: str, *, required_perm: str | None = OPERATE_POS) -> bool:
    """True if ``user`` is an eligible operator (for ``required_perm``) and the PIN matches."""
    return _verify_with_perm(user, raw_pin, required_perm)


def resolve_operator_by_badge(raw_token: str, *, required_perm: str | None = OPERATE_POS):
    """Resolve the operator whose badge matches, eligible for ``required_perm``, or None.

    The badge is a possession-based alternative to typing the PIN (a barcode on the
    operator's crachá). Eligibility (active/staff/perm) is enforced here.
    """
    user = PinCredential.resolve_by_badge(raw_token)
    return user if _eligible(user, required_perm) else None


def verify_manager_pin(user, raw_pin: str) -> bool:
    """True if ``user`` may authorize overrides (cash-shift adjust) and the PIN matches.

    Used by the anti-fraud override gates (void sent item, discount/price,
    refund/cancel, cash-out/no-sale).
    """
    return _verify_with_perm(user, raw_pin, ADJUST_CASHSHIFT)
