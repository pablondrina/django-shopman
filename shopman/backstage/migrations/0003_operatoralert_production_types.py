from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0002_update_group_permissions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="operatoralert",
            name="type",
            field=models.CharField(
                choices=[
                    ("notification_failed", "Notificação falhou"),
                    ("payment_failed", "Pagamento falhou"),
                    ("stock_discrepancy", "Discrepância de estoque"),
                    ("payment_after_cancel", "Pagamento após cancelamento"),
                    ("stock_low", "Estoque baixo"),
                    ("marketplace_rejected_unavailable", "Marketplace rejeitado: indisponível"),
                    ("marketplace_rejected_oos", "Marketplace rejeitado: sem estoque"),
                    ("pos_rejected_unavailable", "POS rejeitado: produto indisponível"),
                    ("stale_new_order", "Pedido parado aguardando confirmação"),
                    ("production_late", "Produção atrasada"),
                    ("production_low_yield", "Produção com yield baixo"),
                    ("production_stock_short", "Produção sem insumo suficiente"),
                ],
                max_length=50,
                verbose_name="tipo",
            ),
        ),
    ]
