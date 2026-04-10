"""
Add CheckConstraint for non-negative Quant._quantity.

Ensures stock balance cannot go below zero at the database level.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stockman", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="quant",
            constraint=models.CheckConstraint(
                condition=models.Q(_quantity__gte=0),
                name="stk_quant_quantity_non_negative",
            ),
        ),
    ]
