"""
Update UniqueConstraint on Quant to use nulls_distinct=False.

Requires PostgreSQL 15+. Ensures that two Quants with the same
(sku, position=NULL, target_date=NULL, batch='') are treated as
duplicates, preventing silent coordinate collisions.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stockman", "0002_quant_non_negative_constraint"),
    ]

    operations = [
        # Remove old constraint (nulls_distinct defaulted to True)
        migrations.RemoveConstraint(
            model_name="quant",
            name="unique_quant_coordinate",
        ),
        # Re-add with nulls_distinct=False
        migrations.AddConstraint(
            model_name="quant",
            constraint=models.UniqueConstraint(
                fields=["sku", "position", "target_date", "batch"],
                name="unique_quant_coordinate",
                nulls_distinct=False,
            ),
        ),
    ]
