"""Data migration: create 'Rules Managers' group with manage_rules permission.

The group has 0 members by default — admin staff must be explicitly added.
This ensures that compromising a staff account does not automatically grant
the ability to modify pricing/validation rules.

Note: uses real auth models (not historical) — auth schema is stable and
the frozen-model API does not reliably support M2M through permission fields.
"""

from django.db import migrations


def create_rules_managers_group(apps, schema_editor):
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    group, _ = Group.objects.get_or_create(name="Rules Managers")

    ct, _ = ContentType.objects.get_or_create(app_label="shop", model="ruleconfig")
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="manage_rules",
        defaults={"name": "Pode gerenciar regras de pricing e validação"},
    )
    group.permissions.add(perm)


def remove_rules_managers_group(apps, schema_editor):
    from django.contrib.auth.models import Group

    Group.objects.filter(name="Rules Managers").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0004_ruleconfig_history_manage_rules"),
    ]

    operations = [
        migrations.RunPython(
            create_rules_managers_group,
            reverse_code=remove_rules_managers_group,
        ),
    ]
