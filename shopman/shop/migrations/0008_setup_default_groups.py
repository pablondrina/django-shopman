"""Data migration: create Caixa, Cozinha, Gerente, Admin de Catálogo groups with permissions."""

from django.db import migrations


def create_groups(apps, schema_editor):
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    def _perm(app_label, model, codename):
        ct, _ = ContentType.objects.get_or_create(app_label=app_label, model=model)
        p, _ = Permission.objects.get_or_create(content_type=ct, codename=codename)
        return p

    shop_shop = lambda c: _perm("shop", "shop", c)
    shop_kdst = lambda c: _perm("shop", "kdsticket", c)
    shop_cash = lambda c: _perm("shop", "cashregistersession", c)
    shop_dclo = lambda c: _perm("shop", "dayclosing", c)
    shop_rule = lambda c: _perm("shop", "ruleconfig", c)

    groups = {
        "Caixa": [
            shop_cash("operate_pos"),
            shop_shop("manage_orders"),
        ],
        "Cozinha": [
            shop_kdst("operate_kds"),
            shop_shop("manage_production"),
        ],
        "Gerente": [
            shop_shop("manage_orders"),
            shop_cash("operate_pos"),
            shop_dclo("perform_closing"),
            shop_shop("view_reports"),
            shop_shop("manage_customers"),
        ],
        "Admin de Catálogo": [
            shop_shop("manage_catalog"),
            shop_rule("manage_rules"),
        ],
    }

    for name, perms in groups.items():
        group, _ = Group.objects.get_or_create(name=name)
        for perm in perms:
            group.permissions.add(perm)


def remove_groups(apps, schema_editor):
    from django.contrib.auth.models import Group

    for name in ("Caixa", "Cozinha", "Gerente", "Admin de Catálogo"):
        Group.objects.filter(name=name).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0007_add_custom_permissions"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
