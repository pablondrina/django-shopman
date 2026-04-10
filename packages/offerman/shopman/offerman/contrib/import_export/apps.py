from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OffermanImportExportConfig(AppConfig):
    name = "shopman.offerman.contrib.import_export"
    label = "offerman_import_export"
    verbose_name = _("Offerman Import/Export")
