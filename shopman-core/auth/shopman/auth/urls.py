"""
Auth URL configuration.

Include in your project's urls.py:
    path("auth/", include("shopman.auth.urls")),
"""

from django.urls import path

from .views.access_link import AccessLinkCreateView, AccessLinkExchangeView
from .views.devices import DeviceListView, DeviceRevokeView
from .views.health import HealthCheckView
from .views.access_link_request import AccessLinkRequestView
from .views.logout import LogoutView
from .views.verification_code import VerificationCodeRequestView, VerificationCodeVerifyView

app_name = "shopman_auth"

urlpatterns = [
    # Access Link (link de acesso do Manychat)
    path("bridge/", AccessLinkExchangeView.as_view(), name="bridge-exchange"),
    path("bridge/create/", AccessLinkCreateView.as_view(), name="bridge-create"),
    # Verification Code (login externo via OTP)
    path("code/request/", VerificationCodeRequestView.as_view(), name="code-request"),
    path("code/verify/", VerificationCodeVerifyView.as_view(), name="code-verify"),
    # Access Link (login via email - one click)
    path("access-link/", AccessLinkRequestView.as_view(), name="access-link"),
    # Devices
    path("devices/", DeviceListView.as_view(), name="device-list"),
    path("devices/<uuid:device_id>/", DeviceRevokeView.as_view(), name="device-revoke"),
    # Logout
    path("logout/", LogoutView.as_view(), name="logout"),
    # Health check (load balancers, Kubernetes probes)
    path("health/", HealthCheckView.as_view(), name="health"),
]
