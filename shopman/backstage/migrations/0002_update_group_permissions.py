"""Data migration: update RBAC group permissions to use backstage app labels.

Models KDSTicket, CashRegisterSession, and DayClosing moved from the shop app
to the backstage app. The groups created in shop.0008 must reference the new
ContentTypes so has_perm("backstage.*") checks pass.
"""

from django.db import migrations


def update_group_permissions(apps, schema_editor):
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    moves = [
        ("shop", "kdsticket", "backstage", "kdsticket"),
        ("shop", "cashregistersession", "backstage", "cashregistersession"),
        ("shop", "dayclosing", "backstage", "dayclosing"),
    ]

    for old_app, model, new_app, _ in moves:
        try:
            old_ct = ContentType.objects.get(app_label=old_app, model=model)
        except ContentType.DoesNotExist:
            continue
        new_ct, _ = ContentType.objects.get_or_create(app_label=new_app, model=model)

        old_perms = Permission.objects.filter(content_type=old_ct)
        for old_perm in old_perms:
            new_perm, _ = Permission.objects.get_or_create(
                content_type=new_ct,
                codename=old_perm.codename,
                defaults={"name": old_perm.name},
            )
            for group in Group.objects.filter(permissions=old_perm):
                group.permissions.remove(old_perm)
                group.permissions.add(new_perm)


def revert_group_permissions(apps, schema_editor):
    pass  # not worth reverting in a new project


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0001_initial"),
        ("shop", "0008_setup_default_groups"),
    ]

    operations = [
        migrations.RunPython(update_group_permissions, revert_group_permissions),
    ]
