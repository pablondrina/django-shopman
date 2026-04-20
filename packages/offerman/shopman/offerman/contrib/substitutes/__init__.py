"""
Substitutes module — find replacement products for unavailable SKUs.

Usage:
    from shopman.offerman.contrib.substitutes import find_substitutes

    subs = find_substitutes("SKU-001")
"""

__all__ = ["find_substitutes"]


def __getattr__(name: str):
    if name in __all__:
        from shopman.offerman.contrib.substitutes.substitutes import find_substitutes

        globals().update({"find_substitutes": find_substitutes})
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
