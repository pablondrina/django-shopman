from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class GatingCustomerInfo:
    """Minimal customer info needed by Gating."""
    uuid: UUID
    name: str
    phone: str | None
    email: str | None
    is_active: bool


@runtime_checkable
class CustomerResolver(Protocol):
    """Resolves customer for authentication flows."""

    def get_by_phone(self, phone: str) -> GatingCustomerInfo | None: ...

    def get_by_email(self, email: str) -> GatingCustomerInfo | None: ...

    def get_by_uuid(self, uuid: UUID) -> GatingCustomerInfo | None: ...

    def create_for_phone(self, phone: str) -> GatingCustomerInfo: ...
