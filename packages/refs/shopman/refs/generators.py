"""
Value generators for shopman.refs.

Each generator produces a unique string value within a (ref_type, scope) pair.
Generators are looked up by slug from RefType.generator and called by attach()
when value=None.

Available generators:
    "sequence"       — SequenceGenerator: monotonic integer, formatted
    "date_sequence"  — DateSequenceGenerator: resets daily, scoped by date
    "alpha_numeric"  — AlphaNumericGenerator: 2-letter + 2-digit memorable code
    "short_uuid"     — ShortUUIDGenerator: 6-8 random alphanumeric chars
    "checksum"       — ChecksumGenerator: sequence + Luhn check digit
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import string
from datetime import date, datetime
from typing import Any

from django.db import transaction

from shopman.refs.models import RefSequence
from shopman.refs.registry import get_ref_type


def _scope_hash(sequence_name: str, scope: dict) -> str:
    """Deterministic hash for a (sequence_name, scope) pair."""
    canonical = json.dumps({"_seq": sequence_name, **scope}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def _increment_sequence(sequence_name: str, scope: dict) -> int:
    """Atomically increment and return the next value for the sequence."""
    scope_h = _scope_hash(sequence_name, scope)
    with transaction.atomic():
        seq, _ = RefSequence.objects.select_for_update().get_or_create(
            sequence_name=sequence_name,
            scope_hash=scope_h,
            defaults={"scope": scope, "last_value": 0},
        )
        seq.last_value += 1
        seq.save(update_fields=["last_value"])
        return seq.last_value


def _apply_format(generator_format: str, code: str, scope: dict) -> str:
    """
    Apply a generator_format string, substituting {code} and {date:...} tokens.

    Supported tokens:
        {code}          — raw generator output (also matches {code:N} length hints)
        {value}         — alias for {code}
        {date:%y%m%d}   — scope["business_date"] formatted with strftime
        {channel_ref}   — scope["channel_ref"] (and any other scope key)
    """
    if generator_format in ("{value}", "{code}"):
        return code

    result = generator_format

    # {code} / {code:N} substitution ({code:N} used by ShortUUID as a length hint)
    result = re.sub(r"\{code(?::\d+)?\}", code, result)
    result = re.sub(r"\{value(?::\d+)?\}", code, result)

    # {date:FORMAT} substitution — scope["business_date"] expected as "YYYY-MM-DD" or date obj
    for match in re.finditer(r"\{date:([^}]+)\}", result):
        fmt = match.group(1)
        raw_date = scope.get("business_date")
        if raw_date is None:
            raw_date = date.today()
        if isinstance(raw_date, str):
            raw_date = date.fromisoformat(raw_date)
        elif isinstance(raw_date, datetime):
            raw_date = raw_date.date()
        result = result.replace(match.group(0), raw_date.strftime(fmt))

    # simple scope key substitution: {channel_ref}, {store_id}, etc.
    for key, val in scope.items():
        result = result.replace(f"{{{key}}}", str(val))

    return result


class SequenceGenerator:
    """
    Monotonic per-scope integer sequence, formatted via generator_format.

    Suitable for: simple ticket numbers like "T-001", "T-042".
    generator_format default: "{value}" → raw integer as string.
    Custom example: "T-{value:03d}" → "T-001".
    """

    slug = "sequence"

    def next(self, ref_type: Any, scope: dict) -> str:
        n = _increment_sequence(ref_type.slug, scope)
        fmt = ref_type.generator_format
        if fmt in ("{value}", "{code}"):
            return str(n)
        # Support numeric format specs like {value:03d}
        match = re.search(r"\{(?:value|code)(?::([^}]*))?\}", fmt)
        if match:
            spec = match.group(1) or ""
            formatted_n = format(n, spec) if spec else str(n)
            result = re.sub(r"\{(?:value|code)(?::[^}]*)?\}", formatted_n, fmt)
            return result
        return _apply_format(fmt, str(n), scope)


class DateSequenceGenerator:
    """
    Per-scope sequence that resets each business day.

    Scope MUST include "business_date" (YYYY-MM-DD) — the date becomes part of
    the sequence_name so each day starts from 1.
    """

    slug = "date_sequence"

    def next(self, ref_type: Any, scope: dict) -> str:
        business_date = scope.get("business_date", str(date.today()))
        if isinstance(business_date, (date, datetime)):
            business_date = business_date.isoformat()[:10]
        seq_name = f"{ref_type.slug}:{business_date}"
        n = _increment_sequence(seq_name, scope)
        fmt = ref_type.generator_format
        if fmt in ("{value}", "{code}"):
            return str(n)
        match = re.search(r"\{(?:value|code)(?::([^}]*))?\}", fmt)
        if match:
            spec = match.group(1) or ""
            formatted_n = format(n, spec) if spec else str(n)
            result = re.sub(r"\{(?:value|code)(?::[^}]*)?\}", formatted_n, fmt)
            return _apply_format(result, formatted_n, scope)
        return _apply_format(fmt, str(n), scope)


class AlphaNumericGenerator:
    """
    Generates memorable 4-char codes: 2 uppercase letters + 2 digits.

    Alphabet excludes I and O (visual confusion): 24 letters × 24 × 10 × 10 = 57,600 per scope.
    Internally sequential (uses RefSequence), mapped to a readable code.

    Example output: "AZ19", "BK03", "MN42"
    Typical final value with generator_format: "POS-260420-AZ19"
    """

    slug = "alpha_numeric"
    LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # 24 chars, no I/O
    DIGITS = "0123456789"

    def next(self, ref_type: Any, scope: dict) -> str:
        seq = _increment_sequence(ref_type.slug, scope)
        code = self._encode(seq - 1)
        return _apply_format(ref_type.generator_format, code, scope)

    def _encode(self, n: int) -> str:
        L, D = len(self.LETTERS), len(self.DIGITS)
        d2 = n % D
        n //= D
        d1 = n % D
        n //= D
        l2 = n % L
        n //= L
        l1 = n % L
        return self.LETTERS[l1] + self.LETTERS[l2] + self.DIGITS[d1] + self.DIGITS[d2]


class ShortUUIDGenerator:
    """
    6-8 random alphanumeric characters (uppercase + digits, no I/O).

    Non-sequential; suitable for external-facing tokens where unpredictability matters.
    Length defaults to 8 chars. Override via generator_format="{code:6}" for 6 chars.
    """

    slug = "short_uuid"
    ALPHABET = string.ascii_uppercase.replace("I", "").replace("O", "") + string.digits
    DEFAULT_LENGTH = 8

    def next(self, ref_type: Any, scope: dict) -> str:
        length = self.DEFAULT_LENGTH
        fmt = ref_type.generator_format
        m = re.search(r"\{(?:code|value):(\d+)\}", fmt)
        if m:
            length = int(m.group(1))
        code = "".join(random.choices(self.ALPHABET, k=length))
        return _apply_format(fmt, code, scope)


class ChecksumGenerator:
    """
    Sequential integer with a Luhn-style check digit appended.

    Produces values like "14" (seq=1, check=4). Useful for balcão codes
    where mistyping should be caught immediately.
    """

    slug = "checksum"

    def next(self, ref_type: Any, scope: dict) -> str:
        n = _increment_sequence(ref_type.slug, scope)
        code = self._with_check_digit(n)
        return _apply_format(ref_type.generator_format, code, scope)

    @staticmethod
    def _luhn_check_digit(n: int) -> int:
        """Return a single check digit (0–9) for the given integer."""
        digits = [int(d) for d in str(n)]
        total = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2 == 0:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        return (10 - (total % 10)) % 10

    def _with_check_digit(self, n: int) -> str:
        check = self._luhn_check_digit(n)
        return f"{n}{check}"


# ── Registry ─────────────────────────────────────────────────────────────────

_GENERATORS: dict[str, Any] = {
    g.slug: g()
    for g in (
        SequenceGenerator,
        DateSequenceGenerator,
        AlphaNumericGenerator,
        ShortUUIDGenerator,
        ChecksumGenerator,
    )
}


def generate_value(ref_type_slug: str, scope: dict | None = None) -> str:
    """
    Generate the next value for the given RefType slug within scope.

    Looks up the RefType from the global registry, finds its generator,
    and returns the formatted generated value.

    Raises:
        LookupError: If ref_type_slug is not registered.
        LookupError: If the RefType has no generator configured.
    """
    if scope is None:
        scope = {}
    ref_type = get_ref_type(ref_type_slug)
    if ref_type is None:
        raise LookupError(f"RefType '{ref_type_slug}' is not registered")
    if not ref_type.generator:
        raise LookupError(f"RefType '{ref_type_slug}' has no generator configured")
    generator = _GENERATORS.get(ref_type.generator)
    if generator is None:
        raise LookupError(f"Generator '{ref_type.generator}' is not available")
    return generator.next(ref_type, scope)
