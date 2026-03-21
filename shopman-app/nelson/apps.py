"""
Nelson Boulangerie app configuration.

Registers Nelson-specific modifiers and validators in the Ordering registry,
plus canonical pricing modifiers from shopman.pricing.

Customizes app verbose_name for sidebar/breadcrumb in Admin.
"""
from __future__ import annotations

from django.apps import AppConfig


class NelsonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nelson"
    verbose_name = "Nelson Boulangerie"

    def ready(self):
        self._register_pricing_modifiers()
        self._register_nelson_modifiers()
        self._register_nelson_validators()
        self._customize_app_names()

    def _register_pricing_modifiers(self):
        """Register canonical pricing modifiers (from shopman.pricing)."""
        try:
            from shopman.ordering import registry
            from shopman.pricing.adapters.offerman import OffermanPricingBackend
            from shopman.pricing.modifiers import (
                ItemPricingModifier,
                SessionTotalModifier,
            )

            backend = OffermanPricingBackend()
            registry.register_modifier(ItemPricingModifier(backend))
            registry.register_modifier(SessionTotalModifier())
        except ImportError:
            pass

    def _register_nelson_modifiers(self):
        """Register Nelson-specific order modifiers."""
        try:
            from shopman.ordering import registry

            from .modifiers import EmployeeDiscountModifier, HappyHourModifier

            registry.register_modifier(EmployeeDiscountModifier())
            registry.register_modifier(HappyHourModifier())
        except ImportError:
            pass

    def _register_nelson_validators(self):
        """Register Nelson-specific order validators."""
        try:
            from shopman.ordering import registry

            from .validators import BusinessHoursValidator, MinimumOrderValidator

            registry.register_validator(BusinessHoursValidator())
            registry.register_validator(MinimumOrderValidator())
        except ImportError:
            pass

    def _customize_app_names(self):
        """Customize verbose_name for sidebar/breadcrumb in Admin."""
        from django.apps import apps

        app_names = {
            "offering": "Catalogo",
            "stocking": "Estoque",
            "crafting": "Producao",
            "attending": "Clientes",
        }
        for app_label, verbose in app_names.items():
            try:
                apps.get_app_config(app_label).verbose_name = verbose
            except LookupError:
                pass
