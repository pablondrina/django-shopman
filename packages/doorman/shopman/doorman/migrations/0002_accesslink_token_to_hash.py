"""
Migrate AccessLink.token (plaintext) to AccessLink.token_hash (HMAC-SHA256).

Security hardening: tokens are no longer stored in plaintext.
Existing tokens are invalidated by this migration (they will need to be
re-created with the new hashing scheme).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("doorman", "0001_initial"),
    ]

    operations = [
        # Rename the field from token to token_hash
        migrations.RenameField(
            model_name="accesslink",
            old_name="token",
            new_name="token_hash",
        ),
        # Update field definition (remove default, update help_text)
        migrations.AlterField(
            model_name="accesslink",
            name="token_hash",
            field=models.CharField(
                max_length=64,
                unique=True,
                db_index=True,
                verbose_name="hash do token",
                help_text="HMAC-SHA256 do token. Token bruto nunca é persistido.",
            ),
        ),
    ]
