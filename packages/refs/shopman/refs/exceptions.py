"""
Exceptions for shopman.refs.
"""


class RefError(Exception):
    """Base for all ref errors."""


class RefConflict(RefError):
    """A Ref already exists for a different target."""

    def __init__(self, ref_type_slug: str, value: str, existing_target_type: str, existing_target_id: str):
        self.ref_type_slug = ref_type_slug
        self.value = value
        self.existing_target_type = existing_target_type
        self.existing_target_id = existing_target_id
        super().__init__(
            f"Ref conflict: '{ref_type_slug}' value '{value}' already assigned to "
            f"{existing_target_type}:{existing_target_id}"
        )


class RefNotFound(RefError):
    """No active Ref matches the lookup."""

    def __init__(self, ref_type_slug: str, value: str):
        self.ref_type_slug = ref_type_slug
        self.value = value
        super().__init__(f"No active Ref found: {ref_type_slug}:{value}")


class RefScopeInvalid(RefError):
    """Scope is missing required keys for the RefType."""

    def __init__(self, missing_keys: set[str], ref_type_slug: str):
        self.missing_keys = missing_keys
        self.ref_type_slug = ref_type_slug
        super().__init__(
            f"Scope missing required keys for RefType '{ref_type_slug}': {missing_keys}"
        )


class AmbiguousRef(RefError):
    """Partial lookup matched more than one active Ref."""

    def __init__(self, ref_type_slug: str, suffix: str, count: int):
        self.ref_type_slug = ref_type_slug
        self.suffix = suffix
        self.count = count
        super().__init__(
            f"Ambiguous ref: '{ref_type_slug}' suffix '{suffix}' matched {count} active refs"
        )
