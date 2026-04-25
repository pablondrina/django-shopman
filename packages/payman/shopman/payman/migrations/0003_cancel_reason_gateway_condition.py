from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payman", "0002_gateway_id_unique_cancel_reason"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentintent",
            name="cancel_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.RemoveConstraint(
            model_name="paymentintent",
            name="pay_intent_gateway_id_unique",
        ),
        migrations.AddConstraint(
            model_name="paymentintent",
            constraint=models.UniqueConstraint(
                condition=models.Q(gateway_id__gt=""),
                fields=("gateway", "gateway_id"),
                name="pay_intent_gateway_id_unique",
            ),
        ),
    ]
