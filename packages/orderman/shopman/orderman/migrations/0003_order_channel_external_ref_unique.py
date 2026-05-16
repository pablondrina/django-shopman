from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orderman", "0002_alter_sessionitem_sku"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_ref__isnull", False))
                & ~models.Q(("external_ref", "")),
                fields=("channel_ref", "external_ref"),
                name="ord_uniq_order_channel_external_ref",
            ),
        ),
    ]
