from __future__ import annotations

from django.urls import path

from ..views.access_link import AccessLinkCreateView
from . import views

urlpatterns = [
    path("access/create/", AccessLinkCreateView.as_view(), name="auth-access-create"),
    path("request-code/", views.RequestCodeView.as_view(), name="auth-request-code"),
    path("verify-code/", views.VerifyCodeView.as_view(), name="auth-verify-code"),
]
