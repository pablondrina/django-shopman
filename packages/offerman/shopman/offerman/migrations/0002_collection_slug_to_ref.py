"""
Rename Collection.slug → Collection.ref.

Follows the suite-wide convention: `ref` for operational identifiers.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("offerman", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="collection",
            old_name="slug",
            new_name="ref",
        ),
    ]
