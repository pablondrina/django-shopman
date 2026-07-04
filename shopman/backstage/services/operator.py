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
    """The active operator card bound to this terminal session, if any."""
    return request.session.get(ACTIVE_OPERATOR_SESSION_KEY)


def resolve_active_operator_user(request):
    """Load the active operator's User (still active staff), or None.

    Used by the Opção C authorization layer to check permissions against the
    operator who unlocked the terminal — not the device session user.
    """
    card = active_operator(request)
    if not card or not card.get("id"):
        return None
    return User.objects.filter(pk=card["id"], is_active=True, is_staff=True).first()


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


# ── PIN self-service (change) + manager reset ────────────────────────────────

MANAGE_OPERATORS = "backstage.manage_operators"


class PinChangeError(ValueError):
    """A self-service PIN change/reset failed, with a stable ``code`` for the UI."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def pin_must_change(user) -> bool:
    """Whether ``user`` was handed a temp PIN and must rotate it before operating."""
    if user is None:
        return False
    try:
        return bool(user.pin_credential.must_change)
    except PinCredential.DoesNotExist:
        return False


def resolve_target_for_pin_change(request, operator_id=None):
    """Who is having their PIN changed: explicit ``operator_id``, else active operator,
    else the device session user (personal devices). ``current_pin`` still gates it.

    The explicit id supports the lock-screen forced-change (temp PIN as current),
    where no operator is active yet. It is not an escalation: the change still
    requires proving that operator's current PIN.
    """
    raw_id = str(operator_id or "").strip()
    if raw_id:
        return User.objects.filter(pk=raw_id, is_active=True, is_staff=True).first()
    operator = resolve_active_operator_user(request)
    if operator is not None:
        return operator
    device_user = getattr(request, "user", None)
    if device_user is not None and device_user.is_authenticated and device_user.is_staff:
        return device_user
    return None


def change_own_pin(user, current_pin: str, new_pin: str) -> None:
    """Prove the current PIN and rotate to a new one (self-service).

    Proving ``current_pin`` *is* the authorization — you can only rotate a PIN you
    already know. A wrong current PIN counts toward lockout (brute-force defense).
    ``set_pin`` clears ``must_change``, so a real rotation satisfies a forced change.
    Raises :class:`PinChangeError` (wrong/locked/no credential) or
    :class:`PinCredentialError` (new PIN violates policy).
    """
    if user is None:
        raise PinChangeError("no_credential", "Operador não identificado.")
    try:
        cred = user.pin_credential
    except PinCredential.DoesNotExist:
        raise PinChangeError(
            "no_credential", "Você ainda não tem um PIN. Peça ao gerente para provisionar."
        )
    if cred.is_locked:
        raise PinChangeError(
            "locked", "PIN bloqueado por tentativas. Aguarde ou peça desbloqueio ao gerente."
        )
    if not cred.verify(current_pin):
        raise PinChangeError("invalid_current", "PIN atual incorreto.")
    # validate_raw (via set_pin) raises PinCredentialError before mutating on policy failure.
    cred.set_pin(new_pin)


def _generate_temp_pin() -> str:
    """A random numeric temp PIN that satisfies the configured minimum length."""
    import secrets

    from shopman.doorman.conf import doorman_settings

    length = max(4, doorman_settings.PIN_MIN_LENGTH)
    return "".join(secrets.choice("0123456789") for _ in range(length))


def reset_operator_pin(target_user, *, temp_pin: str | None = None) -> str:
    """Manager reset: set a temp PIN on ``target_user`` and force a change on first use.

    Returns the temp PIN (generated when not supplied) — shown to the manager once,
    never stored in plaintext. Authorization (``manage_operators``) is the caller's
    responsibility (the API gate). Raises :class:`PinChangeError` on a bad target or
    :class:`PinCredentialError` when a supplied temp PIN violates policy.
    """
    if target_user is None or not getattr(target_user, "is_active", False):
        raise PinChangeError("no_target", "Operador não encontrado.")
    temp = (temp_pin or "").strip() or _generate_temp_pin()
    PinCredential.validate_raw(temp)  # policy check before writing (raises PinCredentialError)
    PinCredential.set_for(target_user, temp, must_change=True)
    return temp
