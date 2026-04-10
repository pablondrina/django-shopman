"""
WP-H2-2: Add error_code and dedupe_key to Directive.

- error_code: Canonical error classification (transient, terminal, handler_not_found, payload_invalid)
- dedupe_key: At-most-once deduplication window key (topic:order_ref:handler_version)
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("omniman", "0008_channel_kind_remove_listing_ref_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="directive",
            name="error_code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Canônico: transient, terminal, handler_not_found, payload_invalid",
                max_length=64,
                verbose_name="código de erro",
            ),
        ),
        migrations.AddField(
            model_name="directive",
            name="dedupe_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Formato: {topic}:{order_ref}:{handler_version}. Handlers definem o seu.",
                max_length=128,
                verbose_name="chave de deduplicação",
            ),
        ),
    ]
