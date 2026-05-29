"""Operator identification via PIN for backstage surfaces (POS/KDS/orders).

Thin policy layer over doorman's generic ``PinCredential``: which staff users may
operate, and verifying a PIN against the required permission. No PIN storage
lives here — credentials belong to doorman. This service is shared across
operational surfaces (POS today; KDS/order manager next).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from shopman.doorman.models import PinCredential

User = get_user_model()

OPERATE_POS = "backstage.operate_pos"
ADJUST_CASHSHIFT = "backstage.adjust_cashshift"

# Server-session key holding the active operator on a (shared) terminal. The
# terminal is authenticated as a Django staff user; the *active operator* is a
# lightweight identity layer established by PIN, used for attribution and
# cleared by auto-lock. Decouples "who is authenticated to the device" from
# "who is ringing this sale".
ACTIVE_OPERATOR_SESSION_KEY = "pos_active_operator"


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


def eligible_operators():
    """Active staff users allowed to operate the POS that have a PIN set."""
    return (
        User.objects.with_perm(
            OPERATE_POS,
            is_active=True,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        .filter(is_staff=True, pin_credential__isnull=False)
        .order_by("first_name", "username")
        .distinct()
    )


def _verify_with_perm(user, raw_pin: str, perm: str) -> bool:
    if user is None or not user.is_active or not user.is_staff:
        return False
    if not user.has_perm(perm):
        return False
    try:
        cred = user.pin_credential
    except PinCredential.DoesNotExist:
        return False
    return cred.verify(raw_pin)


def verify_operator_pin(user, raw_pin: str) -> bool:
    """True if ``user`` is an eligible operator and the PIN matches."""
    return _verify_with_perm(user, raw_pin, OPERATE_POS)


def verify_manager_pin(user, raw_pin: str) -> bool:
    """True if ``user`` may authorize overrides (cash-shift adjust) and the PIN matches.

    Used by the anti-fraud override gates (void sent item, discount/price,
    refund/cancel, cash-out/no-sale).
    """
    return _verify_with_perm(user, raw_pin, ADJUST_CASHSHIFT)
