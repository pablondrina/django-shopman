from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0018_shop_kitchen_note_tags"),
    ]

    operations = [
        migrations.RenameField(
            model_name="ruleconfig",
            old_name="code",
            new_name="ref",
        ),
        migrations.RenameField(
            model_name="historicalruleconfig",
            old_name="code",
            new_name="ref",
        ),
    ]
