"""
Base exception for all apps in the Django Shopman Suite.

Every app defines its own error class inheriting from BaseError:
    class CatalogError(BaseError): ...
    class StockError(BaseError): ...

All follow the same contract: (code, message, **data) + as_dict().
"""


class BaseError(Exception):
    """Base for all structured exceptions in the suite."""

    _default_messages: dict[str, str] = {}

    def __init__(self, code: str, message: str = "", **data):
        self.code = code
        self.message = message or self._default_messages.get(code, code)
        self.data = data
        super().__init__(f"[{code}] {self.message}")

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "data": self.data}
