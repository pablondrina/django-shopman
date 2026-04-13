from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class AuthCustomerInfo:
    """Minimal customer info needed by Auth."""
    uuid: UUID
    name: str
    phone: str | None
    email: str | None
    is_active: bool


@runtime_checkable
class CustomerResolver(Protocol):
    """Resolves customer for authentication flows."""

    def get_by_phone(self, phone: str) -> AuthCustomerInfo | None: ...

    def get_by_email(self, email: str) -> AuthCustomerInfo | None: ...

    def get_by_uuid(self, uuid: UUID) -> AuthCustomerInfo | None: ...

    def create_for_phone(self, phone: str) -> AuthCustomerInfo: ...

    def create_for_email(self, email: str) -> AuthCustomerInfo: ...
