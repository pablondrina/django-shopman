"""Customers exceptions."""

from shopman.utils.exceptions import BaseError


class CustomersError(BaseError):
    """
    Structured exception for customer operations.

    Inherits from shopman.utils.BaseError for suite-wide consistency.

    Usage:
        try:
            customer = customer_service.get("CUST-001")
        except CustomersError as e:
            if e.code == "CUSTOMER_NOT_FOUND":
                handle_not_found()
    """

    _default_messages = {
        "CUSTOMER_NOT_FOUND": "Customer not found",
        "ADDRESS_NOT_FOUND": "Address not found",
        "DUPLICATE_CONTACT": "Contact point already exists",
        "INVALID_PHONE": "Invalid phone number",
        "MERGE_DENIED": "Customer merge denied",
        "CONSENT_NOT_FOUND": "Communication consent not found",
        "LOYALTY_NOT_ENROLLED": "Customer not enrolled in loyalty program",
        "LOYALTY_INSUFFICIENT_POINTS": "Insufficient points for redemption",
    }
