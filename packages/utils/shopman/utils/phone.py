"""
Phone normalization for the Shopman suite.

Uses Google's libphonenumber for robust normalization and validation.
Replaces the custom implementations in auth/utils.py and customers/utils.py.

Handles the known Manychat bug where Brazilian numbers are sent without
the country code 55 (e.g., +43984049009 instead of +5543984049009).
"""

import re

try:
    import phonenumbers
except ImportError:
    phonenumbers = None  # type: ignore[assignment]

# Brazilian DDD codes start at 11 (São Paulo)
_MIN_BR_DDD = 11


def _is_phone_brazilian(digits: str) -> bool:
    """
    Detect Brazilian phone without country code: DDD9XXXXXXXX (11 digits, no leading 55).

    Pattern: 2-digit DDD (>= 11) + 9-digit mobile (starts with 9).
    Heuristic only — conflicts with some international numbers (e.g., Austria +43).
    """
    if len(digits) != 11:
        return False
    ddd = digits[:2]
    try:
        if int(ddd) < _MIN_BR_DDD:
            return False
    except ValueError:
        return False
    return digits[2] == "9"


def _prepare_phone_digits_for_parse(
    digits: str,
    *,
    has_plus: bool,
    default_region: str,
    repair_brazilian_plus: bool,
) -> tuple[str, bool]:
    """Resolve Brazilian national/DDI ambiguity before libphonenumber parsing."""
    region = (default_region or "").upper()

    # Manychat bug detection: +DDD9XXXXXXXX without 55 prefix.
    if repair_brazilian_plus and has_plus and _is_phone_brazilian(digits):
        return f"55{digits}", True

    if region != "BR":
        return digits, has_plus

    # Brazilian iOS/autofill sometimes stores +55 0DD ...
    if has_plus and digits.startswith("550") and len(digits) in (13, 14):
        return f"55{digits[3:]}", True

    # A bare 55DD... value in a Brazilian field is DDI 55, not DDD 55.
    # libphonenumber.parse("5543984049009", "BR") otherwise interprets the
    # first 55 as area code and can collapse the actual phone identity.
    if not has_plus and digits.startswith("55") and len(digits) in (12, 13, 14):
        national = digits[2:]
        if national.startswith("0") and len(national) in (11, 12):
            national = national[1:]
        if len(national) in (10, 11):
            return f"55{national}", True

    # National trunk prefix: 0DD + number.
    if not has_plus and digits.startswith("0") and len(digits) in (11, 12):
        return digits[1:], False

    return digits, has_plus


def normalize_phone(
    value: str,
    default_region: str = "BR",
    contact_type: str | None = None,
    repair_brazilian_plus: bool = True,
) -> str:
    """
    Normalize phone number to E.164 format.

    Handles:
    - Brazilian mobile/landline with/without country code
    - Manychat bug (+DDD9XXXXXXXX missing country code 55)
    - International numbers (any country)
    - Email passthrough (lowercased)
    - Instagram passthrough (lowercased, @ stripped)

    Args:
        value: Raw phone number, email, or Instagram handle.
        default_region: ISO country code for numbers without country code.
        contact_type: Optional hint ("instagram", "email", etc.)
        repair_brazilian_plus: Repair known Brazilian numbers sent as
            +DDD9XXXXXXXX instead of +55DDD9XXXXXXXX.

    Returns:
        Normalized value (E.164 for phones, lowercase for email/Instagram).
        Empty string for empty/invalid input.
    """
    if not value:
        return ""

    value = value.strip()

    # Instagram: lowercase, strip @ (check before email — @ in handle triggers email path)
    if contact_type == "instagram":
        return value.lower().lstrip("@")

    # Email: lowercase passthrough
    if "@" in value:
        return value.lower()

    # Phone: extract digits
    has_plus = value.startswith("+")
    digits = re.sub(r"[^\d]", "", value)

    if not digits:
        return ""

    digits, has_plus = _prepare_phone_digits_for_parse(
        digits,
        has_plus=has_plus,
        default_region=default_region,
        repair_brazilian_plus=repair_brazilian_plus,
    )

    # Build parseable string
    raw = f"+{digits}" if has_plus else digits

    # Use phonenumbers if available
    if phonenumbers is not None:
        try:
            parsed = phonenumbers.parse(raw, default_region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            pass

    # Fallback: manual normalization (when phonenumbers not installed)
    return _fallback_normalize(digits, has_plus, default_region)


def _fallback_normalize(digits: str, has_plus: bool, default_region: str = "BR") -> str:
    """Fallback normalization without phonenumbers library."""
    if has_plus:
        # With explicit +, trust the caller but reject too-short numbers
        if len(digits) < 10:
            return ""
        return f"+{digits}"

    if default_region == "BR":
        # iOS autofill trunk prefix: 0+DDD+number → strip leading 0
        if digits.startswith("0") and len(digits) in (11, 12):
            digits = digits[1:]

        # Brazilian: 10-11 digits without country code (DDD + number)
        if len(digits) in (10, 11):
            return f"+55{digits}"

        # Already has country code
        if len(digits) >= 12 and digits.startswith("55"):
            return f"+{digits}"

        return ""

    # Non-BR regions without phonenumbers: require explicit + or reject
    return ""


def is_valid_phone(
    value: str,
    default_region: str = "BR",
    repair_brazilian_plus: bool = True,
) -> bool:
    """
    Validate phone number.

    Args:
        value: Phone number string.
        default_region: ISO country code.
        repair_brazilian_plus: Repair known Brazilian numbers sent as
            +DDD9XXXXXXXX instead of +55DDD9XXXXXXXX.

    Returns:
        True if the number is valid according to the numbering plan.
        When phonenumbers is not installed, falls back to a digit-length check (>= 10).
    """
    if not value or "@" in value:
        return False
    return bool(
        normalize_phone(
            value,
            default_region=default_region,
            repair_brazilian_plus=repair_brazilian_plus,
        )
    )
