"""
IdentityLink model - Links Customer (Customers) to User (Django auth).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class IdentityLink(models.Model):
    """
    Link between Customer (Customers) and User (Django auth).

    Created when Customer needs a web session.
    1:1 relationship in both directions.

    Auth creates User on demand. The User is just
    a session mechanism - Customer is the real entity.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shopman_auth_identity_link",
        verbose_name=_("usuário"),
    )

    # Customer UUID from Customers
    # Using UUID field, not FK, for decoupling
    customer_id = models.UUIDField(
        _("ID do cliente"),
        unique=True,
        db_index=True,
        help_text=_("UUID do cliente no Customers"),
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    # D3: Metadata for device info, login source, etc.
    metadata = models.JSONField(
        _("metadados"),
        default=dict,
        blank=True,
        help_text=_('Metadados do vínculo. Ex: {"device": "Chrome/120", "ip": "192.168.1.1"}'),
    )

    class Meta:
        db_table = "shopman_auth_identity_link"
        verbose_name = _("perfil de usuário")
        verbose_name_plural = _("perfis de usuário")

    def __str__(self):
        return f"User {self.user_id} <-> Customer {self.customer_id}"

    def get_customer(self):
        """Fetch customer info via resolver."""
        from ..conf import get_customer_resolver

        resolver = get_customer_resolver()
        return resolver.get_by_uuid(self.customer_id)
