from django.urls import include, path

urlpatterns = [
    path("api/", include("shopman.omniman.api.urls")),
]
