"""Per-product fiscal segment for Offerman's Product admin.

Extends Offerman's ``ProductAdminForm``/``ProductAdmin`` (which already manage
nutrition and metadata) with the fiscal classification — ``profile`` + ``NCM`` +
``CEST`` — edited as proper form fields and stored in ``Product.metadata['fiscal']``.
CFOP/CSOSN/origem/PIS-COFINS are NOT edited here: they come from the named profile
at emission time (see ``shopman.fiscalman.classification``).
"""

from __future__ import annotations

from django import forms
from shopman.fiscalman.classification import (
    DEFAULT_PROFILE_KEY,
    FISCAL_PROFILES,
    ProductFiscalClassification,
    from_metadata,
    to_metadata_fiscal,
)
from shopman.offerman.contrib.admin_unfold.admin import ProductAdmin
from shopman.offerman.contrib.admin_unfold.nutrition_form import ProductAdminForm

FISCAL_FORM_FIELDS = ("fiscal_profile", "fiscal_ncm", "fiscal_cest")


class FiscalProductAdminForm(ProductAdminForm):
    """Adds fiscal classification fields, backed by ``metadata['fiscal']``."""

    fiscal_profile = forms.ChoiceField(
        label="Perfil fiscal",
        required=False,
        choices=[(key, profile.name) for key, profile in FISCAL_PROFILES.items()],
        help_text=(
            "Define CFOP/CSOSN/origem/PIS-COFINS na emissão. "
            "Fabricação própria (5101/102) ou Revenda com ST (5405/500)."
        ),
    )
    fiscal_ncm = forms.CharField(
        label="NCM",
        required=False,
        max_length=8,
        help_text="8 dígitos. Ex.: 19059010 (pão), 19059090 (folhados/salgados).",
    )
    fiscal_cest = forms.CharField(
        label="CEST",
        required=False,
        max_length=7,
        help_text="7 dígitos. Só para itens de Revenda sujeitos a ST. Vazio em fabricação própria.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            current = from_metadata(self.instance.metadata or {})
            self.fields["fiscal_profile"].initial = current.profile
            self.fields["fiscal_ncm"].initial = current.ncm
            self.fields["fiscal_cest"].initial = current.cest
        else:
            self.fields["fiscal_profile"].initial = DEFAULT_PROFILE_KEY

    def clean(self):
        cleaned = super().clean()

        classification = ProductFiscalClassification(
            profile=cleaned.get("fiscal_profile") or DEFAULT_PROFILE_KEY,
            ncm=(cleaned.get("fiscal_ncm") or "").strip(),
            cest=(cleaned.get("fiscal_cest") or "").strip(),
        )

        # Validate only once any fiscal data is present — a product may be saved
        # without classification yet (pre-go-live); the emission/adapter guards
        # missing NCM at issue time.
        if classification.ncm or classification.cest:
            for message in classification.errors():
                self.add_error(None, message)

        metadata = dict(cleaned.get("metadata") or {})
        if classification.ncm or classification.cest:
            metadata["fiscal"] = to_metadata_fiscal(classification)
        cleaned["metadata"] = metadata
        if self.instance is not None:
            self.instance.metadata = metadata
        return cleaned


class FiscalProductAdmin(ProductAdmin):
    """Offerman's ProductAdmin + a "Fiscal" fieldset."""

    form = FiscalProductAdminForm

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        fiscal_fieldset = (
            "Fiscal (NFC-e)",
            {
                "fields": FISCAL_FORM_FIELDS,
                "classes": ("tab",),
                "description": (
                    "Classificação fiscal por produto. CFOP/CSOSN/origem/PIS-COFINS "
                    "vêm do perfil; NCM e CEST são por produto."
                ),
            },
        )
        # Insert just before the trailing "Metadados" fieldset when present.
        insert_at = max(len(fieldsets) - 1, 0)
        fieldsets.insert(insert_at, fiscal_fieldset)
        return fieldsets
