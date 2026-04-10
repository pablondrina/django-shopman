"""CustomerGroup model."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomerGroup(models.Model):
    """Customer group for segmentation."""

    # Identification
    ref = models.SlugField(_("referência"), max_length=50, unique=True)
    name = models.CharField(_("nome"), max_length=200)
    description = models.TextField(_("descrição"), blank=True)

    # Link to pricing (Offerman Listing)
    listing_ref = models.CharField(
        _("código da listagem"),
        max_length=50,
        blank=True,
        help_text=_("Código do Listing no Offerman (convenção: Listing.ref == Channel.ref)"),
    )

    # Configuration
    is_default = models.BooleanField(
        _("padrão"),
        default=False,
        help_text=_("Grupo padrão para novos clientes"),
    )

    # Priority (for business rules)
    priority = models.IntegerField(
        _("prioridade"),
        default=0,
        help_text=_("Maior = mais prioridade"),
    )

    # Extensible metadata
    metadata = models.JSONField(
        _("metadados"), default=dict, blank=True,
        help_text=_('Metadados do grupo. Ex: {"discount_percent": 10, "min_order_q": 5000}'),
    )

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("grupo de clientes")
        verbose_name_plural = _("grupos de clientes")
        ordering = ["-priority", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            CustomerGroup.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )
        super().save(*args, **kwargs)
