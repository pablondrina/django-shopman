"""Operator identification via PIN for backstage surfaces (POS/KDS/orders).

Thin policy layer over doorman's generic ``PinCredential``: which staff users may
operate, and verifying a PIN against the required permission. No PIN storage
lives here — credentials belong to doorman. This service is shared across
operational surfaces (POS today; KDS/order manager next).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from shopman.doorman.models import PinCredential

User = get_user_model()

OPERATE_POS = "backstage.operate_pos"
ADJUST_CASHSHIFT = "backstage.adjust_cashshift"


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
