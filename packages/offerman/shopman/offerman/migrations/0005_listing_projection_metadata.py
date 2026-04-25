from django.db import migrations, models


def forwards(apps, schema_editor):
    Listing = apps.get_model("offerman", "Listing")
    for listing in Listing.objects.all().iterator():
        projected_skus = list(getattr(listing, "projected_skus", []) or [])
        metadata = dict(getattr(listing, "projection_metadata", {}) or {})
        if projected_skus and "last_projected_skus" not in metadata:
            metadata["last_projected_skus"] = projected_skus
            listing.projection_metadata = metadata
            listing.save(update_fields=["projection_metadata"])


def backwards(apps, schema_editor):
    Listing = apps.get_model("offerman", "Listing")
    for listing in Listing.objects.all().iterator():
        metadata = dict(getattr(listing, "projection_metadata", {}) or {})
        listing.projected_skus = list(metadata.get("last_projected_skus", []))
        listing.save(update_fields=["projected_skus"])


class Migration(migrations.Migration):

    dependencies = [
        ("offerman", "0004_alter_product_sku"),
    ]

    operations = [
        migrations.AddField(
            model_name="listing",
            name="projection_metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="metadados de projeção",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name="listing",
            name="projected_skus",
        ),
    ]
