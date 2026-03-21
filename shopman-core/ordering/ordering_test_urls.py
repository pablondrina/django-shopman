from django.urls import include, path

urlpatterns = [
    path("api/", include("shopman.ordering.api.urls")),
]
