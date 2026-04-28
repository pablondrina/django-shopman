from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0003_operatoralert_production_types"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="dayclosing",
            options={
                "ordering": ["-date"],
                "permissions": [
                    ("perform_closing", "Pode executar fechamento do dia"),
                    ("view_production_reports", "Pode ver relatórios de produção"),
                ],
                "verbose_name": "fechamento do dia",
                "verbose_name_plural": "fechamentos do dia",
            },
        ),
    ]
