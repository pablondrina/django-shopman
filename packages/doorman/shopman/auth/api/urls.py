from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("request-code/", views.RequestCodeView.as_view(), name="auth-request-code"),
    path("verify-code/", views.VerifyCodeView.as_view(), name="auth-verify-code"),
]
