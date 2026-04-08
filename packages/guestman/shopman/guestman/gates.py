"""
Customers Gates - Validation rules.

G1: ContactPointUniqueness - (type, value) cannot exist in another Customer
G2: PrimaryInvariant - Max 1 primary per (customer, type)
G3: VerifiedTransition - Verification method must be allowed
G4: ProviderEventAuthenticity - Webhook is authentic (HMAC + timestamp)
G5: ReplayProtection - Event cannot be processed twice (persistent via DB)
G6: MergeSafety - Merge requires strong evidence
"""

import hashlib
import hmac
import time
from dataclasses import dataclass

from django.db import IntegrityError, transaction


class GateError(Exception):
    """Gate validation error."""

    def __init__(self, gate_name: str, message: str, details: dict | None = None):
        self.gate_name = gate_name
        self.message = message
        self.details = details or {}
        super().__init__(f"[{gate_name}] {message}")


@dataclass
class GateResult:
    """Result of a gate check."""

    passed: bool
    gate_name: str
    message: str = ""


# =============================================================================
# Gates
# =============================================================================


class Gates:
    """Customers validation gates."""

    # =========================================================================
    # G1: ContactPoint Uniqueness
    # =========================================================================

    @classmethod
    def contact_point_uniqueness(
        cls,
        contact_type: str,
        value_normalized: str,
        exclude_customer_id: str | None = None,
    ) -> GateResult:
        """
        G1: (type, value_normalized) cannot exist in another Customer.

        Args:
            contact_type: Type of contact (whatsapp, phone, email, etc.)
            value_normalized: Normalized contact value
            exclude_customer_id: Customer ID to exclude from check (for updates)

        Raises:
            GateError: If contact exists in another customer
        """
        from shopman.guestman.models import ContactPoint

        query = ContactPoint.objects.filter(
            type=contact_type,
            value_normalized=value_normalized,
        )

        if exclude_customer_id:
            query = query.exclude(customer_id=exclude_customer_id)

        existing = query.select_related("customer").first()
        if existing:
            raise GateError(
                "G1_ContactPointUniqueness",
                "Contact already exists in another customer.",
                {
                    "existing_customer_id": str(existing.customer_id),
                    "existing_customer_ref": existing.customer.ref,
                },
            )

        return GateResult(True, "G1_ContactPointUniqueness")

    @classmethod
    def check_contact_point_uniqueness(cls, *args, **kwargs) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.contact_point_uniqueness(*args, **kwargs)
            return True
        except GateError:
            return False

    # =========================================================================
    # G2: Primary Invariant
    # =========================================================================

    @classmethod
    def primary_invariant(cls, customer_id: str, contact_type: str) -> GateResult:
        """
        G2: Maximum 1 primary per (customer, type).

        Args:
            customer_id: Customer ID
            contact_type: Type of contact

        Raises:
            GateError: If multiple primaries exist
        """
        from shopman.guestman.models import ContactPoint

        count = ContactPoint.objects.filter(
            customer_id=customer_id,
            type=contact_type,
            is_primary=True,
        ).count()

        if count > 1:
            raise GateError(
                "G2_PrimaryInvariant",
                f"Multiple primaries for type '{contact_type}'.",
                {"count": count},
            )

        return GateResult(True, "G2_PrimaryInvariant")

    @classmethod
    def check_primary_invariant(cls, *args, **kwargs) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.primary_invariant(*args, **kwargs)
            return True
        except GateError:
            return False

    # =========================================================================
    # G3: Verified Transition
    # =========================================================================

    ALLOWED_VERIFICATION_METHODS = {
        "channel_asserted",
        "otp_whatsapp",
        "otp_sms",
        "email_link",
        "manual",
    }

    @classmethod
    def verified_transition(cls, method: str) -> GateResult:
        """
        G3: Verification method must be allowed.

        Args:
            method: Verification method

        Raises:
            GateError: If method is not allowed
        """
        if method not in cls.ALLOWED_VERIFICATION_METHODS:
            raise GateError(
                "G3_VerifiedTransition",
                f"Verification method not allowed: {method}",
                {"allowed": list(cls.ALLOWED_VERIFICATION_METHODS)},
            )

        return GateResult(True, "G3_VerifiedTransition")

    @classmethod
    def check_verified_transition(cls, method: str) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.verified_transition(method)
            return True
        except GateError:
            return False

    # =========================================================================
    # G4: Provider Event Authenticity (HMAC validation for webhooks)
    # =========================================================================

    @classmethod
    def provider_event_authenticity(
        cls,
        body: bytes,
        signature: str,
        secret: str,
        timestamp: int | None = None,
        max_age_seconds: int = 300,
    ) -> GateResult:
        """
        G4: Webhook is authentic (HMAC + timestamp validation).

        For Manychat webhooks, the signature is typically:
        - Header: X-Hub-Signature-256 or X-Manychat-Signature
        - Format: sha256=<hex_digest>

        Args:
            body: Raw request body (bytes)
            signature: Signature from header (with or without 'sha256=' prefix)
            secret: Webhook secret
            timestamp: Unix timestamp from header (optional)
            max_age_seconds: Maximum age of request (default 5 minutes)

        Raises:
            GateError: If signature is invalid or timestamp is too old
        """
        if not secret:
            # No secret configured = skip validation (dev mode)
            import logging

            logging.getLogger(__name__).warning(
                "G4_ProviderEventAuthenticity: webhook secret is empty — "
                "all payloads are accepted without signature validation. "
                "Set the webhook secret before deploying to production."
            )
            return GateResult(
                True, "G4_ProviderEventAuthenticity", "No secret configured (skipped)"
            )

        if not signature:
            raise GateError(
                "G4_ProviderEventAuthenticity",
                "Missing signature header.",
            )

        # Remove 'sha256=' prefix if present
        if signature.startswith("sha256="):
            signature = signature[7:]

        # Calculate expected signature
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature.lower(), expected.lower()):
            raise GateError(
                "G4_ProviderEventAuthenticity",
                "Invalid signature.",
            )

        # Validate timestamp if provided
        if timestamp:
            age = abs(int(time.time()) - timestamp)
            if age > max_age_seconds:
                raise GateError(
                    "G4_ProviderEventAuthenticity",
                    f"Timestamp too old ({age}s > {max_age_seconds}s).",
                    {"age_seconds": age},
                )

        return GateResult(True, "G4_ProviderEventAuthenticity")

    @classmethod
    def check_provider_event_authenticity(cls, *args, **kwargs) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.provider_event_authenticity(*args, **kwargs)
            return True
        except GateError:
            return False

    # =========================================================================
    # G5: Replay Protection (persistent via DB)
    # =========================================================================

    @classmethod
    def replay_protection(
        cls,
        nonce: str,
        provider: str = "manychat",
    ) -> GateResult:
        """
        G5: Event cannot be processed twice (persistent via DB).

        Uses ProcessedEvent model to store nonces persistently,
        safe for distributed/multi-server environments.

        Args:
            nonce: Unique event identifier (event_id, message_id, etc.)
            provider: Provider name for categorization

        Raises:
            GateError: If event was already processed (replay attack)
        """
        from shopman.guestman.models import ProcessedEvent

        if not nonce:
            raise GateError(
                "G5_ReplayProtection",
                "Nonce is required.",
            )

        # Try to create record - unique constraint will prevent duplicates
        try:
            with transaction.atomic():
                ProcessedEvent.objects.create(nonce=nonce, provider=provider)
        except IntegrityError:
            # IntegrityError means nonce already exists = replay
            # Check if it actually exists (could be other DB error)
            if ProcessedEvent.objects.filter(nonce=nonce).exists():
                raise GateError(
                    "G5_ReplayProtection",
                    "Replay detected: event already processed.",
                    {"nonce": nonce, "provider": provider},
                )
            # Re-raise if it's a different error
            raise

        return GateResult(True, "G5_ReplayProtection")

    @classmethod
    def check_replay_protection(cls, nonce: str, provider: str = "manychat") -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.replay_protection(nonce, provider)
            return True
        except GateError:
            return False

    @classmethod
    def is_replay(cls, nonce: str) -> bool:
        """Check if nonce was already processed (doesn't record)."""
        from shopman.guestman.models import ProcessedEvent
        return ProcessedEvent.objects.filter(nonce=nonce).exists()

    # =========================================================================
    # G6: Merge Safety
    # =========================================================================

    VALID_MERGE_EVIDENCE = {
        "staff_override",  # Staff explicitly approved
        "same_verified_phone",  # Both have same verified phone
        "same_verified_email",  # Both have same verified email
        "same_verified_whatsapp",  # Both have same verified WhatsApp
    }

    @classmethod
    def merge_safety(
        cls,
        source_id: str,
        target_id: str,
        evidence: dict | None = None,
    ) -> GateResult:
        """
        G6: Merge requires strong evidence.

        Args:
            source_id: Customer ID being merged (will be deactivated)
            target_id: Customer ID to merge into (will receive data)
            evidence: Dict with evidence keys (staff_override, same_verified_phone, etc.)

        Raises:
            GateError: If evidence is insufficient or IDs are invalid
        """
        if source_id == target_id:
            raise GateError(
                "G6_MergeSafety",
                "Cannot merge customer into itself.",
            )

        evidence = evidence or {}

        # Check if any valid evidence is provided
        has_valid_evidence = any(
            evidence.get(e) for e in cls.VALID_MERGE_EVIDENCE
        )

        if not has_valid_evidence:
            raise GateError(
                "G6_MergeSafety",
                "Insufficient evidence for merge.",
                {
                    "required_one_of": list(cls.VALID_MERGE_EVIDENCE),
                    "provided": list(evidence.keys()),
                },
            )

        return GateResult(True, "G6_MergeSafety")

    @classmethod
    def check_merge_safety(cls, *args, **kwargs) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.merge_safety(*args, **kwargs)
            return True
        except GateError:
            return False
