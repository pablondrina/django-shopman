"""ProductForm with dedicated nutrition fields.

The ``Product.nutrition_facts`` JSONField is edited through virtual form
fields — one ``IntegerField`` / ``FloatField`` per nutrient — never as
raw JSON. The form serializes these back into the JSON on save.

Dataclass-driven: field names and types follow
``shopman.offerman.nutrition.NutritionFacts``.
"""

from __future__ import annotations

from django import forms
from shopman.offerman.models import Product
from shopman.offerman.nutrition import (
    NUTRIENT_LABELS_PT,
    NutritionFacts,
)

# Ordered groups for fieldset rendering ("fieldset-like" sub-order in the admin).
SERVING_FIELDS = ("serving_size_g", "servings_per_container")
MACRONUTRIENTS = (
    "energy_kcal",
    "carbohydrates_g",
    "sugars_g",
    "proteins_g",
    "total_fat_g",
    "saturated_fat_g",
    "trans_fat_g",
)
MICRONUTRIENTS = ("fiber_g", "sodium_mg")


def _widget_for(field_name: str) -> forms.Widget:
    return forms.NumberInput(attrs={"step": "0.01", "class": "vTextField"})


def _field_for(field_name: str) -> forms.Field:
    label = NUTRIENT_LABELS_PT.get(field_name, field_name)
    if field_name in ("serving_size_g", "servings_per_container"):
        return forms.IntegerField(
            label=label, required=False, min_value=0, widget=_widget_for(field_name),
        )
    return forms.FloatField(
        label=label, required=False, min_value=0.0, widget=_widget_for(field_name),
    )


NUTRITION_FORM_FIELDS: tuple[str, ...] = (
    SERVING_FIELDS + MACRONUTRIENTS + MICRONUTRIENTS
)
REMOTE_PURCHASE_FORM_FIELDS = (
    "allergens_text",
    "dietary_info_text",
    "serves_text",
    "approx_dimensions_text",
)


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _join_list(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        return value.strip()
    return ""


class ProductAdminForm(forms.ModelForm):
    """Form that exposes nutrition_facts as flat per-nutrient fields."""

    image_url = forms.URLField(
        label="URL da imagem",
        required=False,
        max_length=500,
        assume_scheme="https",
        help_text="URL da imagem principal do produto (ex: Unsplash, Cloudinary, S3)",
    )
    allergens_text = forms.CharField(
        label="Alérgenos",
        required=False,
        help_text="Separe por vírgula. Ex.: glúten, leite, gergelim.",
    )
    dietary_info_text = forms.CharField(
        label="Restrições",
        required=False,
        help_text="Separe por vírgula. Ex.: 100% vegetal, sem lactose.",
    )
    serves_text = forms.CharField(
        label="Serve",
        required=False,
        help_text="Ex.: 2 a 4 pessoas.",
    )
    approx_dimensions_text = forms.CharField(
        label="Medidas aproximadas",
        required=False,
        help_text="Ex.: aprox. 24 x 12 x 10 cm.",
    )
    allows_next_day_sale = forms.BooleanField(
        label="Permite venda no dia seguinte",
        required=False,
        help_text="Produto pode ser vendido no dia seguinte com preço reduzido.",
    )

    # Virtual nutrient fields are declared at class scope (dataclass-driven via
    # NutritionFacts) so the admin fieldsets that reference them validate. The
    # admin builds the form with ``modelform_factory(fields=flatten_fieldsets)``,
    # which only resolves model fields and *declared* form fields — fields added
    # in ``__init__`` are invisible to it and raise FieldError.
    locals().update({name: _field_for(name) for name in NUTRITION_FORM_FIELDS})

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Hide the raw JSON field from the admin rendering.
        if "nutrition_facts" in self.fields:
            self.fields["nutrition_facts"].widget = forms.HiddenInput()
            self.fields["nutrition_facts"].required = False

        # Populate from the stored dict on edit.
        if self.instance and self.instance.pk:
            facts = NutritionFacts.from_dict(self.instance.nutrition_facts or {})
            if facts is not None:
                for name in NUTRITION_FORM_FIELDS:
                    self.fields[name].initial = getattr(facts, name)

            metadata = self.instance.metadata or {}
            self.fields["allergens_text"].initial = _join_list(metadata.get("allergens"))
            self.fields["dietary_info_text"].initial = _join_list(
                metadata.get("dietary_info")
            )
            self.fields["serves_text"].initial = str(metadata.get("serves") or "")
            self.fields["approx_dimensions_text"].initial = str(
                metadata.get("approx_dimensions") or ""
            )
            self.fields["allows_next_day_sale"].initial = bool(
                metadata.get("allows_next_day_sale", False)
            )

    def clean(self):
        cleaned = super().clean()

        # Gather per-nutrient cleaned values into a dict.
        collected: dict[str, object] = {}
        for name in NUTRITION_FORM_FIELDS:
            value = cleaned.get(name)
            if value not in (None, ""):
                collected[name] = value

        # Preserve the auto_filled flag from the existing instance when the
        # operator touches the form — we default to "manual override" because
        # the operator is literally editing the field.
        has_any_nutrient = any(
            k for k in collected if k not in SERVING_FIELDS
        )
        if has_any_nutrient or "serving_size_g" in collected:
            collected["auto_filled"] = False

        cleaned["nutrition_facts"] = collected

        original_meta = (
            dict(self.instance.metadata or {})
            if (self.instance and self.instance.pk)
            else {}
        )

        metadata = dict(cleaned.get("metadata") or {})
        metadata.pop("allergens", None)
        metadata.pop("dietary_info", None)
        metadata.pop("serves", None)
        metadata.pop("approx_dimensions", None)
        metadata.pop("dietary_auto_filled", None)

        allergens = _split_list(cleaned.get("allergens_text") or "")
        dietary_info = _split_list(cleaned.get("dietary_info_text") or "")
        serves = (cleaned.get("serves_text") or "").strip()
        approx_dimensions = (cleaned.get("approx_dimensions_text") or "").strip()
        if allergens:
            metadata["allergens"] = allergens
        if dietary_info:
            metadata["dietary_info"] = dietary_info
        if serves:
            metadata["serves"] = serves
        if approx_dimensions:
            metadata["approx_dimensions"] = approx_dimensions

        metadata["allows_next_day_sale"] = bool(cleaned.get("allows_next_day_sale"))

        # Manual-override sentinel for the Recipe→Product dietary derivation
        # (mirrors nutrition's ``auto_filled``). Only flip to manual when the
        # operator actually changes the dietary data, so merely re-saving a
        # recipe-derived product does not freeze the derivation.
        dietary_changed = (
            allergens != (original_meta.get("allergens") or [])
            or dietary_info != (original_meta.get("dietary_info") or [])
        )
        if dietary_changed and (allergens or dietary_info):
            metadata["dietary_auto_filled"] = False
        elif "dietary_auto_filled" in original_meta:
            metadata["dietary_auto_filled"] = original_meta["dietary_auto_filled"]
        cleaned["metadata"] = metadata

        # Mirror into self.instance so Model.clean() sees the new value.
        if self.instance is not None:
            self.instance.nutrition_facts = collected
            self.instance.metadata = metadata
        return cleaned
