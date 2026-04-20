"""
Registries for shopman.refs.

RefTypeRegistry  — config-as-code RefType definitions (registered in AppConfig.ready()).
RefSourceRegistry — maps (model.field) -> ref_type for cascade/bulk operations (WP-REF-05).
"""

from __future__ import annotations

from shopman.refs.types import RefType


class RefTypeRegistry:
    """Central registry of RefType definitions."""

    def __init__(self) -> None:
        self._types: dict[str, RefType] = {}

    def register(self, ref_type: RefType) -> None:
        """Register a RefType.

        Raises:
            ValueError: If a RefType with the same slug is already registered.
        """
        if ref_type.slug in self._types:
            raise ValueError(f"RefType '{ref_type.slug}' already registered")
        self._types[ref_type.slug] = ref_type

    def get(self, slug: str) -> RefType | None:
        """Return the RefType for slug, or None if not registered."""
        return self._types.get(slug)

    def get_all(self) -> list[RefType]:
        """Return all registered RefTypes."""
        return list(self._types.values())

    def clear(self) -> None:
        """Clear all registrations. For use in tests only."""
        self._types.clear()


class RefSourceRegistry:
    """Maps (app_label.ModelName, field_name) -> ref_type for cascade bulk operations.

    Populated by RefField.contribute_to_class() (WP-REF-05). Each entry records
    which model fields store values for a given ref_type so that RefBulk.cascade_rename()
    can propagate renames across the whole schema.
    """

    def __init__(self) -> None:
        self._sources: dict[str, list[tuple[str, str]]] = {}

    def register(self, app_label_model: str, field_name: str, ref_type: str | None) -> None:
        """Register a model field as a source for ref_type.

        Args:
            app_label_model: "{app_label}.{ModelName}" string (e.g. "offerman.Product").
            field_name: Name of the CharField that stores ref values.
            ref_type: RefType.slug this field belongs to, or None for identity fields.
        """
        if ref_type is None:
            return
        self._sources.setdefault(ref_type, []).append((app_label_model, field_name))

    def register_lazy(self, app_label_model: str, field_name: str, ref_type: str | None) -> None:
        """Same as register() — alias used by RefField.contribute_to_class()."""
        self.register(app_label_model, field_name, ref_type)

    def get_sources_for_type(self, ref_type: str) -> list[tuple[str, str]]:
        """Return all (app_label_model, field_name) pairs for the given ref_type."""
        return list(self._sources.get(ref_type, []))

    def clear(self) -> None:
        """Clear all registrations. For use in tests only."""
        self._sources.clear()


# ── Global singletons ────────────────────────────────────────────────────────

_ref_type_registry = RefTypeRegistry()
_ref_source_registry = RefSourceRegistry()

# Public API surface

register_ref_type = _ref_type_registry.register
get_ref_type = _ref_type_registry.get
get_all_ref_types = _ref_type_registry.get_all
clear_ref_types = _ref_type_registry.clear
