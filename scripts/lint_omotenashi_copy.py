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
    Default: shopman/shop/templates/storefront/
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Heuristic patterns ─────────────────────────────────────────────────

# Lines that are "copy-ok" exemptions
_COPY_OK = re.compile(r"\{#\s*copy-ok\s*:", re.IGNORECASE)

# Attribute values we skip entirely (they contain CSS classes, URLs, etc.)
_ATTR_VALUE = re.compile(
    r"""(?:class|href|src|action|data-[\w-]+|id|name|value|type|for|aria-[\w-]+|hx-[\w-]+|x-[\w.:-]+|@[\w.:-]+|style)\s*=\s*["'][^"']*["']""",
    re.IGNORECASE,
)

# Django / Jinja template tags and variables — remove them
_DJANGO_TAG = re.compile(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", re.DOTALL)

# HTML tags — remove them
_HTML_TAG = re.compile(r"<[^>]+>")

# Punctuation that signals this might be user-facing copy
_COPY_PUNCT = re.compile(r"[.!?]")

# Minimum word count threshold
MIN_WORDS = 4


def _candidate_text(line: str) -> str:
    """Strip template tags, HTML tags, and attribute values, returning bare text."""
    cleaned = _ATTR_VALUE.sub(" ", line)
    cleaned = _DJANGO_TAG.sub(" ", cleaned)
    cleaned = _HTML_TAG.sub(" ", cleaned)
    return cleaned.strip()


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
    prev_line = ""

    for i, raw in enumerate(lines, start=1):
        line = raw.strip()

        # Track block-level exclusion zones
        if "<script" in raw.lower():
            in_script = True
        if "</script>" in raw.lower():
            in_script = False
        if "<style" in raw.lower():
            in_style = True
        if "</style>" in raw.lower():
            in_style = False
        if "<!--" in raw:
            in_comment = True
        if "-->" in raw:
            in_comment = False
        if "{% comment %}" in raw:
            in_comment = True
        if "{% endcomment %}" in raw:
            in_comment = False

        if in_script or in_style or in_comment:
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

        text = _candidate_text(line)
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
    args = sys.argv[1:]
    error_mode = "--error" in args
    path_args = [a for a in args if not a.startswith("--")]

    if path_args:
        targets = [Path(a) for a in path_args]
    else:
        targets = [Path("shopman/shop/templates/storefront")]

    results = scan(targets)

    if not results:
        print("lint_omotenashi_copy: OK — no hardcoded copy candidates found.")
        return 0

    total = sum(len(v) for v in results.values())
    label = "ERROR" if error_mode else "WARNING"
    print(
        f"lint_omotenashi_copy: {label} — {total} candidate(s) across {len(results)} file(s).\n"
        f"  Wrap in {{% omotenashi KEY %}} or add {{# copy-ok: <reason> #}} to suppress.\n"
    )
    for path, hits in sorted(results.items()):
        print(f"  {path}")
        for lineno, text in hits:
            print(f"    line {lineno}: {text[:120]}")
        print()

    return 1 if error_mode else 0


if __name__ == "__main__":
    sys.exit(main())
