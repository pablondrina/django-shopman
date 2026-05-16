"""Lint omotenashi copy — detect user-facing strings not wrapped in {% omotenashi %}.

Heuristics (imperfect, sufficient):
- Lines whose text content has > 3 words and typical copy punctuation (. ! ?)
- Not inside <script>, <style>, <!-- -->, {% comment %} ... {% endcomment %}
- Not inside class="...", data-*="...", href="...", src="..." attributes
- Excepted by {# copy-ok: <reason> #} on the same or previous line

Usage:
    python scripts/lint_omotenashi_copy.py [--error] [path ...]

Flags:
    --error   exit 1 if candidates found (CI error mode; default: warning, exit 0)

Paths:
    Directories are scanned recursively for *.html files.
    Default: shopman/storefront/templates/storefront/
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── Heuristic patterns ─────────────────────────────────────────────────

# Lines that are "copy-ok" exemptions
_COPY_OK = re.compile(r"\{#\s*copy-ok\s*:", re.IGNORECASE)

# Django / Jinja template tags and variables — remove them
_DJANGO_TAG = re.compile(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", re.DOTALL)

# HTML tags — remove them
_HTML_TAG = re.compile(r"<[^>]+>")

# Punctuation that signals this might be user-facing copy
_COPY_PUNCT = re.compile(r"[.!?]")

# Minimum word count threshold
MIN_WORDS = 4

CRITICAL_TEMPLATE_PATHS = [
    "shopman/storefront/templates/storefront/checkout.html",
    "shopman/storefront/templates/storefront/login.html",
    "shopman/storefront/templates/storefront/payment.html",
    "shopman/storefront/templates/storefront/order_tracking.html",
    "shopman/storefront/templates/storefront/order_confirmation.html",
    "shopman/storefront/templates/storefront/welcome.html",
    "shopman/storefront/templates/storefront/_payment_card.html",
    "shopman/storefront/templates/storefront/_payment_pix.html",
    "shopman/storefront/templates/storefront/partials/auth_confirmed.html",
    "shopman/storefront/templates/storefront/partials/auth_trusted_greeting.html",
    "shopman/storefront/templates/storefront/partials/auth_verify_code.html",
    "shopman/storefront/templates/storefront/partials/checkout_order_summary.html",
    "shopman/storefront/templates/storefront/partials/rate_limited.html",
    "shopman/storefront/templates/storefront/partials/reorder_conflict_modal.html",
    "shopman/storefront/templates/storefront/partials/profile_form.html",
]


def _visible_text_outside_tags(
    line: str,
    *,
    in_tag: bool,
    tag_quote: str | None,
) -> tuple[str, bool, str | None]:
    """Return literal text outside HTML tags and the updated tag state.

    This intentionally tracks multi-line start tags. Alpine/HTMX expressions,
    Tailwind classes, SVG paths, ARIA labels, and JS snippets usually live
    inside those tags and are not visible text nodes.
    """
    chunks: list[str] = []
    i = 0
    while i < len(line):
        char = line[i]
        if in_tag:
            if tag_quote:
                if char == tag_quote:
                    tag_quote = None
            elif char in ("'", '"'):
                tag_quote = char
            elif char == ">":
                in_tag = False
            i += 1
            continue
        if char == "<":
            in_tag = True
            tag_quote = None
            i += 1
            continue
        chunks.append(char)
        i += 1
    return "".join(chunks), in_tag, tag_quote


def _candidate_text(
    line: str,
    *,
    in_tag: bool,
    tag_quote: str | None,
) -> tuple[str, bool, str | None]:
    """Strip template syntax and HTML tags, returning bare visible text."""
    visible, in_tag, tag_quote = _visible_text_outside_tags(
        line,
        in_tag=in_tag,
        tag_quote=tag_quote,
    )
    cleaned = _DJANGO_TAG.sub(" ", visible)
    cleaned = _HTML_TAG.sub(" ", cleaned)
    return cleaned.strip(), in_tag, tag_quote


def _looks_like_copy(text: str) -> bool:
    """Return True if *text* looks like a user-facing string worth linting."""
    words = text.split()
    if len(words) < MIN_WORDS:
        return False
    return bool(_COPY_PUNCT.search(text))


def lint_file(path: Path) -> list[tuple[int, str]]:
    """Return a list of (lineno, stripped_line) copy candidates in *path*."""
    lines = path.read_text(encoding="utf-8").splitlines()
    findings: list[tuple[int, str]] = []

    in_script = False
    in_style = False
    in_comment = False
    in_tag = False
    tag_quote: str | None = None
    prev_line = ""

    for i, raw in enumerate(lines, start=1):
        line = raw.strip()
        raw_lower = raw.lower()

        # Track block-level exclusion zones
        if "<script" in raw_lower:
            in_script = True
        if in_script:
            if "</script>" in raw_lower:
                in_script = False
            prev_line = line
            continue
        if "</script>" in raw_lower:
            in_script = False

        if "<style" in raw_lower:
            in_style = True
        if in_style:
            if "</style>" in raw_lower:
                in_style = False
            prev_line = line
            continue
        if "</style>" in raw_lower:
            in_style = False

        if "<!--" in raw:
            in_comment = True
        if in_comment:
            if "-->" in raw:
                in_comment = False
            prev_line = line
            continue

        if "{% comment %}" in raw:
            in_comment = True
        if in_comment:
            if "{% endcomment %}" in raw:
                in_comment = False
            prev_line = line
            continue

        # Skip lines with a copy-ok exemption on this or the previous line
        if _COPY_OK.search(line) or _COPY_OK.search(prev_line):
            prev_line = line
            continue

        # Skip lines that are already using {% omotenashi %}
        if "omotenashi" in line:
            prev_line = line
            continue

        text, in_tag, tag_quote = _candidate_text(
            line,
            in_tag=in_tag,
            tag_quote=tag_quote,
        )
        if _looks_like_copy(text):
            findings.append((i, raw.rstrip()))

        prev_line = line

    return findings


def scan(paths: list[Path]) -> dict[Path, list[tuple[int, str]]]:
    """Scan all *.html files under *paths*, return findings per file."""
    results: dict[Path, list[tuple[int, str]]] = {}
    for p in paths:
        files = sorted(p.rglob("*.html")) if p.is_dir() else [p]
        for f in files:
            hits = lint_file(f)
            if hits:
                results[f] = hits
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detect visible storefront copy that is not wrapped in "
            "{% omotenashi %}."
        )
    )
    parser.add_argument(
        "--error",
        action="store_true",
        help="Exit 1 when candidates are found.",
    )
    parser.add_argument(
        "--critical",
        action="store_true",
        help="Scan checkout, payment, tracking, auth, and reorder surfaces used as the CI gate.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="HTML files or directories to scan.",
    )
    args = parser.parse_args()
    if args.critical and args.paths:
        parser.error("--critical cannot be combined with explicit paths")
    if args.critical:
        targets = [Path(p) for p in CRITICAL_TEMPLATE_PATHS]
    elif args.paths:
        targets = args.paths
    else:
        targets = [Path("shopman/storefront/templates/storefront")]

    results = scan(targets)

    if not results:
        print("lint_omotenashi_copy: OK — no hardcoded copy candidates found.")
        return 0

    total = sum(len(v) for v in results.values())
    label = "ERROR" if args.error else "WARNING"
    print(
        f"lint_omotenashi_copy: {label} — {total} candidate(s) across {len(results)} file(s).\n"
        f"  Wrap in {{% omotenashi KEY %}} or add {{# copy-ok: <reason> #}} to suppress.\n"
    )
    for path, hits in sorted(results.items()):
        print(f"  {path}")
        for lineno, text in hits:
            print(f"    line {lineno}: {text[:120]}")
        print()

    return 1 if args.error else 0


if __name__ == "__main__":
    sys.exit(main())
