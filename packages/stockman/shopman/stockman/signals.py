"""
Stockman signals — domain events emitted by stock operations.
"""

from __future__ import annotations

from django.dispatch import Signal

# Emitted when planned holds are materialized (transferred from planned → physical quant).
# Kwargs: hold_ids (list[str]), sku (str), target_date (date), to_position (Position)
holds_materialized = Signal()
