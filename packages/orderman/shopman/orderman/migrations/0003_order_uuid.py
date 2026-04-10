"""
Add uuid field to Order model.

Follows the uuid + ref pattern used by other aggregate roots (Customer, PaymentIntent).
"""

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orderman", "0002_monetary_check_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
