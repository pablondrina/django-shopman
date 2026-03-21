"""
Shopman Accounting API — URL configuration.
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "accounting"

urlpatterns = [
    path("cash-flow/", views.CashFlowView.as_view(), name="cash-flow"),
    path("accounts/", views.AccountsSummaryView.as_view(), name="accounts"),
    path("entries/", views.EntriesView.as_view(), name="entries"),
    path("payables/", views.CreatePayableView.as_view(), name="payables"),
]
