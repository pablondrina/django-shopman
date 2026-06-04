"""Re-anchor KDSTicket from a FK→Order to a ``session_key`` string ref.

``Order.session_key`` is sealed at commit, so the same key resolves to the
open Session (comanda) before commit and to the Order after — unifying KDS
across channels and enabling progressive (course-by-course) firing from a
comanda without re-pointing tickets. The FK is dropped entirely (no residual);
existing dev tickets are backfilled from ``order.session_key`` first.
"""

from django.db import migrations, models


def backfill_session_key(apps, schema_editor):
    KDSTicket = apps.get_model("backstage", "KDSTicket")
    for ticket in KDSTicket.objects.all().iterator():
        order = ticket.order
        ticket.session_key = (getattr(order, "session_key", "") or "") if order else ""
        ticket.save(update_fields=["session_key"])


def noop_reverse(apps, schema_editor):
    # Pre-prod: migrations reset before launch; the FK linkage is not restored.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0010_kdsticket_cancelled_at_and_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="kdsticket",
            name="session_key",
            field=models.CharField(
                "chave da venda",
                db_index=True,
                default="",
                help_text="Resolve para a Session aberta (comanda) ou o Order selado.",
                max_length=64,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_session_key, noop_reverse),
        migrations.RemoveField(
            model_name="kdsticket",
            name="order",
        ),
    ]
