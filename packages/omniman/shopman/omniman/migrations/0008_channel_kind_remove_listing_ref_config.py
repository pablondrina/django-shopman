"""
WP-K1: Restaura Channel.kind (era flow), remove listing_ref e config.

- flow → kind: restauração do design original, field renomeado por engano
- listing_ref: removido — Listing usa channel.ref por convenção (listing.ref == channel.ref)
- config: removido — framework tem seu próprio storage model (ChannelConfig) via ref
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("omniman", "0007_channel_flow"),
    ]

    operations = [
        # 1. Adiciona campo kind com os valores atuais de flow
        migrations.AddField(
            model_name="channel",
            name="kind",
            field=models.CharField(
                default="base",
                help_text=(
                    "Tipo comportamental do canal. Usado pelo framework para resolver "
                    "a classe de Flow: base, local, pos, totem, remote, web, whatsapp, "
                    "manychat, marketplace, ifood."
                ),
                max_length=32,
                verbose_name="tipo",
            ),
        ),
        # 2. Copia valores de flow para kind
        migrations.RunSQL(
            sql="UPDATE omniman_channel SET kind = flow",
            reverse_sql="UPDATE omniman_channel SET flow = kind",
        ),
        # 3. Remove flow
        migrations.RemoveField(
            model_name="channel",
            name="flow",
        ),
        # 4. Remove listing_ref
        migrations.RemoveField(
            model_name="channel",
            name="listing_ref",
        ),
        # 5. Remove config
        migrations.RemoveField(
            model_name="channel",
            name="config",
        ),
    ]
