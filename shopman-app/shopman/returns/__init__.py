from __future__ import annotations

__all__ = [
    "ReturnHandler",
    "ReturnResult",
    "ReturnService",
]


def __getattr__(name: str):
    if name == "ReturnHandler":
        from .handlers import ReturnHandler
        return ReturnHandler
    if name in ("ReturnResult", "ReturnService"):
        from .service import ReturnResult, ReturnService
        return {"ReturnResult": ReturnResult, "ReturnService": ReturnService}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
