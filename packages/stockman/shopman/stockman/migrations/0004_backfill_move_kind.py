"""Backfill Move.kind from existing free-text reasons.

New rows default to ADJUST (the field default). Historical rows are upgraded here
by matching reason patterns; anything unmatched stays ADJUST (honest: it was never
attributed). Uses the historical model, whose plain manager bypasses the runtime
immutability guard — this is a one-time metadata backfill, not a ledger mutation.
"""

from django.db import migrations

# (reason substring, kind) — applied in order; later wins on overlap so e.g.
# "Devolução de compra" lands on RETURN, not BUY.
_PATTERNS = [
    ("produ", "make"),       # Produção / produzido
    ("compra", "buy"),
    ("venda", "sell"),
    ("transfer", "transfer"),
    ("devolu", "return"),     # devolução
]


def backfill(apps, schema_editor):
    Move = apps.get_model("stockman", "Move")
    for needle, kind in _PATTERNS:
        Move.objects.filter(reason__icontains=needle).exclude(kind=kind).update(kind=kind)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("stockman", "0003_move_kind_alter_move_reason_and_more"),
    ]
    operations = [migrations.RunPython(backfill, noop)]
