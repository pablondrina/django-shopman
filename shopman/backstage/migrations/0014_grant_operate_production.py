"""Grant the new ``backstage.operate_production`` permission to the operator groups.

Sibling of ``operate_pos``/``operate_kds``: the coarse surface gate for the
dedicated production app (``fournil.``). Granted to Cozinha (floor) and Gerente
(oversight), matching ``setup_groups``. Additive + idempotent + reversible.
"""

from django.db import migrations

GROUPS = ("Cozinha", "Gerente")


def grant(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct, _ = ContentType.objects.get_or_create(app_label="backstage", model="dayclosing")
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="operate_production",
        defaults={"name": "Pode operar a produção (chão + planejamento) no app dedicado"},
    )
    for name in GROUPS:
        group = Group.objects.filter(name=name).first()
        if group:
            group.permissions.add(perm)


def revoke(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    perm = Permission.objects.filter(
        content_type__app_label="backstage",
        content_type__model="dayclosing",
        codename="operate_production",
    ).first()
    if not perm:
        return
    for name in GROUPS:
        group = Group.objects.filter(name=name).first()
        if group:
            group.permissions.remove(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0013_alter_dayclosing_options"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(grant, revoke),
    ]
