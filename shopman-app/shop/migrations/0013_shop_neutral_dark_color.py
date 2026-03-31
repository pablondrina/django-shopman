from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0012_alter_shop_neutral_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="shop",
            name="neutral_dark_color",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Fundo da página no modo escuro. Superfícies escurecem para preto. Vazio = derivado do tom claro.",
                max_length=9,
                verbose_name="tom neutro (escuro)",
            ),
        ),
    ]
