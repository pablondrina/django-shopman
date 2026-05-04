from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("craftsman", "0002_rename_work_order_commitment_meta"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="workorder",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Ordem de Produção",
                "verbose_name_plural": "Produção",
            },
        ),
    ]
