import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Ref",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("ref_type", models.CharField(db_index=True, max_length=32, verbose_name="tipo")),
                ("value", models.CharField(db_index=True, max_length=128, verbose_name="valor")),
                ("target_type", models.CharField(
                    help_text='"{app_label}.{ModelName}" — ex: "orderman.Session"',
                    max_length=64,
                    verbose_name="tipo do alvo",
                )),
                ("target_id", models.CharField(max_length=64, verbose_name="ID do alvo")),
                ("scope", models.JSONField(blank=True, default=dict, verbose_name="escopo")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="ativo")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("actor", models.CharField(
                    blank=True,
                    help_text='"system", "user:42", "lifecycle:commit"',
                    max_length=128,
                    verbose_name="ator",
                )),
                ("deactivated_at", models.DateTimeField(blank=True, null=True, verbose_name="desativado em")),
                ("deactivated_by", models.CharField(blank=True, max_length=128, verbose_name="desativado por")),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="metadados")),
            ],
            options={
                "verbose_name": "Referencia",
                "verbose_name_plural": "Referencias",
                "app_label": "refs",
            },
        ),
        migrations.CreateModel(
            name="RefSequence",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sequence_name", models.CharField(db_index=True, max_length=32, verbose_name="nome da sequencia")),
                ("scope_hash", models.CharField(db_index=True, max_length=64, verbose_name="hash do escopo")),
                ("scope", models.JSONField(default=dict, verbose_name="escopo")),
                ("last_value", models.PositiveIntegerField(default=0, verbose_name="ultimo valor")),
            ],
            options={
                "verbose_name": "Sequencia de Referencia",
                "verbose_name_plural": "Sequencias de Referencia",
                "app_label": "refs",
            },
        ),
        migrations.AddIndex(
            model_name="ref",
            index=models.Index(fields=["ref_type", "value", "is_active"], name="ref_type_val_active_idx"),
        ),
        migrations.AddIndex(
            model_name="ref",
            index=models.Index(fields=["target_type", "target_id", "is_active"], name="ref_target_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="refsequence",
            constraint=models.UniqueConstraint(
                fields=["sequence_name", "scope_hash"],
                name="refs_unique_sequence_scope",
            ),
        ),
    ]
