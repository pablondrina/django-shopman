"""
User bridge — get or create Django User for a Customer.

Extracted from AccessLinkService for reuse by PhoneOTPBackend and other
authentication paths.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError

from ..models import CustomerUser
from ..protocols.customer import AuthCustomerInfo

logger = logging.getLogger("shopman.doorman.user_bridge")
User = get_user_model()


def get_or_create_user_for_customer(customer: AuthCustomerInfo) -> tuple:
    """
    Get or create a Django User for a Customer.

    Handles concurrent creation via IntegrityError retry.

    Args:
        customer: Customer info from resolver.

    Returns:
        (User, created: bool) tuple.
    """
    # Check existing link
    try:
        link = CustomerUser.objects.select_related("user").get(
            customer_id=customer.uuid,
        )
        return link.user, False
    except CustomerUser.DoesNotExist:
        pass

    # Create User
    username = f"customer_{str(customer.uuid).replace('-', '')[:12]}"
    user = User.objects.create_user(username=username)

    # Set name from customer
    if customer.name:
        parts = customer.name.split(" ", 1)
        user.first_name = parts[0]
        if len(parts) > 1:
            user.last_name = parts[1]
        user.save(update_fields=["first_name", "last_name"])

    # Create link — retry on concurrent creation
    try:
        CustomerUser.objects.create(user=user, customer_id=customer.uuid)
    except IntegrityError:
        # Another request already created the link; use that one
        user.delete()
        link = CustomerUser.objects.select_related("user").get(
            customer_id=customer.uuid,
        )
        return link.user, False

    logger.info(
        "User created for customer",
        extra={"customer_id": str(customer.uuid), "user_id": user.id},
    )

    return user, True
