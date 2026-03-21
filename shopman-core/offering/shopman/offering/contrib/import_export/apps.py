from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OfferingImportExportConfig(AppConfig):
    name = "shopman.offering.contrib.import_export"
    label = "offering_import_export"
    verbose_name = _("Offering Import/Export")
