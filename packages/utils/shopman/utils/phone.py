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


def normalize_phone(
    value: str,
    default_region: str = "BR",
    contact_type: str | None = None,
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

    # Manychat bug detection: +DDD9XXXXXXXX without 55 prefix
    if has_plus and _is_phone_brazilian(digits):
        digits = f"55{digits}"
        has_plus = True

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
        # Brazilian: 10-11 digits without country code (DDD + number)
        if len(digits) in (10, 11):
            return f"+55{digits}"

        # Already has country code
        if len(digits) >= 12 and digits.startswith("55"):
            return f"+{digits}"

        return ""

    # Non-BR regions without phonenumbers: require explicit + or reject
    return ""


def is_valid_phone(value: str, default_region: str = "BR") -> bool:
    """
    Validate phone number.

    Args:
        value: Phone number string.
        default_region: ISO country code.

    Returns:
        True if the number is valid according to the numbering plan.
        When phonenumbers is not installed, falls back to a digit-length check (>= 10).
    """
    if not value or "@" in value:
        return False

    if phonenumbers is None:
        # Without phonenumbers, we can only do basic length checks
        digits = re.sub(r"[^\d]", "", value)
        return len(digits) >= 10

    try:
        has_plus = value.strip().startswith("+")
        digits = re.sub(r"[^\d]", "", value)

        # Apply Manychat fix before validation
        if has_plus and _is_phone_brazilian(digits):
            digits = f"55{digits}"

        raw = f"+{digits}" if has_plus else digits
        parsed = phonenumbers.parse(raw, default_region)
        return phonenumbers.is_valid_number(parsed)
    except phonenumbers.NumberParseException:
        return False
