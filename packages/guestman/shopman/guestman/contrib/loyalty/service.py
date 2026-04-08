"""Loyalty service — points, stamps, and tier management."""

import logging

from django.db import transaction

from shopman.guestman.contrib.loyalty.models import (
    LoyaltyAccount,
    LoyaltyTransaction,
    LoyaltyTier,
    TransactionType,
)
from shopman.guestman.exceptions import CustomersError
from shopman.guestman.models import Customer

logger = logging.getLogger(__name__)


from shopman.guestman.contrib.loyalty.conf import get_tier_thresholds


class LoyaltyService:
    """
    Service for loyalty program operations.

    Uses @classmethod for extensibility (consistent with other contrib services).
    All point mutations use transaction.atomic().
    """

    @classmethod
    def enroll(cls, customer_ref: str) -> LoyaltyAccount:
        """
        Enroll customer in the loyalty program.

        Idempotent — returns existing account if already enrolled.

        Args:
            customer_ref: Customer ref

        Returns:
            LoyaltyAccount (created or existing)

        Raises:
            Customer.DoesNotExist: If customer not found
        """
        customer = Customer.objects.get(ref=customer_ref, is_active=True)
        account, _ = LoyaltyAccount.objects.get_or_create(customer=customer)
        return account

    @classmethod
    def get_account(cls, customer_ref: str) -> LoyaltyAccount | None:
        """Get loyalty account for customer."""
        try:
            return LoyaltyAccount.objects.select_related("customer").get(
                customer__ref=customer_ref,
                customer__is_active=True,
            )
        except LoyaltyAccount.DoesNotExist:
            return None

    @classmethod
    def get_balance(cls, customer_ref: str) -> int:
        """Get current points balance. Returns 0 if not enrolled."""
        account = cls.get_account(customer_ref)
        return account.points_balance if account else 0

    @classmethod
    def earn_points(
        cls,
        customer_ref: str,
        points: int,
        description: str,
        reference: str = "",
        created_by: str = "",
    ) -> LoyaltyTransaction:
        """
        Award points to customer.

        Args:
            customer_ref: Customer ref
            points: Points to award (must be positive)
            description: Reason for the award
            reference: External reference (order:123)
            created_by: Who triggered the earn

        Returns:
            Created LoyaltyTransaction

        Raises:
            CustomersError: If not enrolled or points <= 0
        """
        if points <= 0:
            raise CustomersError("LOYALTY_INVALID_POINTS", message="Points must be positive")

        with transaction.atomic():
            account = cls._get_active_account_for_update(customer_ref)

            account.points_balance += points
            account.lifetime_points += points
            account.save(update_fields=["points_balance", "lifetime_points", "updated_at"])

            tx = LoyaltyTransaction.objects.create(
                account=account,
                transaction_type=TransactionType.EARN,
                points=points,
                balance_after=account.points_balance,
                description=description,
                reference=reference,
                created_by=created_by,
            )

            # Auto-upgrade tier
            cls._update_tier(account)

        return tx

    @classmethod
    def redeem_points(
        cls,
        customer_ref: str,
        points: int,
        description: str,
        reference: str = "",
        created_by: str = "",
    ) -> LoyaltyTransaction:
        """
        Redeem points from customer balance.

        Args:
            customer_ref: Customer ref
            points: Points to redeem (must be positive)
            description: What was redeemed
            reference: External reference
            created_by: Who triggered the redemption

        Returns:
            Created LoyaltyTransaction

        Raises:
            CustomersError: If not enrolled, insufficient balance, or points <= 0
        """
        if points <= 0:
            raise CustomersError("LOYALTY_INVALID_POINTS", message="Points must be positive")

        with transaction.atomic():
            account = cls._get_active_account_for_update(customer_ref)

            if account.points_balance < points:
                raise CustomersError(
                    "LOYALTY_INSUFFICIENT_POINTS",
                    available=account.points_balance,
                    requested=points,
                )

            account.points_balance -= points
            account.save(update_fields=["points_balance", "updated_at"])

            tx = LoyaltyTransaction.objects.create(
                account=account,
                transaction_type=TransactionType.REDEEM,
                points=-points,
                balance_after=account.points_balance,
                description=description,
                reference=reference,
                created_by=created_by,
            )

        return tx

    @classmethod
    def add_stamp(
        cls,
        customer_ref: str,
        description: str = "",
        reference: str = "",
    ) -> tuple[LoyaltyAccount, bool]:
        """
        Add a stamp to the customer's card.

        When stamps_current reaches stamps_target, the card is completed:
        stamps_current resets to 0, stamps_completed increments.

        Args:
            customer_ref: Customer ref
            description: Reason for the stamp
            reference: External reference

        Returns:
            Tuple of (LoyaltyAccount, card_completed: bool)

        Raises:
            CustomersError: If not enrolled
        """
        with transaction.atomic():
            account = cls._get_active_account_for_update(customer_ref)

            account.stamps_current += 1
            card_completed = False

            if account.stamps_current >= account.stamps_target:
                account.stamps_current = 0
                account.stamps_completed += 1
                card_completed = True

            account.save(update_fields=[
                "stamps_current",
                "stamps_completed",
                "updated_at",
            ])

            LoyaltyTransaction.objects.create(
                account=account,
                transaction_type=TransactionType.STAMP,
                points=1,
                balance_after=account.stamps_current,
                description=description or ("Cartela completa!" if card_completed else "Carimbo"),
                reference=reference,
            )

        return account, card_completed

    @classmethod
    def get_transactions(
        cls,
        customer_ref: str,
        limit: int = 50,
    ) -> list[LoyaltyTransaction]:
        """Get transaction history for a customer."""
        return list(
            LoyaltyTransaction.objects.filter(
                account__customer__ref=customer_ref,
                account__customer__is_active=True,
            )[:limit]
        )

    @classmethod
    def _get_active_account(cls, customer_ref: str) -> LoyaltyAccount:
        """Get active loyalty account or raise."""
        try:
            return LoyaltyAccount.objects.select_related("customer").get(
                customer__ref=customer_ref,
                customer__is_active=True,
                is_active=True,
            )
        except LoyaltyAccount.DoesNotExist:
            raise CustomersError("LOYALTY_NOT_ENROLLED", customer_ref=customer_ref)

    @classmethod
    def _get_active_account_for_update(cls, customer_ref: str) -> LoyaltyAccount:
        """
        Get active loyalty account with row-level lock for mutation.

        MUST be called inside transaction.atomic().
        Prevents lost-update race conditions on concurrent earn/redeem/stamp.
        """
        try:
            return (
                LoyaltyAccount.objects
                .select_for_update()
                .select_related("customer")
                .get(
                    customer__ref=customer_ref,
                    customer__is_active=True,
                    is_active=True,
                )
            )
        except LoyaltyAccount.DoesNotExist:
            raise CustomersError("LOYALTY_NOT_ENROLLED", customer_ref=customer_ref)

    @classmethod
    def _update_tier(cls, account: LoyaltyAccount) -> None:
        """Auto-upgrade tier based on lifetime points."""
        for threshold, tier in get_tier_thresholds():
            if account.lifetime_points >= threshold:
                if account.tier != tier:
                    account.tier = tier
                    account.save(update_fields=["tier", "updated_at"])
                break
