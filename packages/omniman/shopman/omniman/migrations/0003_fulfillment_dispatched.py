"""Rename Fulfillment.SHIPPED → DISPATCHED, shipped_at → dispatched_at."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("omniman", "0002_channel_listing_ref"),
    ]

    operations = [
        # Rename field shipped_at → dispatched_at
        migrations.RenameField(
            model_name="fulfillment",
            old_name="shipped_at",
            new_name="dispatched_at",
        ),
        # Update status choices and verbose_name
        migrations.AlterField(
            model_name="fulfillment",
            name="dispatched_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="despachado em"
            ),
        ),
        migrations.AlterField(
            model_name="fulfillment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "pendente"),
                    ("in_progress", "em andamento"),
                    ("dispatched", "despachado"),
                    ("delivered", "entregue"),
                    ("cancelled", "cancelado"),
                ],
                db_index=True,
                default="pending",
                max_length=32,
                verbose_name="status",
            ),
        ),
        # Migrate existing data: shipped → dispatched
        migrations.RunSQL(
            sql="UPDATE omniman_fulfillment SET status = 'dispatched' WHERE status = 'shipped';",
            reverse_sql="UPDATE omniman_fulfillment SET status = 'shipped' WHERE status = 'dispatched';",
        ),
    ]
