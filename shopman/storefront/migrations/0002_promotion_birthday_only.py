from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storefront', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='promotion',
            name='birthday_only',
            field=models.BooleanField(
                default=False,
                help_text='Se marcado, desconto aplicável somente no dia do aniversário do cliente.',
                verbose_name='apenas aniversariantes',
            ),
        ),
    ]
