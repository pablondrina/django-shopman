from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guestman", "0002_alter_customer_metadata_alter_customergroup_metadata_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(
                condition=~models.Q(phone=""),
                fields=("phone",),
                name="unique_customer_phone",
            ),
        ),
    ]
