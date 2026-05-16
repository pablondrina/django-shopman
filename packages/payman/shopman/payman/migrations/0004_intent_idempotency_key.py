from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payman", "0003_cancel_reason_gateway_condition"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentintent",
            name="idempotency_key",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddConstraint(
            model_name="paymentintent",
            constraint=models.UniqueConstraint(
                condition=models.Q(idempotency_key__gt=""),
                fields=("idempotency_key",),
                name="pay_intent_idempotency_key_unique",
            ),
        ),
    ]
