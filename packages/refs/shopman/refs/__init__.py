"""
shopman.refs — public API surface for WP-REF-01.

Subsequent WPs (REF-02, REF-04) will extend this with attach, resolve, etc.
"""

from shopman.refs.registry import get_all_ref_types, get_ref_type, register_ref_type

default_app_config = "shopman.refs.apps.RefsConfig"

__all__ = [
    "register_ref_type",
    "get_ref_type",
    "get_all_ref_types",
]
