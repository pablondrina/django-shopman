"""Regression guards against cold-tone strings drifting back into templates.

These tests scan the storefront templates for strings that have explicit
omotenashi replacements. They don't check copy quality — they only fence the
known-bad spellings.

If a new template legitimately needs one of these strings (e.g. inside a code
comment or an aria-label), add it to the allow-list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATES_ROOT = Path(__file__).resolve().parents[1] / "templates" / "storefront"

# Substring → expected replacement key or doc pointer.
#
# Only include strings whose mere presence is a regression — i.e. strings that
# should not show up even as a `|default:""` fallback. Strings left as explicit
# Django `|default:"..."` fallbacks are *acceptable* during migration (they
# only render when `OmotenashiCopy` and the defaults dict are both unavailable),
# and intentionally NOT listed here to avoid false positives.
FORBIDDEN_ISOLATED = {
    "Muitas tentativas. Aguarde alguns minutos.": "KINTSUGI_RATE_LIMITED via omotenashi_copy",
    "Informações Nutricionais": "renomear para 'Alérgenos & info'",
    "PIX expirado</p>\n  <p class=\"text-sm mt-1\">O tempo para pagamento encerrou.": "PAYMENT_PIX_EXPIRED via omotenashi_copy + botão Gerar novo PIX",
}

# Files allowed to contain the strings (e.g. source of truth, tests, allowed
# legacy references kept on purpose).
ALLOW_FILES: set[str] = set()


def _iter_template_files():
    return list(TEMPLATES_ROOT.rglob("*.html"))


@pytest.mark.parametrize("forbidden,reason", sorted(FORBIDDEN_ISOLATED.items()))
def test_forbidden_isolated_strings_absent(forbidden: str, reason: str):
    """Cold strings with known replacements must not appear in storefront templates."""
    offenders: list[str] = []
    for f in _iter_template_files():
        if f.name in ALLOW_FILES:
            continue
        content = f.read_text(encoding="utf-8")
        if forbidden in content:
            offenders.append(str(f.relative_to(TEMPLATES_ROOT)))
    assert not offenders, (
        f"Found '{forbidden}' in {offenders}. Use {reason} instead."
    )
