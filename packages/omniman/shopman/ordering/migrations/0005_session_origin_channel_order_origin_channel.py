# WP-F2: Removed — origin_channel stored in Session.data / Order.data (JSONField).
# No schema change needed. Keeping file as no-op to avoid migration conflicts.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ordering", "0004_alter_channel_config_alter_directive_payload_and_more"),
    ]

    operations = []
