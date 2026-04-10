"""
Exceptions para contrib/refs.
"""


class RefError(Exception):
    """Base para erros de Refs."""

    pass


class RefTypeNotFound(RefError):
    """RefType não registrado."""

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f"RefType '{slug}' not found in registry")


class RefScopeInvalid(RefError):
    """Scope não contém keys necessárias."""

    def __init__(self, missing_keys: set[str], ref_type_slug: str):
        self.missing_keys = missing_keys
        self.ref_type_slug = ref_type_slug
        super().__init__(
            f"Scope missing required keys for RefType '{ref_type_slug}': {missing_keys}"
        )


class RefConflict(RefError):
    """Já existe Ref para outro target."""

    def __init__(
        self,
        ref_type_slug: str,
        value: str,
        existing_target_kind: str,
        existing_target_id: str,
    ):
        self.ref_type_slug = ref_type_slug
        self.value = value
        self.existing_target_kind = existing_target_kind
        self.existing_target_id = existing_target_id
        super().__init__(
            f"Ref conflict: '{ref_type_slug}' value '{value}' already assigned to "
            f"{existing_target_kind} {existing_target_id}"
        )
