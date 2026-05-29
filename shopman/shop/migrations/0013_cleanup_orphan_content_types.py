"""Faxina B1: remove orphan ContentTypes/Permissions from the shop→backstage move.

CashRegisterSession, KDSTicket and DayClosing moved from shop to backstage.
`shop.0008_setup_default_groups` created groups referencing perms under the
`shop.*` ContentTypes; `backstage.0002_update_group_permissions` re-pointed the
group memberships to the `backstage.*` ContentTypes. The leftover `shop.*`
ContentTypes (and their cascaded Permissions, e.g. a duplicate `operate_pos`)
are orphan cruft. This migration removes them.

Depends on backstage.0002 so the re-pointing has already happened before we
delete the old perms (otherwise the groups would lose the permission).
"""

from django.db import migrations

_ORPHANS = [
    ("shop", "cashregistersession"),
    ("shop", "kdsticket"),
    ("shop", "dayclosing"),
]


def remove_orphans(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    for app_label, model in _ORPHANS:
        ct = ContentType.objects.filter(app_label=app_label, model=model).first()
        if ct is not None:
            ct.delete()  # cascades to the orphan Permission rows


def noop(apps, schema_editor):
    """Irreversible cleanup — orphan content types are not recreated on revert."""


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0012_production_column_permissions"),
        ("backstage", "0002_update_group_permissions"),
    ]

    operations = [
        migrations.RunPython(remove_orphans, noop),
    ]
