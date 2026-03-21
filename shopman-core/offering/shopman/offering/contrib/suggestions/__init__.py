"""
Suggestions module - find alternative products.

Usage:
    from shopman.offering.contrib.suggestions import find_alternatives, find_similar

    alternatives = find_alternatives("SKU-001")
    similar = find_similar("SKU-001")
"""

__all__ = ["find_alternatives", "find_similar"]


def __getattr__(name: str):
    if name in __all__:
        from shopman.offering.contrib.suggestions.suggestions import find_alternatives, find_similar

        globals().update({"find_alternatives": find_alternatives, "find_similar": find_similar})
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
