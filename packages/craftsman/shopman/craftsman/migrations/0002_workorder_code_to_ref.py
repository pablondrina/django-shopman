"""
Rename WorkOrder.code → WorkOrder.ref and CodeSequence → RefSequence.

Follows the suite-wide convention: `ref` for operational identifiers.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("craftsman", "0001_initial"),
    ]

    operations = [
        # WorkOrder.code → WorkOrder.ref
        migrations.RenameField(
            model_name="workorder",
            old_name="code",
            new_name="ref",
        ),
        # CodeSequence → RefSequence
        migrations.RenameModel(
            old_name="CodeSequence",
            new_name="RefSequence",
        ),
    ]
