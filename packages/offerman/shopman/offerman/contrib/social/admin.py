"""Adds a "Redes sociais" segment to Offerman's Product admin.

Composable by design: at ``ready()`` time we read whatever ``ProductAdmin`` is
currently registered (plain, or Fiscalman's subclass) and build a subclass on
top — so the fiscal and social tabs coexist regardless of app order. Same
pattern/motivation as ``fiscalman.contrib.offerman`` (one-directional: this
contrib knows Offerman, not the reverse).
"""

from __future__ import annotations

from django import forms
from shopman.offerman.contrib.social.schema import (
    CONDITION_CHOICES,
    ProductSocialAttributes,
    get_social_attributes,
    set_social_attributes,
)

SOCIAL_FORM_FIELDS = (
    "social_brand",
    "social_gtin",
    "social_mpn",
    "social_condition",
    "social_google_category",
    "social_tiktok_category",
    "social_hashtags",
    "social_caption",
)


def build_social_form(base_form_cls):
    """Return a ``base_form_cls`` subclass exposing the social fields, backed by
    ``metadata['social']``."""

    class SocialProductAdminForm(base_form_cls):
        social_brand = forms.CharField(
            label="Marca", required=False, max_length=100,
            help_text="Vazio usa o nome da loja. Google/Meta usam como marca do produto.",
        )
        social_gtin = forms.CharField(
            label="GTIN / código de barras", required=False, max_length=14,
            help_text="8, 12, 13 ou 14 dígitos. Vazio = 'sem código de barras' (identifier_exists=no no Google).",
        )
        social_mpn = forms.CharField(
            label="MPN", required=False, max_length=70,
            help_text="Código do fabricante. Só necessário no Google quando não há GTIN.",
        )
        social_condition = forms.ChoiceField(
            label="Condição", required=False, choices=CONDITION_CHOICES,
            help_text="Novo por padrão.",
        )
        social_google_category = forms.CharField(
            label="Categoria Google", required=False, max_length=255,
            help_text="ID numérico (ex.: 2271) ou caminho ' > ' da taxonomia Google Shopping.",
        )
        social_tiktok_category = forms.CharField(
            label="Categoria TikTok", required=False, max_length=64,
            help_text="ID da categoria no TikTok Shop (quando aplicável).",
        )
        social_hashtags = forms.CharField(
            label="Hashtags", required=False,
            help_text="Separadas por espaço ou vírgula, sem #.",
        )
        social_caption = forms.CharField(
            label="Legenda social", required=False, max_length=2200,
            widget=forms.Textarea(attrs={"rows": 3}),
            help_text="Texto curto para redes sociais (nome/descrição do produto são o padrão).",
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance and self.instance.pk:
                attrs = get_social_attributes(self.instance)
                self.fields["social_brand"].initial = attrs.brand
                self.fields["social_gtin"].initial = attrs.gtin
                self.fields["social_mpn"].initial = attrs.mpn
                self.fields["social_condition"].initial = attrs.condition
                self.fields["social_google_category"].initial = attrs.google_product_category
                self.fields["social_tiktok_category"].initial = attrs.tiktok_category_id
                self.fields["social_hashtags"].initial = " ".join(attrs.hashtags)
                self.fields["social_caption"].initial = attrs.social_caption
            else:
                self.fields["social_condition"].initial = "new"

        def clean(self):
            cleaned = super().clean()
            attrs = ProductSocialAttributes(
                brand=(cleaned.get("social_brand") or "").strip(),
                gtin=(cleaned.get("social_gtin") or "").strip(),
                mpn=(cleaned.get("social_mpn") or "").strip(),
                condition=(cleaned.get("social_condition") or "new"),
                google_product_category=(cleaned.get("social_google_category") or "").strip(),
                tiktok_category_id=(cleaned.get("social_tiktok_category") or "").strip(),
                hashtags=(cleaned.get("social_hashtags") or ""),
                social_caption=(cleaned.get("social_caption") or "").strip(),
            )
            for message in attrs.errors():
                self.add_error(None, message)

            metadata = set_social_attributes(cleaned.get("metadata") or {}, attrs)
            cleaned["metadata"] = metadata
            if self.instance is not None:
                self.instance.metadata = metadata
            return cleaned

    return SocialProductAdminForm


def build_social_product_admin(base_admin_cls):
    """Return a ``base_admin_cls`` subclass with the social form + "Redes sociais" tab."""
    from shopman.offerman.contrib.admin_unfold.nutrition_form import ProductAdminForm

    base_form = getattr(base_admin_cls, "form", None) or ProductAdminForm
    social_form = build_social_form(base_form)

    class SocialProductAdmin(base_admin_cls):
        form = social_form

        def get_fieldsets(self, request, obj=None):
            fieldsets = list(super().get_fieldsets(request, obj))
            social_fieldset = (
                "Redes sociais",
                {
                    "fields": SOCIAL_FORM_FIELDS,
                    "classes": ("tab",),
                    "description": (
                        "Dados para publicar em Google Shopping, Meta (Instagram/Facebook/WhatsApp) "
                        "e TikTok. Nome, descrição e palavras-chave vêm dos campos principais; aqui "
                        "ficam marca, código de barras, categoria e legenda social."
                    ),
                },
            )
            # Insert just before the trailing "Metadados" fieldset when present.
            insert_at = max(len(fieldsets) - 1, 0)
            fieldsets.insert(insert_at, social_fieldset)
            return fieldsets

    SocialProductAdmin.__name__ = "SocialProductAdmin"
    SocialProductAdmin.__qualname__ = "SocialProductAdmin"
    return SocialProductAdmin
