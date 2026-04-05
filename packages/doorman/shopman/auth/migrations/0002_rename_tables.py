"""
Rename auth tables from old naming (AUTH-0 refactor).

MagicCode      → VerificationCode
BridgeToken    → AccessLink
IdentityLink   → CustomerUser

Conditional: only renames if old tables exist (fresh DBs already have new names
from 0001_initial).
"""

from django.db import connection, migrations


def _table_exists(name: str) -> bool:
    """Check if a table exists in the database."""
    tables = connection.introspection.table_names()
    return name in tables


def rename_tables(apps, schema_editor):
    renames = [
        ("shopman_auth_magic_code", "shopman_auth_verification_code"),
        ("shopman_auth_bridge_token", "shopman_auth_access_link"),
        ("shopman_auth_identity_link", "shopman_auth_customer_user"),
    ]
    for old, new in renames:
        if _table_exists(old):
            schema_editor.execute(f'ALTER TABLE "{old}" RENAME TO "{new}";')


def reverse_rename_tables(apps, schema_editor):
    renames = [
        ("shopman_auth_verification_code", "shopman_auth_magic_code"),
        ("shopman_auth_access_link", "shopman_auth_bridge_token"),
        ("shopman_auth_customer_user", "shopman_auth_identity_link"),
    ]
    for old, new in renames:
        if _table_exists(old):
            schema_editor.execute(f'ALTER TABLE "{old}" RENAME TO "{new}";')


class Migration(migrations.Migration):

    dependencies = [
        ("shopman_auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(rename_tables, reverse_rename_tables),
    ]
