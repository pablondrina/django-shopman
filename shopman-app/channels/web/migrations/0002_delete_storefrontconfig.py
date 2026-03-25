from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("web_channel", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(
            name="StorefrontConfig",
        ),
    ]
