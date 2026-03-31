"""Design System v2: logo upload, radius presets, font choices."""

from django.db import migrations, models
import shop.models


def convert_radius_values(apps, schema_editor):
    """Convert old radius preset names to new ones."""
    Shop = apps.get_model("shop", "Shop")
    mapping = {
        "sharp": "square",
        "relaxed": "default",
        "rounded": "strong",
        "pill": "round",
        # "default" stays "default"
    }
    for shop in Shop.objects.all():
        new_val = mapping.get(shop.border_radius)
        if new_val:
            shop.border_radius = new_val
            shop.save(update_fields=["border_radius"])


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0010_oklch_color_system"),
    ]

    operations = [
        # ── Logo: URLField → FileField ──
        migrations.RemoveField(
            model_name="shop",
            name="logo_url",
        ),
        migrations.AddField(
            model_name="shop",
            name="logo",
            field=models.FileField(
                blank=True,
                help_text="SVG, PNG, JPG ou WebP. Máximo 2MB. Exibido com altura de 40px no header.",
                upload_to="branding/",
                validators=[shop.models.validate_logo],
                verbose_name="logotipo",
            ),
        ),
        # ── Border radius: new choices ──
        migrations.AlterField(
            model_name="shop",
            name="border_radius",
            field=models.CharField(
                choices=[
                    ("square", "Quadrado (0px)"),
                    ("soft", "Suave (4px)"),
                    ("default", "Padrão (8px)"),
                    ("strong", "Forte (16px)"),
                    ("round", "Redondo (9999px)"),
                ],
                default="default",
                help_text="Define o arredondamento dos cantos de botões, cards e inputs",
                max_length=20,
                verbose_name="arredondamento",
            ),
        ),
        migrations.RunPython(convert_radius_values, migrations.RunPython.noop),
        # ── Fonts: add choices ──
        migrations.AlterField(
            model_name="shop",
            name="heading_font",
            field=models.CharField(
                choices=[
                    ("Playfair Display", "Playfair Display"),
                    ("Cormorant Garamond", "Cormorant Garamond"),
                    ("Lora", "Lora"),
                    ("Merriweather", "Merriweather"),
                    ("EB Garamond", "EB Garamond"),
                    ("Libre Baskerville", "Libre Baskerville"),
                    ("DM Serif Display", "DM Serif Display"),
                    ("Fraunces", "Fraunces"),
                    ("Bitter", "Bitter"),
                    ("Crimson Pro", "Crimson Pro"),
                ],
                default="Playfair Display",
                max_length=100,
                verbose_name="fonte de títulos",
            ),
        ),
        migrations.AlterField(
            model_name="shop",
            name="body_font",
            field=models.CharField(
                choices=[
                    ("Inter", "Inter"),
                    ("DM Sans", "DM Sans"),
                    ("Work Sans", "Work Sans"),
                    ("Plus Jakarta Sans", "Plus Jakarta Sans"),
                    ("Nunito Sans", "Nunito Sans"),
                    ("Source Sans 3", "Source Sans 3"),
                    ("Outfit", "Outfit"),
                    ("Raleway", "Raleway"),
                    ("Rubik", "Rubik"),
                    ("Manrope", "Manrope"),
                ],
                default="Inter",
                max_length=100,
                verbose_name="fonte de corpo",
            ),
        ),
    ]
