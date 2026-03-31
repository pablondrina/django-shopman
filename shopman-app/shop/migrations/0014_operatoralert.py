from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0013_shop_neutral_dark_color"),
    ]

    operations = [
        migrations.CreateModel(
            name="OperatorAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(choices=[
                    ("notification_failed", "Notificação falhou"),
                    ("payment_failed", "Pagamento falhou"),
                    ("stock_discrepancy", "Discrepância de estoque"),
                    ("payment_after_cancel", "Pagamento após cancelamento"),
                    ("stock_low", "Estoque baixo"),
                ], max_length=30, verbose_name="tipo")),
                ("severity", models.CharField(choices=[
                    ("warning", "Aviso"),
                    ("error", "Erro"),
                    ("critical", "Crítico"),
                ], default="warning", max_length=10, verbose_name="severidade")),
                ("message", models.TextField(verbose_name="mensagem")),
                ("order_ref", models.CharField(blank=True, max_length=50, verbose_name="ref do pedido")),
                ("acknowledged", models.BooleanField(default=False, verbose_name="reconhecido")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
            ],
            options={
                "verbose_name": "alerta operacional",
                "verbose_name_plural": "alertas operacionais",
                "ordering": ["-created_at"],
            },
        ),
    ]
