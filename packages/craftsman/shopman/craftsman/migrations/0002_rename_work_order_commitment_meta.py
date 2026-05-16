from django.db import migrations

OLD_KEY = "serves_order_refs"
NEW_KEY = "committed_order_refs"


def forwards(apps, schema_editor):
    WorkOrder = apps.get_model("craftsman", "WorkOrder")
    for work_order in WorkOrder.objects.exclude(meta__isnull=True).iterator():
        meta = dict(work_order.meta or {})
        if OLD_KEY not in meta:
            continue
        refs = [*list(meta.get(NEW_KEY) or []), *list(meta.pop(OLD_KEY) or [])]
        if refs:
            meta[NEW_KEY] = list(dict.fromkeys(refs))
        work_order.meta = meta
        work_order.save(update_fields=["meta"])


def backwards(apps, schema_editor):
    WorkOrder = apps.get_model("craftsman", "WorkOrder")
    for work_order in WorkOrder.objects.exclude(meta__isnull=True).iterator():
        meta = dict(work_order.meta or {})
        if NEW_KEY not in meta:
            continue
        refs = [*list(meta.get(OLD_KEY) or []), *list(meta.pop(NEW_KEY) or [])]
        if refs:
            meta[OLD_KEY] = list(dict.fromkeys(refs))
        work_order.meta = meta
        work_order.save(update_fields=["meta"])


class Migration(migrations.Migration):

    dependencies = [
        ("craftsman", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
