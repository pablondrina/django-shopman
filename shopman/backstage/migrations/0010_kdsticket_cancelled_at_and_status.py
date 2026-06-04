from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0009_alter_postab_reference"),
    ]

    operations = [
        migrations.AddField(
            model_name="kdsticket",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="cancelado em"),
        ),
        migrations.AlterField(
            model_name="kdsticket",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pendente"),
                    ("in_progress", "Em andamento"),
                    ("done", "Concluído"),
                    ("cancelled", "Cancelado"),
                ],
                default="pending",
                max_length=20,
                verbose_name="status",
            ),
        ),
    ]
