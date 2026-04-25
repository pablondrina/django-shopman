"""Customer model (CORE - agnóstico).

Data architecture:
    Customer.phone / Customer.email
        Quick-access cache for the primary contact. Used by services for fast
        lookups (get_by_phone, get_by_email) without joining ContactPoint.
        Updated automatically via _sync_contact_points() on save().

    ContactPoint
        Source of truth for all contact channels (WhatsApp, phone, email, Instagram).
        Carries verification status, verification method, and is_primary flag.
        One primary per (customer, type). Globally unique (type, value_normalized).

    CustomerIdentifier (contrib)
        Deduplication lookup table. Maps external identifiers (Manychat, Instagram
        handle, etc.) to customers. Used by IdentifierService.find_by_identifier()
        for cross-channel customer resolution.
"""

import uuid as uuid_lib

from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.utils.refs import RefField


class CustomerType(models.TextChoices):
    INDIVIDUAL = "individual", _("Pessoa Física")
    BUSINESS = "business", _("Pessoa Jurídica")


class Customer(models.Model):
    """
    Registered customer.

    CORE: Essential and channel-agnostic data only.
    Channel-specific data (Manychat, etc.) goes in contrib/identifiers and contrib/manychat.

    phone/email fields are quick-access cache. ContactPoint is source of truth.
    See module docstring for full data architecture.
    """

    # Identification (ref + uuid pattern - see spec 000 section 12.2)
    ref = RefField(
        ref_type="CUSTOMER",
        verbose_name=_("referência"),
        max_length=50,
        unique=True,
        db_index=False,
        help_text=_("Referência única do cliente (ex: CLI-001)"),
    )
    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True)

    # Basic data (first_name + last_name - see spec 000 section 12.5)
    first_name = models.CharField(_("nome"), max_length=100)
    last_name = models.CharField(_("sobrenome"), max_length=100, blank=True)
    customer_type = models.CharField(
        _("tipo"),
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.INDIVIDUAL,
    )

    # Document (optional)
    document = models.CharField(
        _("documento"),
        max_length=20,
        blank=True,
        db_index=True,
        help_text=_("CPF ou CNPJ (apenas números)"),
    )

    # Birthday
    birthday = models.DateField(_("data de nascimento"), null=True, blank=True)

    # Primary contact
    email = models.EmailField(_("email"), blank=True, db_index=True)
    phone = models.CharField(_("telefone"), max_length=20, blank=True, db_index=True)

    # Segmentation
    group = models.ForeignKey(
        "guestman.CustomerGroup",
        on_delete=models.PROTECT,
        related_name="customers",
        null=True,
        blank=True,
        verbose_name=_("grupo"),
    )

    # Status (is_active is appropriate - see spec 000 section 12.3)
    is_active = models.BooleanField(_("ativo"), default=True, db_index=True)

    # Internal notes (not visible to customer)
    notes = models.TextField(_("observações"), blank=True)

    # Extension point (see spec 000 section 12.4)
    metadata = models.JSONField(
        _("metadados"), default=dict, blank=True,
        help_text=_('Metadados do cliente. Ex: {"preferences": "sem lactose", "birthday": "1990-05-15"}'),
    )

    # Audit (B.I.)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)
    created_by = models.CharField(_("criado por"), max_length=255, blank=True)
    source_system = models.CharField(_("sistema de origem"), max_length=100, blank=True)

    class Meta:
        verbose_name = _("cliente")
        verbose_name_plural = _("clientes")
        ordering = ["first_name", "last_name"]
        indexes = [
            models.Index(fields=["ref"]),
            models.Index(fields=["document"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["email"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                name="unique_customer_phone",
                condition=~models.Q(phone=""),
            ),
        ]

    @classmethod
    def generate_ref(cls) -> str:
        """
        Generate a unique customer ref.

        Canonical ref format: CUST-{12 hex chars from uuid4}.
        This is the SINGLE point of ref generation — API views, IdentifierService,
        and any other caller must delegate here.
        """
        return f"CUST-{uuid_lib.uuid4().hex[:12].upper()}"

    def __str__(self):
        return f"{self.name} ({self.ref})"

    @property
    def name(self) -> str:
        """Full name (first + last)."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def listing_ref(self) -> str | None:
        """Applicable listing code (from customer group)."""
        if self.group and self.group.listing_ref:
            return self.group.listing_ref
        return None

    @property
    def default_address(self):
        """Customer's default address."""
        return self.addresses.filter(is_default=True).first()

    def save(self, *args, **kwargs):
        # Normalize phone using centralized function
        if self.phone:
            from shopman.guestman.utils import normalize_phone

            self.phone = normalize_phone(self.phone)

        # Normalize email (lowercase)
        if self.email:
            self.email = self.email.lower().strip()

        # Set default group (select_for_update prevents race between concurrent creates)
        if not self.group_id:
            from django.db import transaction
            from shopman.guestman.models import CustomerGroup

            with transaction.atomic():
                default_group = (
                    CustomerGroup.objects.select_for_update()
                    .filter(is_default=True)
                    .first()
                )
                if default_group:
                    self.group = default_group

        super().save(*args, **kwargs)

        # Sync cache → ContactPoint (source of truth)
        self._sync_contact_points()

    def _sync_contact_points(self):
        """
        Ensure Customer.phone/email are mirrored as ContactPoints.

        Creates or updates the primary ContactPoint for phone and email
        when Customer.phone or Customer.email change. ContactPoint remains
        source of truth for verification status.

        Called automatically on save(). Safe to call multiple times.
        """
        from shopman.guestman.models.contact_point import ContactPoint

        if not self.pk:
            return

        if self.phone:
            cp, created = ContactPoint.objects.get_or_create(
                customer=self,
                type=ContactPoint.Type.PHONE,
                value_normalized=self.phone,
                defaults={"is_primary": True},
            )
            if created:
                # Ensure only one primary for this type
                ContactPoint.objects.filter(
                    customer=self,
                    type=ContactPoint.Type.PHONE,
                    is_primary=True,
                ).exclude(pk=cp.pk).update(is_primary=False)

        if self.email:
            cp, created = ContactPoint.objects.get_or_create(
                customer=self,
                type=ContactPoint.Type.EMAIL,
                value_normalized=self.email,
                defaults={"is_primary": True},
            )
            if created:
                ContactPoint.objects.filter(
                    customer=self,
                    type=ContactPoint.Type.EMAIL,
                    is_primary=True,
                ).exclude(pk=cp.pk).update(is_primary=False)
