"""
Integration test: Customers <-> Auth.

Tests the flow: customer user -> login.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class TestCustomersAuthIntegration(TestCase):
    """Integration between Customers and Auth."""

    def setUp(self):
        from shopman.customers.models import ContactPoint, Customer

        self.customer = Customer.objects.create(
            ref="GD-INT-001",
            first_name="Guest",
            last_name="Door",
            phone="+5541999998888",
        )

        self.contact = ContactPoint.objects.create(
            customer=self.customer,
            type="whatsapp",
            value_normalized="+5541999998888",
            value_display="(41) 99999-8888",
            is_primary=True,
            is_verified=True,
            verification_method="otp_whatsapp",
        )

    def test_customer_user_uses_customer_uuid(self):
        """CustomerUser references customer by UUID, not FK."""
        from shopman.auth.models import CustomerUser

        user = User.objects.create_user(
            username="gd_test_user",
            password="testpass",
        )

        link = CustomerUser.objects.create(
            user=user,
            customer_id=self.customer.uuid,
        )

        # UUID match
        assert link.customer_id == self.customer.uuid
        # Decoupled: no FK relationship
        assert not hasattr(link, "customer")

    def test_customer_user_one_to_one(self):
        """Each user has at most one CustomerUser."""
        from django.db import IntegrityError

        from shopman.auth.models import CustomerUser

        user = User.objects.create_user(username="gd_unique_user")
        CustomerUser.objects.create(user=user, customer_id=self.customer.uuid)

        # Cannot create second link for same user
        from shopman.customers.models import Customer

        other_customer = Customer.objects.create(
            ref="GD-INT-002",
            first_name="Other",
        )

        with self.assertRaises(IntegrityError):
            CustomerUser.objects.create(user=user, customer_id=other_customer.uuid)

    def test_customer_uuid_unique_in_customer_user(self):
        """Each customer_id has at most one CustomerUser."""
        from django.db import IntegrityError

        from shopman.auth.models import CustomerUser

        user1 = User.objects.create_user(username="gd_user_1")
        user2 = User.objects.create_user(username="gd_user_2")

        CustomerUser.objects.create(user=user1, customer_id=self.customer.uuid)

        with self.assertRaises(IntegrityError):
            CustomerUser.objects.create(user=user2, customer_id=self.customer.uuid)

    def test_verified_contact_for_login(self):
        """Only verified contacts should be used for authentication."""
        from shopman.customers.models import ContactPoint

        # The verified contact
        verified = ContactPoint.objects.filter(
            customer=self.customer,
            is_verified=True,
            type="whatsapp",
        ).first()

        assert verified is not None
        assert verified.value_normalized == "+5541999998888"
        assert verified.verification_method == "otp_whatsapp"

    def test_verification_code_links_to_customer_uuid(self):
        """VerificationCode stores customer_id after verification."""
        from shopman.auth.models import VerificationCode

        code = VerificationCode.objects.create(
            target_value="+5541999998888",
            purpose="login",
            status="verified",
            customer_id=self.customer.uuid,
        )

        assert code.customer_id == self.customer.uuid
