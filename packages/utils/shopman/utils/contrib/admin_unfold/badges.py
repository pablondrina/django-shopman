"""Unfold badge helpers for the Shopman suite."""

from django.utils.html import format_html

_COLOR_CLASSES = {
    "base": "bg-base-100 text-base-700 dark:bg-base-500/20 dark:text-base-200",
    "red": "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400",
    "green": "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400",
    "yellow": "bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400",
    "orange": "bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400",
    "blue": "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400",
}

_BASE = "inline-block font-semibold h-6 leading-6 px-2 rounded-default whitespace-nowrap"


def unfold_badge(text, color="base"):
    """Badge for status labels (uppercase, small text)."""
    classes = f"{_BASE} text-[11px] uppercase {_COLOR_CLASSES.get(color, _COLOR_CLASSES['base'])}"
    return format_html('<span class="{}">{}</span>', classes, text)


def unfold_badge_numeric(text, color="base"):
    """Badge for numeric values (small text, no uppercase transform)."""
    classes = f"{_BASE} text-[11px] {_COLOR_CLASSES.get(color, _COLOR_CLASSES['base'])}"
    return format_html('<span class="{}">{}</span>', classes, text)
